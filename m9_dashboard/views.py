from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def dashboard_page(request):
    """
    M9 dashboard page.

    Responsibilities:
    - Serve the dashboard frontend.
    - Do not access the database.
    - Do not perform CV CRUD operations.
    - Do not call the AI engine.

    All CV data is requested by JavaScript
    through existing authenticated M2 APIs.
    """

    return render(
        request,
        "m9_dashboard/dashboard.html",
    )