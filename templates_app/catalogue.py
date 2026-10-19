"""M3's curated design metadata. CV data and persistence stay in M10 and M2."""
import json
import re
from functools import lru_cache
from pathlib import Path
from django.template.loader import get_template
from django.template import TemplateDoesNotExist

FEATURED = ('modern_horizon', 'professional_meridian', 'creative_studio', 'ats_standard',
            'simple_direct', 'minimalist_space', 'executive_boardroom', 'modern_current',
            'modern_vector', 'creative_folio', 'professional_blue', 'simple_study')

CATEGORIES = {'modern': 'Modern', 'professional': 'Professional', 'simple': 'Simple',
              'creative': 'Creative', 'ats': 'ATS-Friendly', 'minimalist': 'Minimalist', 'executive': 'Executive'}

@lru_cache(maxsize=1)
def catalogue():
    return {row['id']: row for row in json.loads(Path(__file__).with_name('catalogue.json').read_text())}


def definition(template):
    row = catalogue().get(template.pk)
    # An administrator's custom renderer must not be silently replaced.
    return row if row and row['template_path'] == template.template_path else None


def is_renderable(template):
    path = template.template_path
    if not isinstance(path, str) or not re.fullmatch(r'cv_templates/[A-Za-z0-9_-]+\.html', path):
        return False
    if path == 'cv_templates/designed.html' and definition(template) is None:
        return False
    if path.rsplit('/', 1)[-1] in ('base.html',):
        return False
    try:
        get_template(path)
    except TemplateDoesNotExist:
        return False
    return True
