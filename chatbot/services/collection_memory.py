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
