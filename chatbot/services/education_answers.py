"""Extract explicit academic facts before treating an answer as a scalar value."""
import re

MONTHS = {name: index for index, name in enumerate((
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december'), 1)}
MONTHS.update({name[:3]: index for name, index in list(MONTHS.items())})
MONTHS.update({'sept': 9, 'agust': 8})
_MONTH = '(?:' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?'
DATE = rf'(?:(?:19|20)\d{{2}}(?:-\d{{2}})?|{_MONTH}\s*(?:19|20)\d{{2}}|present|ongoing)'
_START = rf'\b(?:start(?:ing)?(?:\s+(?:date|year))?|started(?:\s+in)?|from|since)\s*[:=]?\s*(?P<date>{DATE})(?!\w)'
_END = rf'\b(?:end(?:ing)?(?:\s+(?:date|year))?|(?:expected\s+)?(?:graduation(?:\s+(?:date|year))?|graduated|graduate|completed)(?:\s+(?:in|on))?|to|until)\s*[:=]?\s*(?P<date>{DATE})(?!\w)'
_RANGE = rf'(?P<start>{DATE})\s*(?:–|—|-|to|until)\s*(?P<end>{DATE})(?!\w)'
_QUALIFICATION = (
    r"(?:bachelor(?:'s)?(?:\s+of\s+(?:science|arts|engineering|technology))?|"
    r"master(?:'s)?(?:\s+of\s+(?:science|arts|engineering|technology))?|"
    r'b\.?s\.?c\.?|b\.?s\.?|b\.?a\.?|b\.?e\.?|b\.?tech\.?|'
    r'm\.?s\.?c\.?|m\.?s\.?|m\.?a\.?|m\.?e\.?|m\.?tech\.?|'
    r'ph\.?d\.?|mba|bba|diploma|associate(?:\s+degree)?)')
_PREFIX = re.compile(r"^(?:(?:i\s+(?:have\s+|am\s+)?|i'm\s+)?(?:completed|finished|earned|hold|studying|pursuing|graduated with)(?:\s+(?:a|an|my))?\s+|(?:my\s+)?degree\s*(?:is\s+|:\s*))", re.I)


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
    if 'end_date' not in values and re.match(r'^i\s+(?:have\s+)?(?:completed|earned|finished)\b', text, re.I):
        completion = re.search(r'\bin\s+(?P<date>' + DATE + r')[.!]?$', text, re.I)
        if completion:
            values['end_date'] = normalise_date(completion['date'])
            spans.append(completion.span())
    if not values and field in ('start_date', 'end_date') and re.fullmatch(DATE + r'[.!]?', text, re.I):
        values[field] = normalise_date(text)
        spans.append((0, len(text)))
    return values, spans


def parse_education(text, field=None):
    """Return only stated facts; ambiguous multi-entry prose stays with the provider."""
    text = ' '.join(text.strip().split()).rstrip('.!')
    dates, spans = education_dates(text, field)
    # Remove recognized date clauses before finding the degree/university boundary.
    head = text[:min(start for start, _ in spans)].rstrip(' ,;:-') if spans else text
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
        subject = re.sub(r'^in\s+', '', parts[0], flags=re.I).strip(' ,;')
        if subject and not re.fullmatch(r"[\w &'’()./\-]+", subject):
            return None
        degree = (match['qualification'] + (' ' + parts[0] if parts[0] else '')).strip()
        result = {'degree': degree, **dates}
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
    match = re.fullmatch(r'(?P<name>.+?)\s*[,;]?\s+(?:issue(?:d)?(?:\s+date)?|date)\s*[:=]?\s*(?P<date>' + DATE + r')[.!]?', text.strip(), re.I)
    if match:
        return {'name': match['name'].strip(' ,;'), 'date': normalise_date(match['date'])}
    return None


def parse_employer(text):
    match = re.fullmatch(r"(?:(?:i\s+(?:am|was|work|worked)(?:\s+as)?|i'm)\s+(?:a\s+)?)?(.+?)\s+at\s+(.+?)[.!]?", text, re.I)
    if match and re.search(r'\b(?:developer|engineer|intern|designer|manager|analyst|teacher|accountant|consultant|officer)\b', match[1], re.I):
        if not re.search(r'[;?]|\band\b', text, re.I):
            return {'role': match[1], 'company': match[2]}
    return None
