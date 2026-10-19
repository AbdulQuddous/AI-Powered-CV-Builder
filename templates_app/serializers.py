# templates_app/serializers.py

from rest_framework import serializers

from .models import CVTemplate
from .catalogue import definition, CATEGORIES
from django.templatetags.static import static


class CVTemplateSerializer(serializers.ModelSerializer):

    preview_url = serializers.SerializerMethodField()
    gallery_category = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    layout_family = serializers.SerializerMethodField()
    design_config = serializers.SerializerMethodField()
    preview_html_url = serializers.SerializerMethodField()

    def get_gallery_category(self, obj):
        row = definition(obj)
        return row['category'] if row else {'minimal': 'minimalist', 'technical': 'modern'}.get(obj.category, obj.category)

    def get_category_label(self, obj):
        return CATEGORIES.get(self.get_gallery_category(obj), obj.get_category_display())

    def get_layout_family(self, obj):
        row = definition(obj)
        return row['layout_family'] if row else 'custom'

    def get_design_config(self, obj):
        row = definition(obj)
        return row['design_config'] if row else {}

    def get_preview_html_url(self, obj):
        return f'/api/cvs/templates/{obj.pk}/preview/'


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
            "preview_url", "gallery_category", "category_label", "layout_family", "design_config", "preview_html_url",
            "is_available",
            "version",
        ]

    def get_preview_url(self, obj):
        row = definition(obj)
        path = obj.preview_image or (row['preview_image'] if row else '')
        if not path:
            return None
        url = static(path)
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url
