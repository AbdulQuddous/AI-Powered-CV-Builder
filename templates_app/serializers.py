# templates_app/serializers.py

from rest_framework import serializers

from .models import CVTemplate


class CVTemplateSerializer(serializers.ModelSerializer):

    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = CVTemplate
        fields = [
            "id",
            "name",
            "description",
            "category",
            "ats_compatible",
            "supported_levels",
            "supported_roles",
            "preview_url",
            "is_available",
            "version",
        ]

    def get_preview_url(self, obj):
        if not obj.preview_image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(
                f"/static/{obj.preview_image}"
            )

        return f"/static/{obj.preview_image}"