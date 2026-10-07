# templates_app/models.py

from django.db import models


class CVTemplate(models.Model):

    class Category(models.TextChoices):
        PROFESSIONAL = "professional", "Professional"
        MODERN = "modern", "Modern"
        MINIMAL = "minimal", "Minimal"
        CREATIVE = "creative", "Creative"
        TECHNICAL = "technical", "Technical"

    id = models.SlugField(
        primary_key=True,
        max_length=50,
        editable=False
    )

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    category = models.CharField(
        max_length=30,
        choices=Category.choices
    )

    ats_compatible = models.BooleanField(
        default=True
    )

    supported_levels = models.JSONField(
        default=list
    )

    supported_roles = models.JSONField(
        default=list
    )

    preview_image = models.CharField(
        max_length=255,
        blank=True
    )

    template_path = models.CharField(
        max_length=255
    )

    is_available = models.BooleanField(
        default=True
    )

    version = models.PositiveIntegerField(
        default=1
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name