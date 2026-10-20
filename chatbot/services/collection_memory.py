"""Merge interview followups using backend question context, not guessed identities."""
import re
from copy import deepcopy

from rest_framework.exceptions import ValidationError

from cvs.chat_import import IDENTITIES, meaningful, merge_entries

FIELD_STATES = {'education': 'education_fields', 'experience': 'experience_fields',
                'projects': 'project_fields'}


def merge_collection_entries(entries, updates, section, step, *, index=None):
    entries, updates = deepcopy(entries), deepcopy(updates)
    if section == 'projects' and index is not None and step['field'] != 'name':
        if not isinstance(index, int) or not 0 <= index < len(entries):
            raise ValidationError('Select a valid project before adding details.')
        for item in updates:
            if item.get('name') and str(item['name']).casefold() != str(entries[index].get('name', '')).casefold():
                raise ValidationError('Confirm the project before changing its title.')
            entries[index].update(item)
        return entries
    if (section in FIELD_STATES and step['section'] == section and len(updates) == 1
            and isinstance(updates[0], dict) and meaningful(updates[0].get(step['field']))):
        update = updates[0]
        keys = IDENTITIES[section]
        # A direct answer to the next field completes the single incomplete entry.
        # Carry its already accepted identity into M2's existing sparse merge.
        if len(entries) == 1:
            entry = entries[0]
            conflicts = any(meaningful(entry.get(key)) and meaningful(update.get(key))
                            and str(entry[key]).casefold() != str(update[key]).casefold() for key in keys)
            if section == 'education' and not any(meaningful(entry.get(key)) for key in keys):
                # "I'm currently studying" has status but no identity yet. The
                # answer to its next degree question completes that same row.
                entry.update({key: update[key] for key in keys if meaningful(update.get(key))})
                return merge_entries(entries, updates, section)
            if not conflicts and not meaningful(entry.get(step['field'])):
                updates[0] = {**{key: entry[key] for key in keys if meaningful(entry.get(key))}, **update}
        elif len(entries) > 1:
            matches = [entry for entry in entries
                       if any(meaningful(entry.get(key)) and meaningful(update.get(key)) for key in keys)
                       and all(str(entry[key]).casefold() == str(update[key]).casefold()
                               for key in keys if meaningful(entry.get(key)) and meaningful(update.get(key)))]
            if len(matches) != 1:
                raise ValidationError('Identify the entry before adding this followup.')
    return merge_entries(entries, updates, section)


def sync_project_progress(state, index=None):
    """A project is complete only when its own fields are present, not a union of rows."""
    from chatbot.services.state_manager import get_default_project_fields
    entries = (state.get('collected_data') or {}).get('projects') or []
    required = ('name', 'description', 'technologies')
    active = entries[index] if isinstance(index, int) and 0 <= index < len(entries) else None
    complete = bool(entries) and all(all(entry.get(field) for field in required) for entry in entries)
    if active is not None and (not all(active.get(field) for field in required) or complete):
        state.setdefault('collection_entry_indexes', {})['projects'] = index
        scope = [active]
    else:
        state.setdefault('collection_entry_indexes', {}).pop('projects', None)
        scope = entries
    state['project_fields'] = {field: 'collected' if scope and all(entry.get(field) for entry in scope) else 'missing'
                               for field in get_default_project_fields()}
    completed = set(state.get('completed_sections', []))
    missing = set(state.get('missing_sections', []))
    if complete:
        completed.add('projects'); missing.discard('projects')
    else:
        completed.discard('projects'); missing.add('projects')
    state['completed_sections'], state['missing_sections'] = sorted(completed), sorted(missing)


