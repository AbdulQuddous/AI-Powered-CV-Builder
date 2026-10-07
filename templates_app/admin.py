# templates_app/admin.py

from django.contrib import admin

from .models import CVTemplate


@admin.register(CVTemplate)
class CVTemplateAdmin(admin.ModelAdmin):

    list_display = [
        "id",
        "name",
        "category",
        "ats_compatible",
        "is_available",
        "version",
    ]

    list_filter = [
        "category",
        "ats_compatible",
        "is_available",
    ]

    search_fields = [
        "id",
        "name",
        "description",
    ]

    ordering = [
        "name",
    ]