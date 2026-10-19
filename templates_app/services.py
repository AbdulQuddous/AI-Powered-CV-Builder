# templates_app/services.py

from django.core.exceptions import ObjectDoesNotExist

from .models import CVTemplate
from .catalogue import is_renderable


class TemplateService:

    @staticmethod
    def list_available_templates():
        candidates = CVTemplate.objects.filter(is_available=True)
        return candidates.filter(pk__in=[t.pk for t in candidates if is_renderable(t)])

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
        template = TemplateService.get_template(template_id)
        return template is not None and is_renderable(template)

    @staticmethod
    def is_compatible(template, level=None, role=None):

        if level and template.supported_levels and level not in template.supported_levels:
            return False

        if role and template.supported_roles and role not in template.supported_roles:
            return False

        return True
