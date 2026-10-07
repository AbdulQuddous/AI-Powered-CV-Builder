# cv_imports/serializers.py

from rest_framework import serializers

from .models import CVImport
from .services.validators import (
    validate_cv_file,
)


class CVImportUploadSerializer(
    serializers.Serializer
):

    file = serializers.FileField()

    def validate_file(self, value):

        file_type = validate_cv_file(value)

        self.context["file_type"] = file_type

        return value


class CVImportDetailSerializer(
    serializers.ModelSerializer
):

    import_id = serializers.IntegerField(
        source="id",
        read_only=True,
    )

    file_name = serializers.CharField(
        source="original_file_name",
        read_only=True,
    )

    text = serializers.CharField(
        source="cleaned_text",
        read_only=True,
    )

    class Meta:
        model = CVImport

        fields = [
            "import_id",
            "file_name",
            "file_type",
            "file_size",
            "status",
            "text",
            "error_message",
            "created_at",
            "extracted_at",
        ]