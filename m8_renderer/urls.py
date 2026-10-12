from django.urls import path

from .views import (
    CVPreviewView,
    CVPDFExportView,
    CVDOCXExportView,
)


urlpatterns = [
    path(
        "<int:cv_id>/preview/",
        CVPreviewView.as_view(),
        name="m8-cv-preview",
    ),

    path(
        "<int:cv_id>/export/pdf/",
        CVPDFExportView.as_view(),
        name="m8-cv-export-pdf",
    ),

    path(
        "<int:cv_id>/export/docx/",
        CVDOCXExportView.as_view(),
        name="m8-cv-export-docx",
    ),
]