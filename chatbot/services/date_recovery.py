"""Recover two proven date mistakes in unsaved, single-qualification interviews."""
import re

from chatbot.services.education_answers import parse_education, reversed_date_range


def date_repair_candidate(state):
    entries = (state.get('collected_data') or {}).get('education') or []
    if len(entries) != 1 or not isinstance(entries[0], dict):
        return False
    entry = entries[0]
    return bool(state.get('date_confirmation_pending', {}).get('section') == 'education' or (
        entry.get('start_date') == entry.get('end_date') and re.fullmatch(r'(?:19|20)\d{2}', str(entry.get('start_date', '')))))


def _same(left, right):
    return ' '.join(str(left).casefold().split()) == ' '.join(str(right).casefold().split())


def repair_date_state(state, history):
    """Require paired user/accepted-assistant evidence; never infer missing dates.

    Later accepted corrections win. Multiple qualifications and unsupported
    history remain unchanged so a source date cannot attach to the wrong entry.
    """
    if not date_repair_candidate(state):
        return False
    entry = state['collected_data']['education'][0]
    pairs, source = [], None
    for message in history:
        if message['role'] == 'user':
            source = message['content']
            if re.search(r'\b(?:add|another|second|new)\b.*\b(?:education|degree|university|qualification)\b', source, re.I):
                return False
        elif source is not None:
            updates = (message.get('cv_updates') or {}).get('education') or []
            if len(updates) > 1:
                return False
            if message.get('intent') != 'irrelevant':
                pairs.append((source, updates[0] if updates and isinstance(updates[0], dict) else {}))
            source = None
    changed = False
    for position, (source, accepted) in enumerate(pairs):
        parsed = parse_education(source)
        if not parsed:
            continue
        # Every identifying label in the accepted proposal must still match.
        if any(accepted.get(key) and not _same(accepted[key], entry.get(key, '')) for key in ('degree', 'institution')):
            continue
        later = [item for _, item in pairs[position + 1:]]
        later_sources = [text for text, _ in pairs[position + 1:]]
        # Unaccepted later corrections and omission requests still express user
        # intent; do not restore an older answer over them.
        if any(re.fullmatch(r'(?:omit(?: this date| date)?|skip(?: this date)?|leave it blank)[.!]?', text.strip(), re.I)
               or re.search(r'\b(?:not|never|wrong|incorrect|change|correct|update|edit)\b.*\b(?:date|graduat\w*|education|degree|university)\b', text, re.I)
               for text in later_sources):
            continue
        completion = parsed.get('end_date', '')
        if (parsed.get('degree') and parsed.get('institution') and not parsed.get('start_date')
                and _same(parsed['degree'], entry.get('degree', ''))
                and _same(parsed['institution'], entry.get('institution', ''))
                and re.fullmatch(r'(?:19|20)\d{2}', completion)
                and accepted.get('start_date') == completion and accepted.get('end_date') == completion
                and entry.get('start_date') == completion and not any(item.get('start_date') for item in later)
                and not any(re.fullmatch(r'(?:19|20)\d{2}(?:-\d{2})?[.!]?', text.strip()) for text in later_sources)):
            # The one completion year was incorrectly duplicated as a start year.
            entry.pop('start_date', None)
            changed = True
        start, end = parsed.get('start_date', ''), parsed.get('end_date', '')
        if not (re.fullmatch(r'(?:19|20)\d{2}-(?:0[1-9]|1[0-2])', start)
                and re.fullmatch(r'(?:19|20)\d{2}-(?:0[1-9]|1[0-2])', end)) or reversed_date_range(start, end):
            continue
        # The old precision prompt accepted only one endpoint of a labelled pair.
        if not any(accepted.get(key) == parsed[key] for key in ('start_date', 'end_date')):
            continue
        for key in ('start_date', 'end_date'):
            value = parsed[key]
            if accepted.get(key) == value or any(item.get(key) for item in later):
                continue
            if any((parse_education(text) or {}).get(key) not in (None, '', value) for text in later_sources):
                continue
            if entry.get(key) not in (None, '', value[:4]):
                continue
            other = 'end_date' if key == 'start_date' else 'start_date'
            if entry.get(other) != parsed[other]:
                continue
            entry[key] = value
            changed = True
    if not changed:
        return False
    pending = state.get('date_confirmation_pending') or {}
    field = pending.get('field')
    if pending.get('section') == 'education' and field and (
            not entry.get(field) or re.fullmatch(r'(?:19|20)\d{2}-(?:0[1-9]|1[0-2])', str(entry[field]))):
        state.pop('date_confirmation_pending', None)
    focus = state.get('pending_field') or {}
    if focus.get('section') == 'education' and focus.get('field') in ('start_date', 'end_date'):
        state.pop('pending_field', None)
    for key in ('start_date', 'end_date'):
        state.setdefault('education_fields', {})[key] = 'collected' if entry.get(key) else 'missing'
        statuses = state.setdefault('field_status', {})
        statuses.pop(f'education.0.{key}', None)
        if entry.get(key):
            statuses[f'education.0.{key}'] = 'answered'
    state['invalid_fields'] = [path for path, status in state.get('field_status', {}).items() if status == 'invalid']
    state.pop('approved_review_changes', None)
    state.pop('review_decisions', None)
    return True
