"""Conservative evidence checks for literal facts returned by local extraction.

Descriptions still require user review; this guard rejects unsupported identity,
contact, skill and numerical facts rather than attempting semantic fact proving.
"""
import re
from copy import deepcopy

from chatbot.services.field_validation import ALIASES
from chatbot.services.education_answers import education_dates, structured_education


def comparable(text):
    return ' '.join(str(text).casefold().split())


def mentioned(value, message):
    value, message = comparable(value), comparable(message)
    if value in message:
        return True
    return any(value == comparable(canonical) and re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', message)
               for alias, canonical in ALIASES.items())


def guard_extraction(response, message, state):
    result = deepcopy(response)
    unsupported = []
    context = state.get('collected_data') or state.get('edit_updates') or {}
    existing = state.get('existing_cv') or {}
    # A completion date is not evidence of a start date just because the same
    # year appears in the answer. Check labelled endpoints independently.
    stated_education = structured_education(message) or education_dates(message)[0]
    literal = {'personal': {'full_name', 'email', 'phone', 'location', 'linkedin', 'github', 'portfolio'},
               'education': {'institution', 'degree', 'field_of_study', 'grade'},
               'experience': {'company', 'role', 'job_title', 'technologies', 'employment_type'},
               'projects': {'name', 'technologies', 'url'}, 'certifications': {'name', 'issuer', 'url'},
               'languages': {'name', 'proficiency'}}
    def contextual(section, field, value):
        # Existing entry identities may be needed to identify an anonymous correction.
        if field not in ('name', 'company', 'role', 'job_title', 'institution', 'degree'):
            return False
        for entry in (context.get(section) or []) + (existing.get(section) or []):
            if isinstance(entry, dict) and comparable(entry.get(field, '')) == comparable(value):
                return True
        return False
    for section, updates in result.get('cv_updates', {}).items():
        if not updates:
            continue
        if section == 'skills':
            supported = [skill for skill in updates if mentioned(skill, message)]
            if len(supported) != len(updates): unsupported.append('skills')
            result['cv_updates'][section] = supported or None
            continue
        entries = [updates] if isinstance(updates, dict) else updates if isinstance(updates, list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for field, value in list(entry.items()):
                if not value:
                    continue
                if section == 'personal' and not mentioned(value, message):
                    accepted_personal = {**(existing.get('personal') or {}), **(context.get('personal') or {})}
                    if comparable(accepted_personal.get(field, '')) == comparable(value):
                        entry.pop(field)
                        continue
                if section == 'projects' and field == 'name':
                    from chatbot.services.project_answers import is_profile_paragraph
                    if is_profile_paragraph(message) and not contextual(section, field, value):
                        entry.pop(field)
                        unsupported.append('projects.name (please provide a project title separately from your profile)')
                        continue
                if section == 'projects' and field == 'name' and re.fullmatch(
                        r'(?:a |an )?(?:django|python|react|javascript|web|mobile) (?:project|app|application)', str(value), re.I
                ) and not re.search(r'\b(?:called|named|title)\b', message, re.I):
                    entry.pop(field)
                    unsupported.append('projects.name (please confirm the actual title)')
                    continue
                if field in literal.get(section, set()):
                    values = value if isinstance(value, list) else [value]
                    supported = [v for v in values if mentioned(v, message) or contextual(section, field, v)]
                    if len(supported) != len(values):
                        unsupported.append(f'{section}.{field}')
                        if isinstance(value, list): entry[field] = supported or None
                        else: entry.pop(field)
                if (section == 'education' and field in ('start_date', 'end_date')
                        and any(key in stated_education for key in ('start_date', 'end_date'))
                        and field not in stated_education):
                    entry.pop(field, None)
                    unsupported.append(f'{section}.{field}')
                    continue
                if field in ('start_date', 'end_date', 'date') and re.match(r'^\d{4}', str(value)) and str(value)[:4] not in message:
                    entry.pop(field, None)
                    unsupported.append(f'{section}.{field}')
                    continue
                if field in ('start_date', 'end_date', 'date') and re.fullmatch(r'\d{4}-\d{2}', str(value)):
                    year, month = value.split('-')
                    month_words = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december')
                    if 1 <= int(month) <= 12 and year in message and value not in message and not any(word in message.lower() for word in (month_words[int(month)-1], month_words[int(month)-1][:3])):
                        entry[field] = year
                        unsupported.append(f'{section}.{field} month')
    if unsupported:
        warning = ('Let’s fill in only the education details you know.'
                   if all(field.startswith('education.') for field in unsupported) else
                   'Please confirm extracted details that were not explicit in your answer: ' + ', '.join(dict.fromkeys(unsupported)) + '.')
        result.setdefault('_control', {})['evidence_warning'] = warning
    return result
