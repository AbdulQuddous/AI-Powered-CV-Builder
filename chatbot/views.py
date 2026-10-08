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
)
from chatbot.services.conversation_service import (
    create_chat_session,
    process_user_message,
)
from chatbot.services.groq_client import (
    AIServiceError,
)
from chatbot.services.response_validator import (
    InvalidAIResponse,
)


class ChatSessionCreateView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

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

        except AIServiceError:
            return Response(
                {
                    "code": "ai_service_error",
                    "detail": (
                        "The AI service is "
                        "temporarily unavailable."
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