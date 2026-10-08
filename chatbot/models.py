import uuid

from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )

    # External reference only.
    # This is intentionally NOT a ForeignKey to M2.
    cv_id = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    current_section = models.CharField(
        max_length=50,
        default="target",
    )

    conversation_state = models.JSONField(
        default=dict,
        blank=True,
    )

    model_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ChatSession {self.id} - {self.user_id}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    id = models.BigAutoField(
        primary_key=True,
    )

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )

    content = models.TextField()

    # Assistant response metadata.
    intent = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    section = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    cv_updates = models.JSONField(
        default=dict,
        blank=True,
    )

    next_action = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} message - {self.session_id}"