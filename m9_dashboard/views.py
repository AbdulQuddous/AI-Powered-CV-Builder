from pathlib import Path

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def dashboard_asset_version():
    """Refresh browser assets whenever a dashboard script or stylesheet changes."""
    root = Path(__file__).resolve().parent / 'static' / 'm9_dashboard'
    return str(max((asset.stat().st_mtime_ns for directory in ('js', 'css')
                    for asset in (root / directory).glob('*') if asset.is_file()), default=0))


@require_GET
@never_cache
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
        {'dashboard_asset_version': dashboard_asset_version()},
    )
