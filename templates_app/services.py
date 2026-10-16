# templates_app/services.py

from django.core.exceptions import ObjectDoesNotExist

from .models import CVTemplate


class TemplateService:

    @staticmethod
    def list_available_templates():
        return CVTemplate.objects.filter(
            is_available=True
        )

    @staticmethod
    def get_template(template_id):
        try:
            return CVTemplate.objects.get(
                id=template_id,
                is_available=True
            )
        except ObjectDoesNotExist:
            return None

    @staticmethod
    def template_exists(template_id):
        return CVTemplate.objects.filter(
            id=template_id,
            is_available=True
        ).exists()

    @staticmethod
    def is_compatible(template, level=None, role=None):

        if level and template.supported_levels and level not in template.supported_levels:
            return False

        if role and template.supported_roles and role not in template.supported_roles:
            return False

        return True
