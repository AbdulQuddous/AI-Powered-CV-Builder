from django.urls import path

from .views import dashboard_page


app_name = "m9_dashboard"

urlpatterns = [
    path(
        "dashboard/",
        dashboard_page,
        name="dashboard",
    ),
]