from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from chatbot.models import ChatSession
from chatbot.serializers import (
    ChatMessageInputSerializer,
    ChatSessionCreateResponseSerializer,
    ChatSessionCreateSerializer,
    ChatSessionDetailSerializer,
    ChatSessionListSerializer,
)
from rest_framework.pagination import PageNumberPagination
from chatbot.services.conversation_service import (
    create_chat_session,
    process_user_message,
)
from chatbot.services.existing_cv_conversation import prepare_existing_session
from chatbot.services.content_handling import repair_hostile_experience
from chatbot.services.optional_section_recovery import repair_optional_answers
from chatbot.services.project_recovery import repair_project_profile_split
from chatbot.services.errors import AIServiceError, AIRateLimitError
from chatbot.services.response_validator import (
    InvalidAIResponse,
)


class ChatSessionCreateView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(ChatSession.objects.filter(user=request.user).order_by('-updated_at', '-id'), request)
        return paginator.get_paginated_response(ChatSessionListSerializer(page, many=True).data)

    def post(self, request):
        serializer = (
            ChatSessionCreateSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        session = create_chat_session(
            user=request.user,
            cv_id=serializer.validated_data.get(
                "cv_id"
            ),
            initial_values={key: value for key, value in serializer.validated_data.items() if key != 'cv_id'},
        )

        output = (
            ChatSessionCreateResponseSerializer(
                session
            )
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )


class ChatSessionDetailView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def get_object(self, request, session_id):
        return get_object_or_404(
            ChatSession,
            id=session_id,
            user=request.user,
        )

    def get(self, request, session_id):
        session = self.get_object(
            request,
            session_id,
        )
        prepare_existing_session(session)
        repair_hostile_experience(session)
        repair_optional_answers(session)
        repair_project_profile_split(session)

        serializer = (
            ChatSessionDetailSerializer(
                session
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class ChatMessageCreateView(APIView):
    throttle_scope = 'm5_chat'
    permission_classes = [
        IsAuthenticated
    ]

    def get_session(
        self,
        request,
        session_id,
    ):
        return get_object_or_404(
            ChatSession,
            id=session_id,
            user=request.user,
        )

    def post(
        self,
        request,
        session_id,
    ):
        input_serializer = (
            ChatMessageInputSerializer(
                data=request.data
            )
        )

        input_serializer.is_valid(
            raise_exception=True
        )

        session = self.get_session(
            request,
            session_id,
        )

        try:
            assistant_message = (
                process_user_message(
                    session=session,
                    request_id=input_serializer.validated_data.get('request_id'),
                    expected_updated_at=input_serializer.validated_data.get('expected_updated_at'),
                    user_message=(
                        input_serializer
                        .validated_data[
                            "message"
                        ]
                    ),
                )
            )

        except ValueError as exc:
            return Response(
                {
                    "code": (
                        "chat_session_inactive"
                    ),
                    "detail": str(exc),
                },
                status=status.HTTP_409_CONFLICT,
            )

        except InvalidAIResponse:
            return Response(
                {
                    "code": (
                        "invalid_ai_response"
                    ),
                    "detail": (
                        "The AI provider returned "
                        "an invalid structured "
                        "response."
                    ),
                },
                status=(
                    status.HTTP_502_BAD_GATEWAY
                ),
            )

        except AIRateLimitError:
            return Response({'code': 'ai_rate_limit', 'detail': 'The AI service is busy. Please retry shortly.'}, status=429)

        except AIServiceError:
            return Response(
                {
                    "code": "ai_service_error",
                    "detail": (
                        "Local Qwen is unavailable. Check Ollama and the installed model, "
                        "then retry. Simple field answers still work."
                    ),
                },
                status=(
                    status.HTTP_502_BAD_GATEWAY
                ),
            )

        return Response(
            {
                "assistant_message": (
                    assistant_message.content
                ),
                "intent": (
                    assistant_message.intent
                ),
                "section": (
                    assistant_message.section
                ),
                "cv_updates": (
                    assistant_message.cv_updates
                ),
                "next_action": (
                    assistant_message.next_action
                ),
            },
            status=status.HTTP_200_OK,
        )


class ChatDraftView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        from ai.services.final_review import draft_for_review, fingerprint
        session = get_object_or_404(ChatSession, pk=session_id, user=request.user)
        repair_optional_answers(session)
        repair_project_profile_split(session)
        document, warnings = draft_for_review(session, include_warnings=True)
        from chatbot.services.question_engine import recommendations
        return Response({'draft': document, 'fingerprint': fingerprint(document),
                         'recommendations': recommendations(session.conversation_state),
                         'warnings': warnings})


class ChatReopenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        from django.db import transaction
        from chatbot.models import ChatMessage
        from chatbot.services.question_engine import question
        with transaction.atomic():
            session = get_object_or_404(ChatSession.objects.select_for_update(), pk=session_id, user=request.user)
            repair_optional_answers(session)
            repair_project_profile_split(session)
            if session.conversation_state.get('chat_saved_cv_id') or session.conversation_state.get('edit_saved_cv_id'):
                return Response({'detail': 'This draft has been saved. Use Continue with AI on the saved CV.'}, status=409)
            if session.status == 'archived':
                return Response({'detail': 'Archived conversations cannot be reopened.'}, status=409)
            if session.status == 'completed':
                session.status = 'active'
                session.conversation_state.pop('approved_review_changes', None)
                session.conversation_state.pop('review_decisions', None)
                session.save(update_fields=['status', 'conversation_state', 'updated_at'])
                ChatMessage.objects.create(session=session, role='assistant', intent='collect_information',
                    section=session.current_section, next_action='ask_question',
                    content='You can correct collected details, then finish again. ' + question(session.conversation_state))
        return Response(ChatSessionDetailSerializer(session).data)


class ChatFinalReviewView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'm6_ai'

    def post(self, request, session_id):
        from chatbot.serializers import FinalReviewRequestSerializer
        from ai.services.final_review import request_review
        from ai.exceptions import AIError
        serializer = FinalReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Owner check occurs before entering the service or calling a provider.
        get_object_or_404(ChatSession, pk=session_id, user=request.user)
        try:
            return Response(request_review(user=request.user, session_id=session_id,
                approved_external_processing=serializer.validated_data['approved_external_processing'],
                expected_fingerprint=serializer.validated_data['fingerprint']))
        except AIError:
            return Response({'code': 'final_review_unavailable', 'detail': 'Gemini review is unavailable. You can retry or save your validated CV without suggestions.'}, status=502)


class ChatFinalReviewDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        from chatbot.serializers import FinalReviewDecisionSerializer
        from ai.services.final_review import decide_review
        serializer = FinalReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(decide_review(user=request.user, session_id=session_id,
            expected_fingerprint=serializer.validated_data['fingerprint'],
            accepted_indexes=serializer.validated_data['accepted_indexes']))
