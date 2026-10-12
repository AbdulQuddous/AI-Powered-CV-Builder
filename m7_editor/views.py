from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_deny


@never_cache
@xframe_options_deny
def cv_editor_page(request, cv_id: str):
    """UI shell only. Existing M1/M2 APIs authorize and own all CV data."""
    return render(request, "m7_editor/editor.html", {"cv_id": cv_id})
