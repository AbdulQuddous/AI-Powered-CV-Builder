"""Reset prompts when the user explicitly changes or leaves an editing task."""
from copy import deepcopy

TRANSIENT = ('pending_field', 'pending_selection', 'pending_entry',
             'date_confirmation_pending', 'language_proficiency_pending',
             'optional_entry_confirmation', 'guidance_choice_pending',
             'experience_absence_pending', 'section_followup')


def clear_prompts(state):
    for key in TRANSIENT:
        state.pop(key, None)


def cancel_edit(state):
    clear_prompts(state)
    state.update(edit_focus=None, edit_operation=None, edit_draft=[],
                 edit_explicit_add=False, edit_finish_requested=False)


def prepare_edit_context(state, switch):
    """Apply a server-created deterministic correction target before validation."""
    state = deepcopy(state)
    clear_prompts(state)
    section = switch.get('section')
    state.update(edit_focus=section, edit_operation='edit' if section else None,
                 edit_draft=[], edit_explicit_add=False, edit_finish_requested=False)
    if section and switch.get('field'):
        state['pending_field'] = {key: value for key, value in switch.items()
                                  if key in ('section', 'field', 'index')}
    return state
