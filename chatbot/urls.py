from django.urls import path

from chatbot.views import (
    ChatMessageCreateView,
    ChatSessionCreateView,
    ChatSessionDetailView,
    ChatDraftView,
    ChatFinalReviewView,
    ChatFinalReviewDecisionView,
    ChatReopenView,
)


urlpatterns = [
    path('sessions/<uuid:session_id>/draft/', ChatDraftView.as_view(), name='chat-draft'),
    path('sessions/<uuid:session_id>/reopen/', ChatReopenView.as_view(), name='chat-reopen'),
    path('sessions/<uuid:session_id>/final-review/', ChatFinalReviewView.as_view(), name='chat-final-review'),
    path('sessions/<uuid:session_id>/final-review/decisions/', ChatFinalReviewDecisionView.as_view(), name='chat-final-review-decisions'),
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