def repair_study_status(session, state):
    """Join an evidenced status-only legacy row to its one subsequent degree.

    This repairs unsaved collection state only. Explicit additional degrees,
    contradictory status and ambiguous history remain untouched.
    """
    from chatbot.services.education_answers import parse_education
    if state.get('mode') == 'edit_existing' or state.get('pending_entry') or state.get('pending_selection'):
        return state
    entries = (state.get('collected_data') or {}).get('education') or []
    if (len(entries) != 2 or entries[0] != {'is_current': True}
            or not isinstance(entries[1], dict) or not isinstance(entries[1].get('degree'), str)
            or not entries[1]['degree']
            or entries[1].get('is_current') is False):
        return state
    source, status_seen, degree_seen = None, False, False
    for message in session.messages.order_by('created_at', 'id').values('role', 'content', 'intent', 'cv_updates'):
        if message['role'] == 'user':
            source = message['content']
            if re.search(r'\b(?:add|another|second|new)\b.*\b(?:education|degree|university|qualification)\b', source, re.I):
                return state
            continue
        if not source or message['intent'] == 'irrelevant':
            continue
        parsed = parse_education(source) or {}
        updates = (message['cv_updates'] or {}).get('education') or []
        if len(updates) > 1:
            return state
        update = updates[0] if updates and isinstance(updates[0], dict) else {}
        if parsed == {'is_current': True} and update == parsed:
            status_seen = True
        if (status_seen and parsed.get('is_current') and parsed.get('degree')
                and parsed['degree'].casefold() == entries[1]['degree'].casefold()
                and str(update.get('degree', '')).casefold() == entries[1]['degree'].casefold()):
            degree_seen = True
        if update.get('is_current') is False:
            return state
        source = None
    if not degree_seen:
        return state
    from chatbot.services.state_manager import get_default_education_fields
    state = deepcopy(state)
    merged = {**entries[0], **entries[1]}

    def collapse(target):
        target['collected_data']['education'] = [deepcopy(merged)]
        fields = get_default_education_fields()
        fields.update({key: 'collected' for key in fields if meaningful(merged.get(key))})
        target['education_fields'] = fields
        for key in ('pending_field', 'date_confirmation_pending'):
            pending = target.get(key) or {}
            if pending.get('section') == 'education' and pending.get('index') == 1:
                pending['index'] = 0
        statuses = target.setdefault('field_status', {})
        shifted = {key.replace('education.1.', 'education.0.', 1): value
                   for key, value in statuses.items() if key.startswith('education.1.')}
        for key in list(statuses):
            if key.startswith('education.1.'):
                statuses.pop(key)
        statuses.update(shifted)
        statuses.update({f'education.0.{key}': 'answered' for key in fields if meaningful(merged.get(key))})

    collapse(state)
    undo = state.get('undo_state') or {}
    if (undo.get('collected_data') or {}).get('education') == entries:
        collapse(undo)
    return state


def repair_split_education(session, state):
    """Repair only the old, evidenced degree-then-institution fragmentation bug.

    Explicit additional entries and grouped source entries remain distinct. No
    database write happens here; the usual atomic turn persists a repaired state.
    Rejected answers are not reconstructed or silently promoted into accepted facts.
    """
    if state.get('mode') == 'edit_existing' or state.get('pending_entry'):
        return state
    fragments = state.get('collected_data', {}).get('education') or []
    if len(fragments) != 2 or not all(isinstance(entry, dict) for entry in fragments):
        return state
    degree, institution = fragments
    if not (degree.get('degree') and not degree.get('institution')
            and institution.get('institution') and not institution.get('degree')):
        return state
    if any(meaningful(degree.get(key)) and meaningful(value)
           and str(degree[key]).casefold() != str(value).casefold()
           for key, value in institution.items()):
        return state
    degree_seen, institution_seen = False, False
    for message in session.messages.order_by('created_at', 'id').values('role', 'content', 'cv_updates'):
        if message['role'] == 'user':
            if re.search(r'\b(?:add|another|second|new)\b.*\b(?:education|degree|university|qualification)\b', message['content'], re.I):
                return state
            continue
        updates = (message['cv_updates'] or {}).get('education')
        if not updates:
            continue
        if not isinstance(updates, list) or len(updates) != 1 or not isinstance(updates[0], dict):
            return state
        item = updates[0]
        if item.get('degree') == degree['degree'] and not item.get('institution'):
            degree_seen = True
        if degree_seen and item.get('institution') == institution['institution'] and not item.get('degree'):
            institution_seen = True
    if not institution_seen:
        return state
    from chatbot.services.state_manager import get_required_conversation_step, get_default_education_fields
    previous_step = get_required_conversation_step(state)
    state = deepcopy(state)
    merged = {**degree, **{key: value for key, value in institution.items() if meaningful(value)}}
    state['collected_data']['education'] = [merged]
    fields = get_default_education_fields()
    for field in fields:
        if meaningful(merged.get(field)):
            fields[field] = 'collected'
    state['education_fields'] = fields
    state['completed_sections'] = [section for section in state.get('completed_sections', []) if section != 'education']
    # Keep the last asked question answerable, then return to genuinely missing fields.
    if previous_step['section'] == 'education':
        state['pending_field'] = previous_step
    return state


