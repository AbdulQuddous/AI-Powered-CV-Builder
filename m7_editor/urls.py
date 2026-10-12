from django.urls import path
from .views import cv_editor_page

app_name = "m7_editor"

urlpatterns = [
    path("cvs/<str:cv_id>/edit/", cv_editor_page, name="edit"),
]
