from django.contrib import admin

from .models import CVImport


@admin.register(CVImport)
class CVImportAdmin(admin.ModelAdmin):

    list_display = [
        "id",
        "original_file_name",
        "user",
        "file_type",
        "status",
        "file_size",
        "created_at",
    ]

    list_filter = [
        "file_type",
        "status",
        "created_at",
    ]

    search_fields = [
        "original_file_name",
        "user__email",
    ]

    readonly_fields = [
        "raw_text",
        "cleaned_text",
        "error_message",
        "created_at",
        "updated_at",
        "extracted_at",
    ]