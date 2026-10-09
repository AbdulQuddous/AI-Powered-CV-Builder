import json

from rest_framework import serializers


class ExtractionSerializer(serializers.Serializer):
    raw_text = serializers.CharField(
        min_length=20,
        max_length=20000,
        trim_whitespace=True,
    )


class CVAnalysisSerializer(serializers.Serializer):
    cv = serializers.JSONField()

    target_role = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=200,
    )

    job_description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=10000,
    )

    use_ai = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate_cv(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "CV must be a JSON object."
            )

        size = len(
            json.dumps(
                value,
                ensure_ascii=False,
            ).encode("utf-8")
        )

        if size > 50000:
            raise serializers.ValidationError(
                "CV exceeds the supported size."
            )

        return value


class WritingSerializer(serializers.Serializer):
    text = serializers.CharField(
        max_length=3000,
    )

    section = serializers.ChoiceField(
        choices=[
            "summary",
            "experience",
            "projects",
            "education",
            "achievements",
            "certifications",
        ],
    )

    target_role = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=200,
    )