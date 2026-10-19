"""Recover evidenced answer-boundary bugs in unsaved creation sessions."""
from copy import deepcopy
import re

from chatbot.services.section_answers import (labelled_summary, parse_languages,
    keep_languages_unchanged, proficiency_unspecified, structured_section_answer)
from chatbot.services.education_answers import parse_education
from chatbot.services.structured_answers import looks_structured
from chatbot.services.field_validation import unique_skills, extract_skills
from chatbot.services.date_recovery import date_repair_candidate, repair_date_state


def _misplaced_dates(data):
    entries = data.get('education') or []
    if len(entries) != 1 or not isinstance(entries[0], dict):
        return None
    value = entries[0].get('institution')
    dates = parse_education(value) if isinstance(value, str) else None
    if dates and set(dates) <= {'start_date', 'end_date'}:
        return dates
    return None


def _repair_education(state, user_answers, accepted_universities=()):
    from chatbot.services.state_manager import get_default_education_fields
    data = state.get('collected_data') or {}
    dates = _misplaced_dates(data)
    if not dates:
        return False
    entry = data['education'][0]
    if _normalise(entry['institution']) not in user_answers:
        return False
    universities = set()
    for text in user_answers.values():
        parsed = parse_education(text)
        if parsed and parsed.get('institution') and _normalise(parsed.get('degree', '')) == _normalise(entry.get('degree', '')):
            universities.add(parsed['institution'])
    explicit_source = bool(universities)
    # A later accepted university/correction may contradict the earlier grouped
    # answer. Ask again rather than restoring an older institution over that edit.
    universities.update(accepted_universities)
    correction_seen = any(re.search(r'\b(?:change|edit|update|correct)\b.*\b(?:university|institution|college)\b',
                                   text, re.I) for text in user_answers.values())
    # Exclude only the proven date-as-university value. Restore a university only
    # when its explicit degree answer identifies this single entry unambiguously.
    entry.pop('institution')
    if explicit_source and len({_normalise(value) for value in universities}) == 1 and not correction_seen:
        entry['institution'] = universities.pop()
    for key, value in dates.items():
        entry.setdefault(key, value)
    fields = get_default_education_fields()
    fields.update({key: 'collected' for key in fields if entry.get(key)})
    state['education_fields'] = fields
    completed = state.setdefault('completed_sections', [])
    required = ('degree', 'institution', 'field_of_study', 'end_date')
    if all(entry.get(key) for key in required):
        if 'education' not in completed:
            completed.append('education')
        state['missing_sections'] = [section for section in state.get('missing_sections', []) if section != 'education']
    else:
        state['completed_sections'] = [section for section in completed if section != 'education']
        if 'education' not in state.setdefault('missing_sections', []):
            state['missing_sections'].append('education')
    pending = state.get('pending_field') or {}
    if pending.get('section') == 'education' and entry.get(pending.get('field')):
        state.pop('pending_field', None)
    statuses = state.setdefault('field_status', {})
    for path in list(statuses):
        if path.startswith('education.'):
            statuses.pop(path)
    statuses.update({f'education.0.{key}': 'answered' for key in fields if entry.get(key)})
    return True


def _normalise(value):
    return ' '.join(value.casefold().split())


def _has_list_cleanup(data):
    return (any(isinstance(entry, dict) and (
                keep_languages_unchanged(entry.get('name', '')) or proficiency_unspecified(entry.get('name', '')))
                for entry in data.get('languages') or [])
            or any(isinstance(entry, dict) and looks_structured(entry.get('name', ''))
                   for entry in data.get('certifications') or [])
            or unique_skills(data.get('skills') or []) != (data.get('skills') or [])
            or any(isinstance(entry, dict) and re.search(r'\bdegrre$', entry.get('degree', ''), re.I)
                   for entry in data.get('education') or []))


def _repair_lists(data, user_answers):
    changed = False
    for section in ('certifications',):
        entries = data.get(section) or []
        for source in user_answers.values():
            clean = structured_section_answer(source, section)
            if not clean:
                continue
            # Match exactly the old comma-split proposal, including its JSON
            # wrapper. A later user edit or a different list is never replaced.
            legacy = [{'name': value.strip().rstrip('.')} for value in
                      re.split(r',|\band\b', ' '.join(source.split())) if value.strip()]
            for start in range(len(entries) - len(legacy) + 1):
                if entries[start:start + len(legacy)] == legacy and legacy != clean:
                    entries[start:start + len(legacy)] = deepcopy(clean)
                    data[section] = entries
                    changed = True
                    break
    original_skills = data.get('skills') or []
    skills = unique_skills(original_skills)
    if skills != original_skills and any(extract_skills(text) == skills for text in user_answers.values()):
        data['skills'] = skills
        changed = True
    for entry in data.get('education') or []:
        degree = entry.get('degree', '')
        if not re.search(r'\bdegrre$', degree, re.I):
            continue
        parsed = parse_education(degree)
        sources = [parse_education(text) for text in user_answers.values() if _normalise(degree) in _normalise(text)]
        if not parsed or not any(source and source.get('degree') == parsed['degree']
                and _normalise(source.get('institution', '')) == _normalise(entry.get('institution', '')) for source in sources):
            continue
        entry['degree'] = parsed['degree']
        subject = entry.get('field_of_study', '')
        if re.search(r'\bdegrre$', subject, re.I) and parsed.get('field_of_study'):
            entry['field_of_study'] = parsed['field_of_study']
        changed = True
    return changed


