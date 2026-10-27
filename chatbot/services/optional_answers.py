"""Clarify ambiguous optional entries before treating them as candidate facts.

This validates conversational intent, not whether a credential or language exists.
Unfamiliar names remain usable through explicit user confirmation.
"""
from copy import deepcopy
import re

from chatbot.services.section_answers import LANGUAGES

KNOWN_LANGUAGES = {name.casefold() for name in LANGUAGES}
_PROSE = re.compile(r"\b(?:i|my|you|your|am|are|going|went|travel|travelling|traveling|want|would|please|tomorrow|today)\b", re.I)
_CODE = re.compile(r'(?:[A-Z]{2,10}|[A-Z]{1,8}(?:[- ]\d{2,5})|[A-Z]{2,8}(?:[- ][A-Z0-9]{2,8}){1,3})')
_CREDENTIAL = re.compile(r'\b(?:certificate|certification|certified|diploma|specialization|qualification)\b', re.I)


def optional_chatter(text):
    """Obvious conversation/travel statements are not short optional field names."""
    value = text.strip().rstrip('.!')
    return bool(re.fullmatch(r'yes(?:,?\s+add\s+it)?|add it|confirm|confirmed|ok|okay|sure|thanks|thank you', value, re.I) or re.match(
        r"^(?:(?:i\s+(?:am|m|'m|will|want to)\s+)?(?:going|travell?ing|visiting)|are you|do you|can you)\b", value, re.I))


def clear_language(entry, message):
    name = entry.get('name', '').strip()
    if name.casefold() in KNOWN_LANGUAGES:
        return True
    # Explicit assertions allow uncommon/local/sign languages without a catalogue.
    return bool(re.search(r'\b(?:speak|read|write)\b|\blanguages?(?:\s+(?:is|are))?\s*:', message, re.I)) and not _PROSE.search(name)


def clear_certificate(entry, message=''):
    name = entry.get('name', '').strip()
    from chatbot.services.entity_validation import credential_code, entity_problem
    if not name or entity_problem('certifications', 'name', name, message):
        return False
    # Metadata supports an already plausible title; it never overrides a type error.
    if entry.get('issuer') or entry.get('url') or entry.get('date'):
        return True
    from chatbot.services.field_validation import extract_skills
    if (not _CREDENTIAL.search(name) and extract_skills(name)) or name.casefold() in {
            'google', 'microsoft', 'cisco', 'coursera', 'udemy', 'edx'}:
        return False
    if _CODE.fullmatch(name) or credential_code(name):
        return True
    if re.match(r'^(?:certification|certificate)(?:\s+(?:title|name))?\s*(?::|=|\bis\b)', message.strip(), re.I):
        return True
    subject = _CREDENTIAL.sub('', name).strip(' :-')
    if _CREDENTIAL.search(name) and subject and extract_skills(subject):
        return True
    return bool(_CREDENTIAL.search(name) and len(name.split()) >= 3 and not _PROSE.search(name))


def review_optional_entries(response, message, state):
    """Remove provisional names from updates; retain independently valid siblings."""
    result = deepcopy(response)
    if (result.get('_control') or {}).get('intent') == 'confirm_optional':
        return result, []
    from chatbot.services.structured_answers import looks_structured
    # Explicit structured fields already establish the user's naming intent.
    structured = looks_structured(message)
    for section in ('languages', 'certifications'):
        entries = (result.get('cv_updates') or {}).get(section) or []
        if not entries:
            continue
        if section == 'languages' and any(_PROSE.search(entry.get('name', '')) for entry in entries):
            result['cv_updates'][section] = None
            result['_control'] = {'intent': 'clarification',
                'notice': 'Please give a language name, such as English or Urdu, or say "cancel" to leave this step. I have not added a language.'}
            continue
        unclear = [entry for entry in entries if not (
            (structured or clear_language(entry, message)) if section == 'languages' else clear_certificate(entry, message))]
        if unclear:
            result['cv_updates'][section] = [entry for entry in entries if entry not in unclear] or None
            result['_control'] = {'intent': 'optional_confirmation', 'section': section, 'entries': unclear}
            return result, [f'{section}.{index}.name' for index, entry in enumerate(entries) if entry in unclear]
    return result, []


def confirmation_question(pending):
    titles = ', '.join('“' + entry.get('name', '')[:100] + '”' for entry in pending['entries'][:5])
    if pending['section'] == 'certifications':
        if not any(entry.get('name') for entry in pending['entries']):
            return ('Please provide the actual course or qualification title. '
                    'The issuer, date or link alone does not identify a certification. You can skip or cancel.')
        return (f'I need the full certification title for {titles}, and the issuer if available. '
                'For example: "Certification: Google AI Essentials — Google". '
                'A simple "yes" will not add it. You can provide the details, skip or cancel.')
    noun = 'language name' if pending['section'] == 'languages' else 'certification title'
    detail = 'the correct language name' if pending['section'] == 'languages' else 'the full title and issuer'
    return f'Is {titles} the {noun} you want to add? Reply "yes, add it", provide {detail}, or say "cancel". It has not been added yet.'
