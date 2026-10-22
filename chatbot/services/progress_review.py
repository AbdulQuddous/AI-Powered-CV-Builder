"""Read-only, plain-text review of proposals in an existing-CV conversation."""
import unicodedata

from chatbot.services.existing_cv_conversation import FIELDS, IDENTITIES


LABELS = {
    'personal': 'Contact details', 'summary': 'Summary', 'skills': 'Skills',
    'experience': 'Experience', 'education': 'Education', 'projects': 'Projects',
    'certifications': 'Certifications', 'achievements': 'Achievements', 'languages': 'Languages',
    'target_role': 'Target role', 'career_level': 'Career level',
    'full_name': 'Full name', 'field_of_study': 'Field of study', 'job_title': 'Job title',
    'role': 'Job title', 'start_date': 'Start date', 'end_date': 'Completion date',
    'is_current': 'Current position',
}
ENTRY_KEYS = {**IDENTITIES, 'certifications': ('name', 'issuer'), 'languages': ('name',)}
ALIASES = {'role': 'job_title', 'responsibilities': 'highlights'}
LIMIT = 4800  # Leave room for the caller's current question.


def clean(value, limit=300):
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ''
    value = ''.join(char for char in value if not unicodedata.category(char).startswith('C') or char in '\n\r\t')
    value = ' '.join(value.split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def meaningful(value):
    if isinstance(value, dict):
        return any(meaningful(item) for item in value.values())
    if isinstance(value, list):
        return any(meaningful(item) for item in value)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def display(value):
    if isinstance(value, list):
        values = [clean(item, 180) for item in value]
        return clean(' · '.join(item for item in values if item), 500)
    return clean(value, 500)


def label(key):
    return LABELS.get(key, str(key).replace('_', ' ').capitalize())


def fields(value, previous=None):
    if not isinstance(value, dict):
        return display(value)
    parts = []
    for key, item in value.items():
        if not meaningful(item):
            continue
        old = previous.get(ALIASES.get(key, key), previous.get(key)) if isinstance(previous, dict) else None
        if isinstance(previous, dict) and item == old:
            continue
        rendered = display(item)
        if rendered:
            parts.append(f'{label(key)}: {rendered}')
    return '; '.join(parts)


def entry_label(section, item, index=None):
    if isinstance(item, str):
        return clean(item, 140)
    item = item if isinstance(item, dict) else {}
    keys = {'experience': ('company', 'job_title', 'role'), 'education': ('institution', 'degree'),
            'projects': ('name',), 'certifications': ('name', 'issuer'), 'languages': ('name',)}.get(section, ('name', 'title'))
    values = list(dict.fromkeys(clean(item.get(key), 100) for key in keys if clean(item.get(key))))
    return ' / '.join(values) or (f'Entry {index + 1}' if index is not None else 'Entry awaiting identification')


def matches(section, proposal, entries):
    if not isinstance(proposal, dict):
        return []
    result = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        common = [(proposal.get(key), entry.get(ALIASES.get(key, key), entry.get(key)))
                  for key in ENTRY_KEYS.get(section, ())]
        common = [(a, b) for a, b in common if meaningful(a) and meaningful(b)]
        if common and all(clean(a).casefold() == clean(b).casefold() for a, b in common):
            result.append((index, entry))
    return result


def unfinished(state):
    section = state.get('edit_focus')
    if section not in FIELDS or state.get('edit_operation') == 'edit':
        return []
    return [(section, item, [key for key in FIELDS[section] if not meaningful(item.get(key))])
            for item in state.get('edit_draft') or [] if isinstance(item, dict)
            and meaningful(item) and any(not meaningful(item.get(key)) for key in FIELDS[section])]


def progress_message(state):
    """Describe pending facts only; saved context is used solely to label changes."""
    state = state if isinstance(state, dict) else {}
    saved = state.get('existing_cv') if isinstance(state.get('existing_cv'), dict) else {}
    updates = state.get('edit_updates') if isinstance(state.get('edit_updates'), dict) else {}
    partial = unfinished(state)
    pending = []
    for section, value in updates.items():
        if not meaningful(value):
            continue
        if section in ENTRY_KEYS:
            previous = saved.get(section) if isinstance(saved.get(section), list) else []
            for item in value if isinstance(value, list) else []:
                if any(section == draft_section and item == draft for draft_section, draft, _ in partial):
                    continue
                found = matches(section, item, previous)
                if len(found) == 1:
                    index, old = found[0]
                    text = fields(item, old)
                    if text:
                        pending.append(f'- {label(section)} — {entry_label(section, old, index)}: {text}')
                else:
                    text = fields(item)
                    if text:
                        suffix = ' (entry needs confirmation)' if len(found) > 1 else ''
                        pending.append(f'- {label(section)}{suffix}: {text}')
        else:
            if section in ('skills', 'achievements') and isinstance(value, list):
                previous = saved.get(section) if isinstance(saved.get(section), list) else []
                known = {clean(item, 2000).casefold() for item in previous}
                removed = {clean(item, 2000).casefold() for item in state.get('removed_skills') or []} if section == 'skills' else set()
                value = [item for item in value if clean(item, 2000).casefold() not in known | removed]
            text = fields(value, saved.get(section)) if isinstance(value, dict) else display(value)
            if section == 'summary' and value == saved.get(section):
                continue
            if text:
                pending.append(f'- {label(section)}: {text}')
    for item in state.get('edit_new_projects') or []:
        text = fields(item)
        if text:
            pending.append('- New project: ' + text)
    metadata = saved.get('meta') if isinstance(saved.get('meta'), dict) else {}
    for key, value in (state.get('edit_metadata_updates') or {}).items():
        text = display(value)
        if key in ('target_role', 'career_level') and text and value != metadata.get(key):
            pending.append(f'- {label(key)}: {text}')
    for patch in state.get('entry_patches') or []:
        if not isinstance(patch, dict):
            continue
        section, index = patch.get('section'), patch.get('index')
        if not isinstance(section, str) or section not in ENTRY_KEYS:
            continue
        entries = saved.get(section) if isinstance(saved.get(section), list) else []
        identified = type(index) is int and 0 <= index < len(entries)
        old = entries[index] if identified else None
        text = fields(patch.get('updates'), old)
        if text:
            title = entry_label(section, old, index) if identified else 'Entry needs confirmation'
            pending.append(f'- {label(section)} — {title}: {text}')
    removed = display(state.get('removed_skills') or [])
    if removed:
        pending.append('- Requested skill removals: ' + removed)
    pending = list(dict.fromkeys(pending))
    lines = ['Pending CV changes (not saved).', 'Your saved CV is unchanged. This review lists only proposed changes.']
    confirmation = state.get('optional_entry_confirmation')
    if isinstance(confirmation, dict) and confirmation.get('section') in ('languages', 'certifications'):
        candidates = [clean(entry.get('name'), 160) for entry in confirmation.get('entries') or []
                      if isinstance(entry, dict) and clean(entry.get('name'))]
        if candidates:
            lines.append('Awaiting confirmation (not added):')
            lines.append(f'- {label(confirmation["section"])}: ' + ' · '.join(candidates[:5]))
            if pending:
                lines.append('Other collected changes (not saved):')
    lines.extend(pending or ['No pending changes have been collected.'])
    if partial:
        lines.append('Unfinished additions (not ready to save):')
        for section, item, missing in partial:
            lines.append(f'- {label(section)}: {fields(item)}. Still needed: ' + ', '.join(label(key).lower() for key in missing) + '.')
    message = '\n'.join(lines)
    if len(message) > LIMIT:
        note = '\nMore pending details are retained. Open the draft review to see the full proposal.'
        message = message[:LIMIT - len(note) - 1].rsplit('\n', 1)[0] + note
    return message
