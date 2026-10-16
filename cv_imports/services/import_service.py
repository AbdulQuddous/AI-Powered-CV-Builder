from django.utils import timezone
from rest_framework.exceptions import APIException

from cv_imports.models import CVImport

from .extractors import (
    ExtractionError,
    extract_text,
)
from .text_cleaner import clean_extracted_text


class ImportInProgress(APIException):
    status_code = 409
    default_code = 'import_in_progress'
    default_detail = 'This document is already being extracted. Refresh its status before retrying.'


def process_cv_import(cv_import):

    # Compare-and-set makes claiming a job atomic without holding a database
    # transaction open while parsing a file. Successful extraction is reusable.
    claimed = CVImport.objects.filter(pk=cv_import.pk).exclude(
        status__in=[CVImport.Status.EXTRACTING, CVImport.Status.EXTRACTED]
    ).update(status=CVImport.Status.EXTRACTING, error_message='', updated_at=timezone.now())
    if not claimed:
        cv_import.refresh_from_db()
        if cv_import.status == CVImport.Status.EXTRACTED:
            return cv_import
        raise ImportInProgress()

    cv_import.status = (
        CVImport.Status.EXTRACTING
    )

    cv_import.error_message = ""

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
    finally:
        cv_import.file.close()
