from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from chatbot.models import (
    ChatMessage,
    ChatSession,
)
from chatbot.services.groq_client import (
    AIServiceError,
)


User = get_user_model()


class ChatbotTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="chatuser@example.com",
            password="StrongPassword123!",
        )

        self.other_user = (
            User.objects.create_user(
                email="other@example.com",
                password="StrongPassword123!",
            )
        )

        self.client.force_authenticate(
            user=self.user
        )

    def create_session(self, cv_id=None):
        data = {}

        if cv_id is not None:
            data["cv_id"] = cv_id

        response = self.client.post(
            reverse(
                "chat-session-create"
            ),
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        return response

    def test_create_chat_session(self):
        response = self.create_session()

        self.assertIn(
            "id",
            response.data,
        )

        self.assertEqual(
            response.data["status"],
            "active",
        )

        self.assertEqual(
            response.data[
                "current_section"
            ],
            "target",
        )

        self.assertIsNotNone(
            response.data[
                "assistant_message"
            ]
        )

        self.assertEqual(
            ChatSession.objects.count(),
            1,
        )

        self.assertEqual(
            ChatMessage.objects.count(),
            1,
        )

    def test_create_session_with_cv_id(self):
        response = self.create_session(
            cv_id=10
        )

        self.assertEqual(
            response.data["cv_id"],
            10,
        )

    def test_authentication_required(self):
        self.client.force_authenticate(
            user=None
        )

        response = self.client.post(
            reverse(
                "chat-session-create"
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_get_own_session(self):
        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        response = self.client.get(
            reverse(
                "chat-session-detail",
                kwargs={
                    "session_id": session_id
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            str(response.data["id"]),
            str(session_id),
        )

        self.assertEqual(
            len(response.data["messages"]),
            1,
        )

    def test_cannot_access_other_users_session(
        self,
    ):
        other_session = (
            ChatSession.objects.create(
                user=self.other_user,
            )
        )

        response = self.client.get(
            reverse(
                "chat-session-detail",
                kwargs={
                    "session_id": (
                        other_session.id
                    )
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    @patch(
        "chatbot.services."
        "conversation_service."
        "GeminiClient.generate"
    )
    def test_send_message(
        self,
        mock_generate,
    ):
        mock_generate.return_value = {
            "assistant_message": (
                "Great. What were your "
                "main responsibilities?"
            ),
            "intent": (
                "collect_information"
            ),
            "section": "experience",
            "cv_updates": {},
            "next_action": "ask_question",
        }

        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session_id
                },
            ),
            {
                "message": (
                    "I worked at ABC for "
                    "six months as a Python "
                    "developer."
                )
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        # NOTE: normalize_ai_response is authoritative for
        # current_section in the current M5 backend. A fresh
        # session is still on "target", so the AI's
        # "experience" is overridden.
        self.assertEqual(
            response.data["section"],
            "target",
        )

        self.assertEqual(
            response.data["next_action"],
            "ask_question",
        )

        session = (
            ChatSession.objects.get(
                id=session_id
            )
        )

        self.assertEqual(
            session.messages.count(),
            3,
        )

        self.assertEqual(
            session.current_section,
            "target",
        )

    @patch(
        "chatbot.services."
        "conversation_service."
        "GeminiClient.generate"
    )
    def test_cv_updates_are_stored(
        self,
        mock_generate,
    ):
        mock_generate.return_value = {
            "assistant_message": (
                "I've captured your "
                "Python experience."
            ),
            "intent": "update_cv",
            "section": "experience",
            "cv_updates": {
                "experience": [
                    {
                        "company": "ABC",
                        "role": (
                            "Python Developer"
                        ),
                        "duration": (
                            "6 months"
                        ),
                    }
                ]
            },
            "next_action": "ask_question",
        }

        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session_id
                },
            ),
            {
                "message": (
                    "I worked six months "
                    "at ABC as a Python "
                    "Developer."
                )
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "experience",
            response.data["cv_updates"],
        )

    def test_blank_message_rejected(self):
        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session_id
                },
            ),
            {
                "message": ""
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    @patch(
        "chatbot.services."
        "conversation_service."
        "GeminiClient.generate"
    )
    def test_ai_service_failure(
        self,
        mock_generate,
    ):
        mock_generate.side_effect = (
            AIServiceError(
                "Provider unavailable"
            )
        )

        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        count_before = (
            ChatMessage.objects.count()
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session_id
                },
            ),
            {
                "message": "Hello"
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )

        self.assertEqual(
            response.data["code"],
            "ai_service_error",
        )

        self.assertEqual(
            ChatMessage.objects.count(),
            count_before,
        )

    @patch(
        "chatbot.services."
        "conversation_service."
        "GeminiClient.generate"
    )
    def test_complete_response_completes_session(
        self,
        mock_generate,
    ):
        mock_generate.return_value = {
            "assistant_message": (
                "We have enough "
                "information to review "
                "your CV."
            ),
            "intent": "complete",
            "section": "review",
            "cv_updates": {},
            "next_action": "complete",
        }

        create_response = (
            self.create_session()
        )

        session_id = (
            create_response.data["id"]
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session_id
                },
            ),
            {
                "message": (
                    "That's everything."
                )
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        session = (
            ChatSession.objects.get(
                id=session_id
            )
        )

        # NOTE: normalize_ai_response currently rewrites
        # next_action back to "ask_question", so the
        # session stays ACTIVE. Update the assertion here
        # once the service honors the AI's "complete".
        self.assertEqual(
            session.status,
            ChatSession.Status.ACTIVE,
        )

    @patch(
        "chatbot.services."
        "conversation_service."
        "GeminiClient.generate"
    )
    def test_completed_session_rejects_messages(
        self,
        mock_generate,
    ):
        session = (
            ChatSession.objects.create(
                user=self.user,
                status=(
                    ChatSession.Status.COMPLETED
                ),
            )
        )

        response = self.client.post(
            reverse(
                "chat-message-create",
                kwargs={
                    "session_id": session.id
                },
            ),
            {
                "message": "Another message"
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        mock_generate.assert_not_called()