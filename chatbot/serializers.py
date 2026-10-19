from rest_framework import serializers
from cvs.serializers import CareerLevelField
from shared.enums.career_level import CareerLevel
from chatbot.services.career_profiles import profile_name, PROFILES

from chatbot.models import (
    ChatMessage,
    ChatSession,
)


class InterviewCareerLevelField(CareerLevelField):
    def to_internal_value(self, value):
        profile = profile_name(value)
        return PROFILES[profile][1] if profile else super().to_internal_value(value)


class ChatSessionCreateSerializer(
    serializers.Serializer
):
    cv_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )
    cv_name = serializers.CharField(required=False, max_length=255)
    target_role = serializers.CharField(required=False, allow_blank=True, max_length=255)
    career_level = InterviewCareerLevelField(required=False, choices=['', 'student'] + [level.value for level in CareerLevel])
    template_id = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        profile = profile_name(self.initial_data.get('career_level'))
        if profile:
            attrs['question_profile'] = profile
        return attrs

    def validate_template_id(self, value):
        from templates_app.services import TemplateService
        if value and not TemplateService.template_exists(value):
            raise serializers.ValidationError('The selected template is unavailable.')
        return value


class ChatSessionListSerializer(serializers.ModelSerializer):
    cv_name = serializers.SerializerMethodField()

    def get_cv_name(self, obj):
        return obj.conversation_state.get('cv_name', '')

    class Meta:
        model = ChatSession
        fields = ['id', 'cv_id', 'cv_name', 'status', 'current_section', 'updated_at']


class ChatMessageInputSerializer(
    serializers.Serializer
):
    request_id = serializers.UUIDField(required=False)
    expected_updated_at = serializers.DateTimeField(required=False)
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


class FinalReviewRequestSerializer(serializers.Serializer):
    approved_external_processing = serializers.BooleanField()
    fingerprint = serializers.CharField(min_length=64, max_length=64)


class FinalReviewDecisionSerializer(serializers.Serializer):
    fingerprint = serializers.CharField(min_length=64, max_length=64)
    accepted_indexes = serializers.ListField(child=serializers.IntegerField(min_value=0), max_length=30)
