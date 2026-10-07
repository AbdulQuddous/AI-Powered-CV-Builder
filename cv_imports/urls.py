from django.urls import path

from .views import (
    CVImportDetailAPIView,
    CVImportExtractAPIView,
    CVImportUploadAPIView,
)


urlpatterns = [
    path(
        "upload/",
        CVImportUploadAPIView.as_view(),
        name="cv-import-upload",
    ),

    path(
        "<int:import_id>/",
        CVImportDetailAPIView.as_view(),
        name="cv-import-detail",
    ),

    path(
        "<int:import_id>/extract/",
        CVImportExtractAPIView.as_view(),
        name="cv-import-extract",
    ),
]