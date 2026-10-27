"""Small, explicit interview answers that do not need model interpretation."""
import re

PROFICIENCIES = 'basic|conversational|professional|fluent|native'
# Only split unpunctuated lists when every word belongs to a known language.
# Unknown and compound names are retained intact rather than guessed apart.
LANGUAGES = (
    'American Sign Language', 'British Sign Language', 'Brazilian Portuguese',
    'Mandarin Chinese', 'Scottish Gaelic', 'English', 'Urdu', 'Hindi', 'Punjabi',
    'Pashto', 'Sindhi', 'Balochi', 'Saraiki', 'Hindko', 'Hindku', 'Arabic', 'French', 'German',
    'Spanish', 'Portuguese', 'Italian', 'Chinese', 'Mandarin', 'Cantonese',
    'Japanese', 'Korean', 'Russian', 'Turkish', 'Persian', 'Farsi', 'Bengali',
    'Tamil', 'Telugu', 'Malayalam', 'Marathi', 'Gujarati', 'Nepali', 'Dutch',
    'Polish', 'Ukrainian', 'Swedish', 'Norwegian', 'Danish', 'Finnish', 'Greek',
    'Hebrew', 'Indonesian', 'Malay', 'Vietnamese', 'Thai', 'Swahili', 'Afrikaans',
)
_LANGUAGE = re.compile(r'(?:' + '|'.join(re.escape(v) for v in sorted(LANGUAGES, key=len, reverse=True)) + r')\b', re.I)
_CANONICAL = {v.casefold(): v for v in LANGUAGES}
_UNSPECIFIED = r'(?:(?:keep|leave)(?:\s+(?:these|them|it|all|the languages|languages|language proficiency|proficiency))?(?:\s+as)?\s+unspecified|(?:keep|leave)\s+it\s+blank|(?:no|without)\s+proficiency|unspecified)'
_UNCHANGED = r'(?:keep\s+(?:as\s+it|it\s+as\s+(?:it\s+is|is)|as\s+is)|leave\s+(?:it\s+)?as\s+is)'


def proficiency_unspecified(text):
    return bool(re.fullmatch(_UNSPECIFIED + r'[.!]?', text.strip(), re.I))


def keep_languages_unchanged(text):
    return bool(re.fullmatch(_UNCHANGED + r'[.!]?', text.strip(), re.I))


def labelled_summary(text):
    """Return (summary, explicit unspecified choice), or None for ordinary prose."""
    match = re.fullmatch(r'(?:(?P<choice>' + _UNSPECIFIED + r')\s*(?:[,;.]\s*|\s+and\s+))?'
                         r'(?:(?:my|the|professional|my professional)\s+)?summary\s*(?:is\s+|[:=]\s*)(?P<body>.+)',
                         text.strip(), re.I | re.S)
    return (match['body'].strip(), bool(match['choice'])) if match else None


def parse_languages(text):
    if proficiency_unspecified(text) or keep_languages_unchanged(text):
        return []
    entries = []
    for value in re.split(r'[,;\n]|\band\b', text.strip().rstrip('.'), flags=re.I):
        value = value.strip()
        if not value:
            continue
        matches = list(_LANGUAGE.finditer(value))
        remaining = _LANGUAGE.sub('', value).strip()
        # Plain space-separated known names, including complete compound names.
        if matches and not remaining:
            entries.extend({'name': _CANONICAL[m[0].casefold()]} for m in matches)
            continue
        match = re.fullmatch(r'(.+?)\s+(' + PROFICIENCIES + r')', value, re.I)
        name = match[1].strip() if match else value
        entry = {'name': _CANONICAL.get(name.casefold(), name)}
        if match:
            entry['proficiency'] = match[2].casefold()
        entries.append(entry)
    return entries


def structured_section_answer(text, section):
    """Convert explicit list values to interview fields before scalar splitting."""
    from chatbot.services.structured_answers import section_list
    values = section_list(text, section)
    if not values:
        return None
    if section == 'achievements':
        return [value.strip() for value in values] if all(isinstance(value, str) and value.strip() for value in values) else None
    fields = {'certifications': {'name', 'issuer', 'date', 'url'},
              'languages': {'name', 'proficiency'}}[section]
    entries = []
    for value in values:
        if isinstance(value, str) and value.strip():
            if section == 'languages':
                names = parse_languages(value)
                if not names:
                    return None
                entries.extend(names)
                continue
            value = {'name': value.strip()}
        if not isinstance(value, dict) or not value.get('name') or set(value) - fields:
            return None
        if not all(isinstance(item, str) for item in value.values()):
            return None
        if section == 'languages' and (proficiency_unspecified(value['name']) or keep_languages_unchanged(value['name'])):
            return None
        entries.append({key: item.strip() for key, item in value.items()})
    return entries


def work_presence_answer(text):
    """Recognize a fact-free acknowledgment; an employer/title still needs collecting."""
    match = re.fullmatch(
        r'(?:yes[,\s]+)?(?:i\s+)?(?:have(?:\s+(?:completed|finished))?|completed|finished|did)'
        r'(?:\s+(?:a|an|my|some))?\s+(?P<kind>[a-z]+(?:\s+[a-z]+)?)[.!]?', text.strip(), re.I)
    if not match:
        return False
    kind = ' '.join(match['kind'].casefold().split())
    from chatbot.services.local_extractor import _one_typing_error
    return (kind in ('work experience', 'professional experience', 'freelance work', 'volunteer work')
            or _one_typing_error(kind, 'internship'))


def section_request(text):
    """Match fact-free commands, allowing one typo in a known section noun."""
    match = re.fullmatch(
        r'(?:(?:(?:i )?(?:want|wan|would like) to|can i|could i|please)\s+)?'
        r'(?P<verb>add|edit|update)(?:\s+(?:my|a new|a|an|another|new|more))?\s+'
        r'(?P<noun>[a-z]+)'
        r'(?:\s+to (?:my |the )?(?:cv|resume))?[.!?]?', text.strip(), re.I)
    if not match:
        return None
    noun = match['noun'].casefold()
    nouns = {
        'certificate': 'certifications', 'certificates': 'certifications',
        'certification': 'certifications', 'certifications': 'certifications',
        'language': 'languages', 'languages': 'languages', 'skill': 'skills', 'skills': 'skills',
        'education': 'education', 'degree': 'education', 'degrees': 'education',
        'experience': 'experience', 'job': 'experience', 'jobs': 'experience',
        'project': 'projects', 'projects': 'projects', 'summary': 'summary',
        'achievement': 'achievements', 'achievements': 'achievements',
    }
    section = nouns.get(noun)
    if section is None and len(noun) >= 5:
        from chatbot.services.local_extractor import _one_typing_error
        # Only the command noun is compared; names and factual prose stay intact.
        candidates = {target for known, target in nouns.items()
                      if len(known) >= 5 and _one_typing_error(noun, known)}
        if len(candidates) == 1:
            section = candidates.pop()
    if section is None:
        return None
    return section, 'add' if match['verb'].casefold() == 'add' else 'edit'
