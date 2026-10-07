from django.conf import settings
from django.db import models


class CVImport(models.Model):

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        EXTRACTING = "extracting", "Extracting"
        EXTRACTED = "extracted", "Extracted"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cv_imports",
    )

    file = models.FileField(
        upload_to="cv_imports/%Y/%m/"
    )

    original_file_name = models.CharField(
        max_length=255
    )

    file_type = models.CharField(
        max_length=10,
        choices=FileType.choices,
    )

    file_size = models.PositiveBigIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )

    raw_text = models.TextField(
        blank=True
    )

    cleaned_text = models.TextField(
        blank=True
    )

    error_message = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    extracted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.original_file_name} "
            f"({self.status})"
        )