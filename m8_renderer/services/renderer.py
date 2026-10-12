import re

from django.template.loader import render_to_string
from rest_framework.exceptions import ValidationError

from templates_app.services import TemplateService

from .context_builder import build_context


class CVRenderer:

    @staticmethod
    def render_html(payload):
        """
        Public rendering contract:

        {
            "template_id": "modern",
            "cv_data": {...}
        }
        """

        if not isinstance(payload, dict):
            raise ValidationError({
                "code": "invalid_payload",
                "detail": "Payload must be an object.",
            })

        template_id = payload.get("template_id")
        cv_data = payload.get("cv_data")

        if not isinstance(template_id, str) or not template_id:
            raise ValidationError({
                "code": "template_required",
                "detail": "A template ID is required.",
            })

        if not isinstance(cv_data, dict):
            raise ValidationError({
                "code": "invalid_cv_data",
                "detail": "cv_data must be an object.",
            })

        # Resolve the template through existing M3.
        template = TemplateService.get_template(
            template_id
        )

        if template is None:
            raise ValidationError({
                "code": "invalid_template",
                "detail": "Template does not exist or is unavailable.",
            })

        template_path = template.template_path

        # Only allow application-managed CV templates.
        if not isinstance(template_path, str) or not re.fullmatch(
            r"cv_templates/[A-Za-z0-9_-]+\.html",
            template_path,
        ):
            raise ValidationError({
                "code": "invalid_template_path",
                "detail": "Invalid template configuration.",
            })

        context = build_context(cv_data)

        return render_to_string(
            template_path,
            context,
        )