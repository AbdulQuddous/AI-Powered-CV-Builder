from rest_framework import serializers

from chatbot.models import (
    ChatMessage,
    ChatSession,
)


class ChatSessionCreateSerializer(
    serializers.Serializer
):
    cv_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )


class ChatMessageInputSerializer(
    serializers.Serializer
):
    message = serializers.CharField(
        max_length=10000,
        allow_blank=False,
        trim_whitespace=True,
    )


class ChatMessageSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ChatMessage

        fields = [
            "id",
            "role",
            "content",
            "intent",
            "section",
            "cv_updates",
            "next_action",
            "created_at",
        ]


class ChatSessionDetailSerializer(
    serializers.ModelSerializer
):
    messages = ChatMessageSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ChatSession

        fields = [
            "id",
            "cv_id",
            "status",
            "current_section",
            "conversation_state",
            "model_name",
            "created_at",
            "updated_at",
            "messages",
        ]


class ChatSessionCreateResponseSerializer(
    serializers.ModelSerializer
):
    assistant_message = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = ChatSession

        fields = [
            "id",
            "cv_id",
            "status",
            "current_section",
            "assistant_message",
            "created_at",
        ]

    def get_assistant_message(self, obj):
        message = (
            obj.messages.filter(
                role=ChatMessage.Role.ASSISTANT
            )
            .order_by("-created_at")
            .first()
        )

        return (
            message.content
            if message
            else None
        )