def repair_structured_education(session, state):
    """Unpack a proven JSON-as-degree mistake in an unsaved, single-qualification draft.

    Only the normal owner-scoped message transaction persists this repair. Original
    messages remain intact; ambiguous qualifications and saved documents are untouched.
    """
    from chatbot.services.education_answers import structured_education, parse_education, reversed_date_range
    from chatbot.services.structured_answers import looks_structured
    from chatbot.services.field_validation import validate_value
    from django.core.exceptions import ValidationError as FieldError
    from chatbot.services.state_manager import get_default_education_fields, get_required_conversation_step

    if (session.cv_id or state.get('mode') == 'edit_existing' or state.get('chat_saved_cv_id')
            or state.get('pending_entry') or state.get('edit_saved_cv_id')):
        return state
    entries = (state.get('collected_data') or {}).get('education') or []
    if not 1 <= len(entries) <= 2 or not all(isinstance(entry, dict) for entry in entries):
        return state
    anchors = [(entry[key], key) for entry in entries for key in ('degree', 'institution')
               if isinstance(entry.get(key), str) and looks_structured(entry[key])]
    if len(anchors) != 1:
        return state
    raw, bad_field = anchors[0]
    decoded = structured_education(raw)
    if not decoded or not decoded.get('degree') or not decoded.get('institution'):
        return state
    # A matching accepted proposal and its exact user source prove the old mistake.
    source_seen, proven = False, False
    for message in session.messages.order_by('created_at', 'id').values('role', 'content', 'cv_updates'):
        if message['role'] == 'user':
            if re.search(r'\b(?:add|another|second|new)\b.*\b(?:education|degree|university|qualification)\b', message['content'], re.I):
                return state
            if re.search(r'\b(?:change|correct|update|edit)\b.*\b(?:education|degree|university|institution|specialization)\b', message['content'], re.I):
                return state
            source_seen = ' '.join(message['content'].split()) == ' '.join(raw.split())
        elif source_seen:
            updates = (message['cv_updates'] or {}).get('education') or []
            if isinstance(updates, list) and len(updates) == 1 and isinstance(updates[0], dict) and updates[0].get(bad_field) == raw:
                proven = True
            source_seen = False
    if not proven:
        return state
    subject = (parse_education(decoded['degree']) or {}).get('field_of_study')
    merged = deepcopy(decoded)
    accepted = {}
    for entry in entries:
        for key, value in entry.items():
            if not meaningful(value) or value == raw:
                continue
            if key in ('degree', 'institution') and str(value).casefold() != str(decoded[key]).casefold():
                return state
            if key == 'field_of_study' and decoded.get(key) and value == subject:
                continue  # Keep the explicit specialization instead of the broader degree subject.
            if key in accepted and accepted[key] != value:
                return state
            accepted[key] = value
    merged.update(accepted)
    try:
        for key, value in merged.items():
            if key != 'is_current':
                validate_value(key, value)
        if reversed_date_range(merged.get('start_date'), merged.get('end_date')):
            return state
    except FieldError:
        return state
    state = deepcopy(state)
    previous = get_required_conversation_step(state)
    state['collected_data']['education'] = [merged]
    fields = get_default_education_fields()
    fields.update({key: 'collected' for key in fields if meaningful(merged.get(key))})
    state['education_fields'] = fields
    state['completed_sections'] = [key for key in state.get('completed_sections', []) if key != 'education']
    if previous['section'] == 'education':
        state['pending_field'] = previous  # The user's reply still answers the last question shown.
    statuses = state.setdefault('field_status', {})
    for key in list(statuses):
        if key.startswith('education.'):
            statuses.pop(key)
    statuses.update({f'education.0.{key}': 'answered' for key in fields if meaningful(merged.get(key))})
    if state.get('undo_state', {}).get('collected_data', {}).get('education') == entries:
        state['undo_state']['collected_data']['education'] = [deepcopy(merged)]
        state['undo_state']['education_fields'] = deepcopy(fields)
    return state
