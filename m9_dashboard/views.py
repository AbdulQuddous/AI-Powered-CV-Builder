from pathlib import Path
import json

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from shared.enums.career_level import CareerLevel
from chatbot.services.career_profiles import PROFILES


def dashboard_asset_version():
    """Refresh browser assets whenever a dashboard script or stylesheet changes."""
    root = Path(__file__).resolve().parent / 'static' / 'm9_dashboard'
    assets = [asset for directory in ('js', 'css') for asset in (root / directory).glob('*') if asset.is_file()]
    assets.append(root.parents[2] / 'accounts' / 'static' / 'accounts' / 'js' / 'session.js')
    return str(max(asset.stat().st_mtime_ns for asset in assets))


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
        {'dashboard_asset_version': dashboard_asset_version(),
         'career_levels': [{'value': level.value, 'label': level.value.title()} for level in CareerLevel],
         'interview_profiles': [{'value': key, 'label': value[0]} for key, value in PROFILES.items()],
         'cv_schema': json.loads((Path(__file__).resolve().parent.parent / 'shared' / 'schemas' / 'cv_schema.json').read_text())},
    )


@require_GET
@never_cache
def template_gallery_page(request):
    from templates_app.catalogue import CATEGORIES
    return render(request, 'm9_dashboard/template_gallery.html', {
        'categories': CATEGORIES.items(), 'dashboard_asset_version': dashboard_asset_version(),
    })
