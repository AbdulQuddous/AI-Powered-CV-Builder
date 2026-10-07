# templates_app/urls.py

from django.urls import path

from .views import (
    TemplateListAPIView,
    TemplateDetailAPIView,
)

urlpatterns = [
    path(
        "",
        TemplateListAPIView.as_view(),
        name="template-list"
    ),

    path(
        "<slug:id>/",
        TemplateDetailAPIView.as_view(),
        name="template-detail"
    ),
]