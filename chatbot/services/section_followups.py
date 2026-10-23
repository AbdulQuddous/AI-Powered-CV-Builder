"""Optional count checks after an interview section, without adding CV facts."""
import re

from chatbot.services.career_guidance import EARLY, career_profile, guidance_data


def entry_count(data, section):
    entries = data.get(section) or []
    if section == 'projects':
        return sum(all(entry.get(field) for field in ('name', 'description', 'technologies'))
                   for entry in entries)
    return len(entries)


def offer_followup(previous, state, response, errors):
    # Existing-CV editing already has an explicit add/review loop. This pause is
    # for the initial interview, where the next question otherwise changes topic.
    if errors or state.get('mode') == 'edit_existing':
        return
    from chatbot.services.question_engine import next_step
    section = next_step(previous)['section']
    if section not in ('skills', 'projects', 'certifications'):
        return
    if not response.get('cv_updates', {}).get(section):
        return
    if any(state.get(key) for key in ('pending_field', 'pending_entry', 'pending_selection',
                                     'date_confirmation_pending', 'optional_entry_confirmation')):
        return
    count = entry_count(guidance_data(state), section)
    if count <= entry_count(guidance_data(previous), section):
        return
    lower, upper = {'skills': (8, 15), 'projects': ((2, 3) if career_profile(state) in EARLY else (3, 5)),
                    'certifications': (3, 5)}[section]
    band = 'short' if count < lower else 'long' if count > upper else None
    if not band:
        return
    key = f'{section}:{band}:{career_profile(state)}'
    seen = state.setdefault('section_followups_seen', [])
    if key in seen:
        return
    seen.append(key)
    state['section_followup'] = {'section': section, 'count': count, 'lower': lower,
                                'upper': upper, 'band': band}


def followup_question(state):
    pending = state['section_followup']
    section, count = pending['section'], pending['count']
    noun = {'skills': 'skill', 'projects': 'project', 'certifications': 'certification'}[section]
    intro = f'You have added {count} {noun}{"s" if count != 1 else ""}. '
    target = f'{pending["lower"]}–{pending["upper"]}'
    if pending['band'] == 'long':
        return (intro + f'Consider prioritizing your strongest {target} relevant {section} for readability. '
                'Everything is retained. Would you like prioritization suggestions, or continue with all entries?')
    detail = {'skills': f'Around {target} relevant skills can help if you can demonstrate them; fewer are fine.',
              'projects': f'{target} strong relevant projects can help if available; one is fine too.',
              'certifications': f'Consider {target} relevant certifications only if you already hold them; fewer or none is fine.'}[section]
    return intro + detail + ' Would you like to add more, or continue?'


def route_followup(state, text):
    """A suggestion is never consent to fabricate skills or credentials."""
    from chatbot.services.message_routing import control, response_update
    from chatbot.services.local_extractor import is_finish_command, is_skip_command
    pending = state.get('section_followup')
    if not pending:
        return None
    lower = text.casefold().rstrip('.!')
    if is_finish_command(text) or lower in ('done', 'save', 'nothing else'):
        response = control('finish')
        response['next_action'] = 'complete'
        return response
    if is_skip_command(text) or lower in ('no', 'none', 'no more', 'no thanks', 'continue', 'next', 'keep all',
                                         'continue please', 'move on',
                                         'continue with all', 'continue with all entries',
                                         'continue without changes', 'cancel', 'keep it as is'):
        return control('dismiss_followup')
    if lower in ('yes', 'yes please', 'add more', 'more', 'yes add more', 'yes, add more',
                 'suggestions', 'prioritize', 'prioritise'):
        section = pending['section']
        if pending['band'] == 'long':
            return control('career_guidance', topic=section)
        if section == 'projects':
            return control('collection_focus', section=section)
        return control('focus', focus={'section': section, 'field': section})
    section = pending['section']
    response = None
    if section == 'skills':
        from chatbot.services.field_validation import extract_skills
        detail = re.sub(r'^(?:(?:i (?:want|would like) to )?add\s+(?:more\s+)?)', '', text, flags=re.I)
        skills = extract_skills(detail)
        if skills:
            response = response_update('skills', 'skills', skills)
            response['_control'] = {'intent': 'dismiss_followup'}
    elif section == 'projects' and re.match(r'^(?:i (?:want|would like) to )?add\s+', text, re.I):
        from chatbot.services.project_answers import project_title
        title = project_title(text)
        if title:
            response = response_update('projects', 'name', title)
            response['_control'] = {'intent': 'collection_focus', 'section': 'projects'}
    elif section == 'certifications':
        from chatbot.services.education_answers import parse_certificate
        from chatbot.services.section_answers import structured_section_answer
        from chatbot.services.conversation_router import empty_ai_response
        certificate = parse_certificate(text)
        entries = structured_section_answer(text, 'certifications') or ([certificate] if certificate else None)
        if entries:
            response = empty_ai_response()
            response['cv_updates']['certifications'] = entries
            response['_control'] = {'intent': 'dismiss_followup'}
    if response is not None:
        return response
    return control('clarification', notice='Your entries are kept. Say "add more" to add your own details, or "continue" to move on. You can also switch sections.')
