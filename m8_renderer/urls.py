from django.urls import path

from .views import (
    CVPreviewView,
    CVDocumentPreviewView,
    TemplatePreviewView,
    CVPDFExportView,
    CVDOCXExportView,
)


urlpatterns = [
    path("<int:cv_id>/preview/document/", CVDocumentPreviewView.as_view(), name="m8-cv-document-preview"),
    path("templates/<slug:template_id>/preview/", TemplatePreviewView.as_view(), name="m8-template-preview"),
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