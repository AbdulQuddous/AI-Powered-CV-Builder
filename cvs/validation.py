import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from rest_framework.exceptions import ValidationError
SHARED = Path(__file__).resolve().parent.parent / 'shared'
META_FIELDS = ('target_role','career_level','template_id')

@lru_cache(maxsize=1)
def validator():
    schema = json.loads((SHARED/'schemas/cv_schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def validate_document(data):
    errors = list(validator().iter_errors(data))
    if errors:
        raise ValidationError({'data': [
            {'path':'/'.join(map(str,e.absolute_path)) or '$', 'message':e.message}
            for e in errors[:20]]})
    # Cross-field rules belong to M2, not shared contracts.
    for section in ('experience','education'):
        for i, item in enumerate(data[section]):
            start, end = item['start_date'], item['end_date']
            if start and end and start > end:
                raise ValidationError({'data':[f'{section}/{i}: end_date precedes start_date.']})
            if item.get('is_current') and end:
                raise ValidationError({'data':[f'{section}/{i}: current work must have empty end_date.']})
    if len(json.dumps(data, ensure_ascii=False).encode('utf-8')) > 1_000_000:
        raise ValidationError({'data':['CV document exceeds 1 MB.']})
    return data

def build_document(values, current=None):
    if 'data' in values:
        data = deepcopy(values['data'])
        if current is None and data == {}:
            data = json.loads((SHARED/'examples/cv_draft.json').read_text())
        # Full replacement data must already satisfy M10; no silent partial merges.
        validate_document(data)
    elif current is not None:
        data = deepcopy(current)
    else:
        data = json.loads((SHARED/'examples/cv_draft.json').read_text())
    for key in META_FIELDS:
        if key in values:
            # An explicitly populated conflicting meta value is a client error.
            if 'data' in values and data['meta'][key] not in ('', values[key]):
                raise ValidationError({key:['Conflicts with data.meta.' ]})
            data['meta'][key] = values[key]
    validate_document(data)
    if data['meta']['template_id']:
        from templates_app.services import TemplateService
        if not TemplateService.template_exists(data['meta']['template_id']):
            raise ValidationError({'template_id': ['The selected template does not exist or is unavailable.']})
    return data
