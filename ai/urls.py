from django.urls import path

from ai.views import (
    ExtractCVView,
    ValidateCVView,
    SuggestionsView,
    OptimizeCVView,
    RewriteView,
    ImproveView,
)


urlpatterns = [
    path(
        "extract/",
        ExtractCVView.as_view(),
        name="ai-extract",
    ),
    path(
        "validate/",
        ValidateCVView.as_view(),
        name="ai-validate",
    ),
    path(
        "suggestions/",
        SuggestionsView.as_view(),
        name="ai-suggestions",
    ),
    path(
        "optimize/",
        OptimizeCVView.as_view(),
        name="ai-optimize",
    ),
    path(
        "rewrite/",
        RewriteView.as_view(),
        name="ai-rewrite",
    ),
    path(
        "improve/",
        ImproveView.as_view(),
        name="ai-improve",
    ),
]