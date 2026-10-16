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


def proficiency_unspecified(text):
    return bool(re.fullmatch(_UNSPECIFIED + r'[.!]?', text.strip(), re.I))


def labelled_summary(text):
    """Return (summary, explicit unspecified choice), or None for ordinary prose."""
    match = re.fullmatch(r'(?:(?P<choice>' + _UNSPECIFIED + r')\s*(?:[,;.]\s*|\s+and\s+))?'
                         r'(?:(?:my|the|professional|my professional)\s+)?summary\s*(?:is\s+|[:=]\s*)(?P<body>.+)',
                         text.strip(), re.I | re.S)
    return (match['body'].strip(), bool(match['choice'])) if match else None


def parse_languages(text):
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


def section_request(text):
    """Match a request with no facts; never mistake certificate content for a command."""
    match = re.fullmatch(
        r'(?:(?:i (?:want|wan|would like) to|can i|could i|please)\s+)?'
        r'(?P<verb>add|edit|update)(?:\s+(?:my|a new|a|an|another|new))?\s+'
        r'(?P<noun>certificates?|certifications?|cetificates?|languages?|skills?|education|degrees?|experience|jobs?|projects?|summary|achievements?)'
        r'(?:\s+to (?:my |the )?(?:cv|resume))?[.!?]?', text.strip(), re.I)
    if not match:
        return None
    noun = match['noun'].casefold()
    section = next((target for stem, target in (
        ('cert', 'certifications'), ('cetif', 'certifications'), ('language', 'languages'),
        ('skill', 'skills'), ('degree', 'education'), ('job', 'experience'),
        ('project', 'projects'), ('achievement', 'achievements')) if noun.startswith(stem)), noun)
    return section, 'add' if match['verb'].casefold() == 'add' else 'edit'
