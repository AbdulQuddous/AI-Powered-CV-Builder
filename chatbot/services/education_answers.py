"""Extract explicit academic facts before treating an answer as a scalar value."""
import re

from chatbot.services.structured_answers import looks_structured, parse_structured

MONTHS = {name: index for index, name in enumerate((
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december'), 1)}
MONTHS.update({name[:3]: index for name, index in list(MONTHS.items())})
MONTHS.update({'sept': 9, 'agust': 8})
_MONTH = '(?:' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?'
DATE = rf'(?:(?:19|20)\d{{2}}(?:-\d{{2}})?|{_MONTH}\s*(?:19|20)\d{{2}}|present|ongoing)'
_START = rf'\b(?:start(?:ing)?(?:\s+(?:date|year))?|started(?:\s+in)?|from|since)\s*[:=]?\s*(?P<date>{DATE})(?!\w)'
_COMPLETED = r'(?:completed|sompleted)'
_EXPECT = r'(?:expect|excpect)(?:ed|ing)?'
_GRADUATION = rf'(?:(?:i\s+(?:am\s+|have\s+)?)?(?:(?:{_EXPECT}(?:\s+to)?|will)\s+(?:graduate|finish|complete|end)|(?:expected\s+)?(?:graduation(?:\s+(?:date|year))?|graduated|graduate|graduted|{_COMPLETED})))'
_END = rf'\b(?:end(?:ing)?(?:\s+(?:date|year))?|{_GRADUATION}|to|until)(?:\s+(?:in|on|is|will\s+be))?\s*[:=]?\s*(?P<date>{DATE})(?!\w)'
_RANGE = rf'(?P<start>{DATE})\s*(?:–|—|-|to|until)\s*(?P<end>{DATE})(?!\w)'
_QUALIFICATION = (
    r"(?:bachelor(?:'s)?(?:\s+of\s+(?:science|arts|engineering|technology))?|"
    r"master(?:'s)?(?:\s+of\s+(?:science|arts|engineering|technology))?|"
    r'b\.?s\.?c\.?|b\.?s\.?|b\.?a\.?|b\.?e\.?|b\.?tech\.?|'
    r'm\.?s\.?c\.?|m\.?s\.?|m\.?a\.?|m\.?e\.?|m\.?tech\.?|'
    r'ph\.?d\.?|mba|bba|diploma|associate(?:\s+degree)?)')
_PREFIX = re.compile(r"^(?:(?:i\s+(?:have\s+|am\s+)?|i'm\s+)?(?:(?:currently|still)\s+)?(?:" + _COMPLETED + r"|finished|earned|hold|studying|pursuing|enrolled|graduated with)(?:\s+(?:a|an|my|in))?\s+|(?:my\s+)?degree\s*(?:is\s+|:\s*))", re.I)
_STUDYING = r"(?:(?:i\s+am|i'm)\s+)?(?:(?:currently|still)\s+)?(?:studying|pursuing|enrolled|a student)"


def active_education(state):
    """Use only an unambiguous active entry to personalize follow-up questions."""
    pending = state.get('pending_entry') or {}
    if pending.get('section') == 'education':
        return pending.get('draft') or {}
    focus = state.get('pending_field') or {}
    if focus.get('section') == 'education' and type(focus.get('index')) is int:
        source = 'existing_cv' if state.get('mode') == 'edit_existing' else 'collected_data'
        entries = (state.get(source) or {}).get('education') or []
        if 0 <= focus['index'] < len(entries):
            return entries[focus['index']]
    if state.get('edit_focus') == 'education' and state.get('edit_draft'):
        return state['edit_draft'][-1]
    entries = (state.get('collected_data') or {}).get('education') or []
    return entries[0] if len(entries) == 1 else {}


def reversed_date_range(start, end):
    """Reject only definite inversions; a year denotes an unknown month in it."""
    pattern = r'(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?'
    if not (isinstance(start, str) and isinstance(end, str)
            and re.fullmatch(pattern, start) and re.fullmatch(pattern, end)):
        return False
    earliest_start = start + '-01' if len(start) == 4 else start
    latest_end = end + '-12' if len(end) == 4 else end
    return earliest_start > latest_end


def normalise_date(value):
    value = value.strip().rstrip('.').lower()
    if value in ('present', 'ongoing'):
        return 'present'
    match = re.fullmatch(r'(' + _MONTH + r')\s*((?:19|20)\d{2})', value, re.I)
    if match:
        return f"{match[2]}-{MONTHS[match[1].rstrip('.').lower()]:02d}"
    return value


def education_dates(text, field=None):
    values, spans = {}, []
    match = re.search(_RANGE, text, re.I)
    if match:
        values.update(start_date=normalise_date(match['start']), end_date=normalise_date(match['end']))
        spans.append(match.span())
    for key, pattern in [('start_date', _START), ('end_date', _END)]:
        match = re.search(pattern, text, re.I)
        if match:
            value = normalise_date(match['date'])
            if key in values and values[key] != value:
                return {}, []  # Conflicting clauses require interpretation/clarification.
            values[key] = value
            spans.append(match.span())
    if 'end_date' not in values and re.match(r'^i\s+(?:have\s+)?(?:' + _COMPLETED + r'|earned|finished)\b', text, re.I):
        completion = re.search(r'\bin\s+(?P<date>' + DATE + r')[.!]?$', text, re.I)
        if completion:
            values['end_date'] = normalise_date(completion['date'])
            spans.append(completion.span())
    if not values and field in ('start_date', 'end_date') and re.fullmatch(DATE + r'[.!]?', text, re.I):
        values[field] = normalise_date(text)
        spans.append((0, len(text)))
    return values, spans


_EDUCATION_ALIASES = {
    'institution': 'institution', 'university': 'institution', 'degree': 'degree',
    'field_of_study': 'field_of_study', 'specialization': 'field_of_study',
    'start_date': 'start_date', 'start_year': 'start_date',
    'end_date': 'end_date', 'graduation_date': 'end_date', 'graduation_year': 'end_date',
    'grade': 'grade', 'is_current': 'is_current',
}


def structured_education(text):
    """Normalize explicit labels, preserving year-only values and stated specialization."""
    value = parse_structured(text)
    if not isinstance(value, dict) or not value:
        return None
    if set(value) == {'education'}:
        value = value['education']
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
    if not isinstance(value, dict) or not value or set(value) - set(_EDUCATION_ALIASES):
        return None
    result = {}
    for key, raw in value.items():
        field = _EDUCATION_ALIASES[key]
        if field == 'is_current':
            if type(raw) is not bool:
                return None
        elif isinstance(raw, int) and not isinstance(raw, bool) and field in ('start_date', 'end_date'):
            raw = str(raw)
        elif not isinstance(raw, str):
            return None
        if isinstance(raw, str):
            raw = raw.strip()
            if field in ('start_date', 'end_date'):
                raw = normalise_date(raw)
        if field in result and result[field] != raw:
            return None  # Conflicting aliases must be clarified, never silently overwritten.
        result[field] = raw
    degree = result.get('degree')
    if degree and 'field_of_study' not in result:
        parsed = parse_education(degree)
        if parsed and parsed.get('field_of_study'):
            result['field_of_study'] = parsed['field_of_study']
    return result


def parse_education(text, field=None):
    """Return only stated facts; ambiguous multi-entry prose stays with the provider."""
    if looks_structured(text):
        return structured_education(text)
    text = ' '.join(text.strip().split()).rstrip('.!')
    if re.fullmatch(_STUDYING + r'(?:\s+(?:right now|at university|at college))?', text, re.I):
        return {'is_current': True}
    studying = bool(re.match(_STUDYING + r'\s+', text, re.I))
    # Accept an explicitly labelled graduation value even with a missing leading
    # quote/g from a pasted fragment. This never treats arbitrary prose as a date.
    labelled_date = re.fullmatch(r'["\']?(?:g?raduation[_ ](?:year|date)|end_date)["\']?\s*:\s*["\']?(' + DATE + r')["\']?', text, re.I)
    if labelled_date and field == 'end_date':
        return {'end_date': normalise_date(labelled_date[1])}
    dates, spans = education_dates(text, field)
    # Remove recognized date clauses before finding the degree/university boundary.
    head = text[:min(start for start, _ in spans)].rstrip(' ,;:.!-') if spans else text
    head = re.sub(r'\b(?:from|in)\s*$', '', head, flags=re.I).rstrip(' ,;')
    degree_text = _PREFIX.sub('', head)
    # Informal answers such as "i bs software engineering from ..." still state a
    # qualification explicitly. The qualification match below bounds this prefix.
    degree_text = re.sub(r"^(?:i(?:\s+am|'m)?(?:\s+have)?\s+(?:(?:a|an|my)\s+)?)", '', degree_text, flags=re.I)
    match = re.fullmatch(r'(?P<qualification>' + _QUALIFICATION + r')(?=\s|$)(?P<rest>.*)', degree_text, re.I)
    if match:
        rest = match['rest'].strip()
        if re.search(r'\b(?:and|but|not|because|then)\b', rest, re.I):
            return None
        parts = re.split(r'(?:^|\s+)(?:from|at)\s+', rest, maxsplit=1, flags=re.I)
        # "degree" is an answer descriptor, not part of the subject. Bound the
        # correction to this suffix rather than spellchecking academic names.
        parts[0] = re.sub(r'\s*\b(?:degree|degrre)\s*$', '', parts[0], flags=re.I).strip()
        subject = re.sub(r'^in\s+', '', parts[0], flags=re.I).strip(' ,;')
        if subject and not re.fullmatch(r"[\w &'’()./\-]+", subject):
            return None
        degree = (match['qualification'] + (' ' + parts[0] if parts[0] else '')).strip()
        result = {'degree': degree, **dates}
        if studying:
            result['is_current'] = True
        if subject:
            result['field_of_study'] = subject
        if len(parts) == 2 and parts[1].strip(' ,;'):
            result['institution'] = parts[1].strip(' ,;')
        return result
    university = re.fullmatch(r"(?:(?:my\s+)?(?:university|institution|college)\s*(?:is\s+|:\s*)|i\s+(?:studied|study|graduated)\s+(?:at|from)\s+)(.+)", head, re.I)
    if university:
        return {'institution': university[1], **dates}
    if re.match(r'^(?:university|college|institute|school)\b', head, re.I):
        return {'institution': head, **dates}
    if dates:
        # Date answers are useful even when the last question asked for the university.
        # Do not promote unrelated surrounding prose to academic facts.
        remainder = text
        for start, end in sorted(spans, reverse=True):
            remainder = remainder[:start] + ' ' * (end - start) + remainder[end:]
        remainder = re.sub(r'\b(?:i|am|have|and|in|on|from|my|expected|date|year)\b', '', remainder, flags=re.I)
        if not remainder.strip(' ,;:.!-–—'):
            return dates
    return None


def parse_certificate(text):
    labelled = re.fullmatch(r'(?:certification|certificate)(?:\s+(?:title|name))?\s*(?::|=|\bis\b)\s*(.+)', text.strip(), re.I)
    body = labelled[1] if labelled else text.strip()
    details = {}
    match = re.fullmatch(r'(?P<name>.+?)\s*[,;]?\s+(?:issue(?:d)?(?:\s+date)?|date)\s*[:=]?\s*(?P<date>' + DATE + r')[.!]?', body, re.I)
    if match:
        body = match['name'].strip(' ,;')
        details['date'] = normalise_date(match['date'])
    issuer = re.fullmatch(r'(.+?)\s*(?:[;|—–]|\s+-)\s*issuer\s*[:=]\s*(.+)', body, re.I)
    if not issuer and labelled:
        issuer = re.fullmatch(r'(.+?)\s+[—–]\s+(.+)', body)
    if not issuer:
        issuer = re.fullmatch(r'(.+?)\s+(?:issued by|issuer\s*[:=])\s*(.+)', body, re.I)
    if issuer:
        return {'name': issuer[1].strip(), 'issuer': issuer[2].strip(), **details}
    if labelled or details:
        return {'name': body.strip(), **details}
    return None


def parse_employer(text):
    prefix = (r"(?:(?:i\s+(?:am|was|work|worked)(?:\s+as)?|i'm)\s+(?:(?:a|an)\s+)?|"
              r"i\s+(?:have\s+)?(?:completed|finished|did)\s+(?:(?:a|an|my)\s+)?"
              r"(?:internship|intership)\s+as\s+(?:(?:a|an)\s+)?)?")
    match = re.fullmatch(prefix + r'(.+?)\s+at\s+(.+?)[.!]?', text, re.I)
    if match and re.search(r'\b(?:developer|engineer|intern|designer|manager|analyst|teacher|accountant|consultant|officer)\b', match[1], re.I):
        if not re.search(r'[;?]|\band\b', text, re.I) and not re.match(r'^(?:i|my)\b', match[1], re.I):
            return {'role': match[1], 'company': match[2]}
    return None
