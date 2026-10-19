"""Resolve source dates that cannot be represented by the canonical CV schema."""
import re


def next_unconfirmed_date(state):
    if state.get('mode') == 'edit_existing':
        return None
    data = state.get('collected_data') or {}
    omitted = state.get('omitted_source_dates') or []
    for section in ('education', 'experience', 'certifications'):
        for index, entry in enumerate(data.get(section) or []):
            selection = (state.get('display_experience_indexes') if section == 'experience'
                         else (state.get('display_entry_indexes') or {}).get(section))
            if selection is not None and index not in selection:
                continue
            for field in ('start_date', 'end_date', 'date'):
                value = entry.get(field, '')
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}', value):
                    continue
                pending = {'section': section, 'field': field, 'index': index, 'year': value}
                if pending not in omitted:
                    return pending
    return None


def confirmation_question(state):
    pending = state['date_confirmation_pending']
    entry = state['collected_data'][pending['section']][pending['index']]
    name = entry.get('institution') or entry.get('company') or entry.get('name') or pending['section']
    label = {'start_date': 'start date', 'end_date': 'end/graduation date', 'date': 'issue date'}[pending['field']]
    return (f'You gave {pending["year"]} for the {label} at {name}. '
            'The saved CV needs a year and month. Please provide YYYY-MM (for example '
            f'{pending["year"]}-06), or say "omit this date" to leave it off the CV.')
