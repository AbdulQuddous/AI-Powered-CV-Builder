"""Deterministic profile questions and recommendations; never adds CV facts."""
from chatbot.services.state_manager import PERSONAL_FIELD_ORDER
from chatbot.services.career_profiles import career_profile
from chatbot.services.career_guidance import recommendations

OPTIONAL_SECTIONS = ('certifications', 'achievements', 'languages')


def profile(state):
    return career_profile(state)


def next_step(state):
    if state.get('optional_entry_confirmation'):
        section = state['optional_entry_confirmation']['section']
        return {'section': section, 'field': section}
    if state.get('section_followup'):
        return {'section': state['section_followup']['section'], 'field': 'more_entries'}
    if state.get('pending_selection'):
        return {'section': state['pending_selection']['section'], 'field': 'select_entry'}
    if state.get('date_confirmation_pending'):
        pending = state['date_confirmation_pending']
        return {'section': pending['section'], 'field': pending['field']}
    focus = state.get('pending_field')
    if focus:
        return focus
    entry = state.get('pending_entry')
    if entry:
        from chatbot.services.existing_cv_conversation import FIELDS
        for field in FIELDS[entry['section']]:
            if not entry['draft'].get(field):
                return {'section': entry['section'], 'field': field}
    if state.get('language_proficiency_pending'):
        return {'section': 'languages', 'field': 'proficiency'}
    if state.get('mode') == 'edit_existing':
        from chatbot.services.existing_cv_conversation import edit_step
        return edit_step(state)
    if not state.get('target_role'):
        return {'section': 'target', 'field': 'target_role'}
    if not state.get('career_level'):
        return {'section': 'target', 'field': 'career_level'}
    for field in PERSONAL_FIELD_ORDER:
        if state['personal_fields'].get(field) in ('missing', 'invalid', 'needs_clarification'):
            return {'section': 'personal', 'field': field}
    completed = set(state.get('completed_sections', [])) | set(state.get('skipped_sections', []))
    junior = profile(state) in ('fresher', 'student', 'junior')
    order = ['education', 'skills', 'projects', 'experience'] if junior else ['experience', 'skills', 'education', 'projects']
    fields = {'education': ('education_fields', ['degree', 'institution', 'field_of_study', 'end_date']),
              'experience': ('experience_fields', ['company', 'role', 'responsibilities']),
              'projects': ('project_fields', ['name', 'description', 'technologies'])}
    for section in order + list(OPTIONAL_SECTIONS) + ['summary']:
        if section in completed:
            continue
        if section in fields:
            key, names = fields[section]
            for field in names:
                if state[key].get(field, 'missing') in ('missing', 'invalid', 'needs_clarification'):
                    return {'section': section, 'field': field}
        else:
            return {'section': section, 'field': section}
    return {'section': 'review', 'field': 'review'}


def question(state):
    from chatbot.services.response_normalizer import QUESTION_MAP
    step = next_step(state)
    section, field = step['section'], step['field']
    if state.get('optional_entry_confirmation'):
        from chatbot.services.optional_answers import confirmation_question
        return confirmation_question(state['optional_entry_confirmation'])
    if state.get('section_followup'):
        from chatbot.services.section_followups import followup_question
        return followup_question(state)
    if section == 'target' and field == 'career_level':
        return 'What is your career level: Student, Fresher, Junior, Mid-Level, Senior or Executive? You may also choose other.'
    if state.get('date_confirmation_pending'):
        from chatbot.services.date_confirmation import confirmation_question
        return confirmation_question(state)
    if section == 'languages' and field == 'proficiency':
        return 'Would you like to specify language proficiency? You can say "English professional, Urdu native", or keep it unspecified.'
    if state.get('pending_selection'):
        source = 'collected_data' if state['pending_selection'].get('source') == 'collection' else 'existing_cv'
        entries = (state.get(source) or {}).get(section) or []
        labels = [' / '.join(str(entry.get(key)) for key in ('name', 'institution', 'degree', 'company', 'job_title') if entry.get(key)) for entry in entries]
        return 'Which entry would you like to change? Reply with its number. ' + '; '.join(f'{i+1}. {label}' for i, label in enumerate(labels))
    if state.get('mode') == 'edit_existing' and not state.get('pending_field'):
        from chatbot.services.existing_cv_conversation import question as edit_question
        return edit_question(state)
    if section == 'education':
        from chatbot.services.education_answers import active_education
        entry = active_education(state)
        if entry.get('is_current'):
            if field == 'degree':
                return 'Which degree or course are you studying? You can include your university and expected graduation date in the same message.'
            if field == 'institution':
                return 'Which university or college are you studying at?'
            if field == 'field_of_study':
                return 'What is your subject or major?'
            if field == 'end_date':
                place = f' from {entry["institution"]}' if entry.get('institution') else ''
                return f'When do you expect to graduate{place}? You can say June 2028 or 2028-06, or just the year if the month is unknown.'
    if section == 'experience' and field == 'company':
        if state.get('pending_field') or state.get('pending_entry'):
            return 'Which company did you work or intern at? You can include your job title in the same reply, or skip if you have no experience.'
        if profile(state) in ('student', 'fresher', 'junior'):
            return 'Have you completed any internships, freelance work or professional experience? You can skip this if you have none.'
        return 'What relevant professional experience would you like to include? Share the company and job title; one employer is enough.'
    if section == 'experience' and field == 'responsibilities':
        if profile(state) == 'junior':
            return 'What did you deliver or contribute in this role? Include collaboration and any confirmed outcomes; metrics are optional.'
        if profile(state) == 'mid_level':
            return 'What did you own and deliver independently? Include technical decisions, collaboration and confirmed outcomes; metrics are optional.'
        if profile(state) == 'senior':
            return 'What did you own or design in this role? Include leadership, mentoring or technical decisions and confirmed results where relevant.'
        if profile(state) == 'executive':
            return 'What leadership scope, strategy and organizational responsibilities did you have? Include confirmed business impact where available.'
        return 'What were your main responsibilities and confirmed achievements? You can also share employment dates, current status and technologies used.'
    if section == 'projects' and field == 'technologies':
        return 'Which technologies did you use? Include a database or REST APIs only if you worked with them.'
    if section == 'certifications':
        return 'Do you have any relevant certifications? Share a title and issuer/date/link if available, or skip; none is required.'
    if section == 'achievements':
        return 'Would you like to include any achievements? Share only confirmed details, or skip.'
    if section == 'languages':
        return 'Which languages would you like to include? You may add basic, conversational, professional, fluent or native proficiency, or skip.'
    if section == 'review':
        return 'Please review your collected information. You can correct a field, or finish the interview when ready.'
    return QUESTION_MAP.get((section, field), f'Please provide {field.replace("_", " ")}, or skip if it is optional.')
