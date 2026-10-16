"""Deterministic profile questions and recommendations; never adds CV facts."""
from chatbot.services.state_manager import PERSONAL_FIELD_ORDER

OPTIONAL_SECTIONS = ('certifications', 'achievements', 'languages')


def profile(state):
    return state.get('question_profile') or state.get('career_level') or 'fresher'


def next_step(state):
    if state.get('pending_selection'):
        return {'section': state['pending_selection']['section'], 'field': 'select_entry'}
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
    if section == 'experience' and field == 'company':
        if profile(state) in ('student', 'fresher', 'junior'):
            return 'Have you completed any internships, freelance work or professional experience? You can skip this if you have none.'
        return 'What relevant professional experience would you like to include? Share the company and job title; one employer is enough.'
    if section == 'experience' and field == 'responsibilities':
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


def recommendations(state):
    data = state.get('collected_data') or state.get('edit_updates') or {}
    messages = []
    skills = data.get('skills') or []
    if len(skills) > 15:
        messages.append('You have a large skills list. Consider highlighting your strongest relevant skills; I can help group them for readability. All skills are retained.')
    if len(data.get('certifications') or []) > 5:
        messages.append('Consider featuring around 3–5 of your most relevant certifications. All certifications are retained until you choose.')
    if len(data.get('projects') or []) > 5:
        messages.append('Consider selecting the strongest three to five projects for your target role. All projects are retained.')
    if len(data.get('experience') or []) > 5:
        messages.append('The canonical CV supports at most five displayed experiences. Please select five; all source entries remain in this conversation.')
    if profile(state) in ('student', 'fresher'):
        messages.append('Aim for a concise page when practical; final page count depends on the rendered template.')
    else:
        messages.append('One or two pages may be useful depending on relevant career history and the selected template.')
    for entry in data.get('education') or []:
        import re
        grade = re.fullmatch(r'(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)', str(entry.get('grade', '')).replace(' ', ''))
        if grade and float(grade[2]) > 0 and float(grade[1]) / float(grade[2]) < .6:
            messages.append('Grades are optional. You can omit your grade and focus on relevant coursework, projects and confirmed achievements if you prefer.')
            break
    role = (state.get('target_role') or '').lower()
    if 'python' in role or 'django' in role:
        messages.append("If you have used REST APIs, Git or Django REST Framework, you may want to include them. They have not been added.")
    elif 'frontend' in role or 'front end' in role:
        messages.append("If you have used React, TypeScript or responsive design, you may want to include them. They have not been added.")
    return messages