def _clean(state, user_answers, accepted_universities=()):
    data = state.get('collected_data') or {}
    changed = _repair_education(state, user_answers, accepted_universities)
    changed = _repair_lists(data, user_answers) or changed
    summary = data.get('summary')
    parsed = labelled_summary(summary) if isinstance(summary, str) else None
    if parsed and parsed[1] and _normalise(summary) in user_answers:
        data['summary'] = parsed[0]
        state.pop('language_proficiency_pending', None)
        changed = True
    entries = data.get('languages') or []
    cleaned = []
    for entry in entries:
        name = entry.get('name', '') if isinstance(entry, dict) else ''
        if (name and not entry.get('proficiency') and _normalise(name) in user_answers
                and (keep_languages_unchanged(name) or proficiency_unspecified(name))):
            pending = state.get('language_proficiency_pending') or []
            if any(_normalise(value) == _normalise(name) for value in pending):
                state.pop('language_proficiency_pending', None)
            changed = True
            continue
        split = parse_languages(name) if name and not entry.get('proficiency') else []
        if len(split) > 1 and _normalise(name) in user_answers:
            cleaned.extend(split)
            changed = True
        else:
            cleaned.append(entry)
    if cleaned != entries:
        data['languages'] = cleaned
    if changed:
        state.pop('approved_review_changes', None)
        state.pop('review_decisions', None)
    return changed


def repair_optional_answers(session):
    from django.db import transaction
    from chatbot.models import ChatSession

    def eligible(item):
        state = item.conversation_state
        data = state.get('collected_data') or {}
        summary = data.get('summary')
        parsed = labelled_summary(summary) if isinstance(summary, str) else None
        possible = (bool(parsed and parsed[1]) or bool(_misplaced_dates(data)) or _has_list_cleanup(data)
                    or date_repair_candidate(state)) or any(
            isinstance(entry, dict) and not entry.get('proficiency')
            and len(parse_languages(entry.get('name', ''))) > 1
            for entry in data.get('languages') or [])
        return (item.status in ('active', 'completed') and not item.cv_id
                and state.get('mode') != 'edit_existing'
                and not state.get('chat_saved_cv_id') and not state.get('edit_saved_cv_id') and possible)

    if not eligible(session):
        return False
    with transaction.atomic():
        locked = ChatSession.objects.select_for_update().get(pk=session.pk, user_id=session.user_id)
        if not eligible(locked):
            session.refresh_from_db()
            return False
        answers = {_normalise(text): text for text in locked.messages.filter(role='user').values_list('content', flat=True)}
        accepted_universities = set()
        for updates in locked.messages.filter(role='assistant').values_list('cv_updates', flat=True):
            for entry in (updates or {}).get('education') or []:
                name = entry.get('institution') if isinstance(entry, dict) else None
                if isinstance(name, str) and name and not _misplaced_dates({'education': [{'institution': name}]}):
                    accepted_universities.add(name)
        state = deepcopy(locked.conversation_state)
        history = list(locked.messages.order_by('created_at', 'id').values('role', 'content', 'intent', 'cv_updates'))
        date_changed = repair_date_state(state, history)
        if not (_clean(state, answers, accepted_universities) or date_changed):
            return False
        if state.get('undo_state'):
            _clean(state['undo_state'], answers, accepted_universities)
            repair_date_state(state['undo_state'], history)
        from chatbot.services.question_engine import next_step
        locked.current_section = state['current_section'] = next_step(state)['section']
        locked.conversation_state = state
        locked.save(update_fields=['conversation_state', 'current_section', 'updated_at'])
        if date_changed:
            from chatbot.models import ChatMessage
            from chatbot.services.question_engine import question
            dates = state['collected_data']['education'][0]
            values = ', '.join(f'{key.replace("_", " ")}: {dates[key]}' for key in ('start_date', 'end_date') if dates.get(key))
            ChatMessage.objects.create(session=locked, role='assistant', intent='collect_information',
                section=locked.current_section, next_action='review' if locked.current_section == 'review' else 'ask_question',
                content='I recovered the dates supported by your earlier answers (' + values + '). ' + question(state))
        session.refresh_from_db()
        return True
