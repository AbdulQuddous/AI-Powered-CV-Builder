from django.urls import path

from chatbot.views import (
    ChatMessageCreateView,
    ChatSessionCreateView,
    ChatSessionDetailView,
)


urlpatterns = [
    path(
        "sessions/",
        ChatSessionCreateView.as_view(),
        name="chat-session-create",
    ),

    path(
        "sessions/<uuid:session_id>/",
        ChatSessionDetailView.as_view(),
        name="chat-session-detail",
    ),

    path(
        "sessions/<uuid:session_id>/messages/",
        ChatMessageCreateView.as_view(),
        name="chat-message-create",
    ),
]