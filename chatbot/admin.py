from django.contrib import admin

from chatbot.models import (
    ChatMessage,
    ChatSession,
)


class ChatMessageInline(
    admin.TabularInline
):
    model = ChatMessage
    extra = 0
    readonly_fields = [
        "role",
        "content",
        "intent",
        "section",
        "cv_updates",
        "next_action",
        "created_at",
    ]


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "cv_id",
        "status",
        "current_section",
        "created_at",
    ]

    list_filter = [
        "status",
        "current_section",
    ]

    search_fields = [
        "id",
        "user__email",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
    ]

    inlines = [
        ChatMessageInline
    ]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "session",
        "role",
        "section",
        "intent",
        "created_at",
    ]

    list_filter = [
        "role",
        "section",
        "intent",
    ]