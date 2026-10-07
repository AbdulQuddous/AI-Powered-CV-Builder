from django.utils import timezone

from cv_imports.models import CVImport

from .extractors import (
    ExtractionError,
    extract_text,
)
from .text_cleaner import clean_extracted_text


def process_cv_import(cv_import):

    cv_import.status = (
        CVImport.Status.EXTRACTING
    )

    cv_import.error_message = ""

    cv_import.save(
        update_fields=[
            "status",
            "error_message",
            "updated_at",
        ]
    )

    try:
        raw_text = extract_text(
            cv_import.file,
            cv_import.file_type,
        )

        cleaned_text = clean_extracted_text(
            raw_text
        )

        cv_import.raw_text = raw_text
        cv_import.cleaned_text = cleaned_text
        cv_import.status = (
            CVImport.Status.EXTRACTED
        )
        cv_import.extracted_at = timezone.now()
        cv_import.error_message = ""

        cv_import.save(
            update_fields=[
                "raw_text",
                "cleaned_text",
                "status",
                "extracted_at",
                "error_message",
                "updated_at",
            ]
        )

        return cv_import

    except ExtractionError as exc:

        cv_import.status = (
            CVImport.Status.FAILED
        )

        cv_import.error_message = str(exc)

        cv_import.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        raise