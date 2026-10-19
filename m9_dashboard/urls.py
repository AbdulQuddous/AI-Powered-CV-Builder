from django.urls import path

from .views import dashboard_page, template_gallery_page


app_name = "m9_dashboard"

urlpatterns = [
    path("templates/", template_gallery_page, name="template-gallery"),
    path(
        "dashboard/",
        dashboard_page,
        name="dashboard",
    ),
]