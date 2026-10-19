from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_deny
from pathlib import Path
import json


@never_cache
@xframe_options_deny
def cv_editor_page(request, cv_id: str):
    """UI shell only. Existing M1/M2 APIs authorize and own all CV data."""
    root = Path(__file__).resolve().parent
    assets = list((root / 'static' / 'm7_editor').rglob('*.js')) + list((root / 'static' / 'm7_editor').rglob('*.css'))
    assets.append(root.parent / 'accounts' / 'static' / 'accounts' / 'js' / 'session.js')
    assets.extend((root.parent / 'm9_dashboard' / 'static' / 'm9_dashboard' / 'css').glob('*.css'))
    schema = json.loads((root.parent / 'shared' / 'schemas' / 'cv_schema.json').read_text())
    return render(request, "m7_editor/editor.html", {'cv_id': cv_id, 'cv_schema': schema,
        'editor_asset_version': str(max(asset.stat().st_mtime_ns for asset in assets))})
