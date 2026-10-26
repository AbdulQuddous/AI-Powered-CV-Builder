"""Normalize and route messages before model use, preserving the M5 envelope."""
import json
import re
from copy import deepcopy

from chatbot.services.conversation_router import empty_ai_response, try_local_extraction
from chatbot.services.field_validation import extract_skills
from chatbot.services.local_extractor import is_skip_command, is_finish_command
from chatbot.services.question_engine import question, recommendations
from chatbot.services.content_handling import is_direct_abuse, is_conversational_question, is_self_harm_concern
from chatbot.services.section_answers import (labelled_summary, parse_languages, proficiency_unspecified,
    keep_languages_unchanged, section_request, structured_section_answer)
from chatbot.services.education_answers import parse_education, parse_certificate, parse_employer, normalise_date, DATE
from chatbot.services.structured_answers import looks_structured
from chatbot.services.project_answers import is_profile_paragraph, project_title, project_description
from chatbot.services.career_profiles import profile_name, PROFILES
from chatbot.services.career_guidance import guidance_request, guidance_message, automatic_guidance, guidance_data

PERSONAL = {'name': 'full_name', 'full name': 'full_name', 'email': 'email',
            'phone': 'phone', 'location': 'location', 'linkedin': 'linkedin',
            'github': 'github', 'portfolio': 'portfolio'}
OPTIONAL = {'phone', 'location', 'linkedin', 'github', 'portfolio'}
ABSENCE = re.compile(r"^(?:no(?: (?:work )?experience| internship)?|none|skip(?: this(?: question| section)?)?|i have no experience|experience nahi hai|no employment|i have never worked)[.!]*$", re.I)


def control(intent, **kwargs):
    response = empty_ai_response()
    response['_control'] = {'intent': intent, **kwargs}
    return response


def response_update(section, field, value):
    response = empty_ai_response()
    response['section'] = section
    if section == 'target':
        response['state_updates'][field] = value
    elif section == 'personal':
        response['cv_updates'][section] = {field: value}
    elif section in ('summary', 'skills', 'achievements'):
        response['cv_updates'][section] = value
    else:
        response['cv_updates'][section] = [{field: value}]
    return response


def _edit_target(response, state, section, field=None, index=None):
    """Private marker emitted only by these exact local correction commands."""
    if state.get('mode') == 'edit_existing':
        response.setdefault('_control', {})['_edit_switch'] = {
            'section': section, **({'field': field} if field else {}),
            **({'index': index} if index is not None else {}),
        }
    return response


def _explicit_correction(state, text):
    correction = re.fullmatch(r'(?:change|update|edit) my (full name|name|email|phone|location|linkedin|github|portfolio|summary)(?: to (.+))?', text, re.I)
    if correction:
        label, value = correction.groups()
        section = 'summary' if label.lower() == 'summary' else 'personal'
        field = 'summary' if section == 'summary' else PERSONAL[label.lower()]
        response = response_update(section, field, value) if value else control('focus', focus={'section': section, 'field': field})
        return _edit_target(response, state, section, field)
    correction = re.fullmatch(r'(?:change|update|edit) my (university|institution|degree|project description|job title)(?: to (.+))?', text, re.I)
    if correction and state.get('mode') == 'edit_existing':
        label, value = correction.groups()
        section, field = {'university': ('education', 'institution'),
            'institution': ('education', 'institution'), 'degree': ('education', 'degree'),
            'project description': ('projects', 'description'), 'job title': ('experience', 'role')}[label.lower()]
        entries = (state.get('existing_cv') or {}).get(section) or []
        if len(entries) == 1:
            if value:
                response = response_update(section, field, value)
                response['_control'] = {'intent': 'entry_patch', 'section': section, 'index': 0}
            else:
                response = control('focus', focus={'section': section, 'field': field, 'index': 0})
            return _edit_target(response, state, section, field, 0)
        if len(entries) > 1:
            return _edit_target(control('select_entry', section=section, field=field), state, section)
        return _edit_target(control('clarification', notice='There is no saved entry in this section yet. You can add a new entry.'), state, None)
    command = re.fullmatch(r'(add|remove) (.+?) (?:to|from) (?:my )?skills', text, re.I)
    if command:
        operation, values = command.groups()
        skills = extract_skills(values)
        if not skills and operation.lower() == 'remove':
            skills = [skill for skill in guidance_data(state).get('skills') or []
                      if skill.casefold() == values.strip().casefold()]
        if skills:
            if operation.lower() == 'remove':
                return _edit_target(control('remove_skills', skills=skills), state, None)
            return _edit_target(response_update('skills', 'skills', skills), state, 'skills', 'skills')
    return None


def classify(text):
    if is_self_harm_concern(text):
        return 'support_needed'
    # Intent patterns, not a profanity substring blacklist. Quoted/workplace content stays eligible.
    if re.search(r'\b(?:ignore (?:all |previous )?instructions|delete (?:my |the )?database|execute (?:shell|sql))\b', text, re.I):
        return 'inappropriate'
    if is_direct_abuse(text):
        return 'inappropriate'
    if re.search(r'\b(?:who won (?:the |today.s )?(?:cricket|football|match)|(?:what is|what.s|tell me) (?:the )?weather|tell (?:me |us )?a joke|write (?:me )?(?:a |some )?(?:python )?(?:game|code))\b', text, re.I):
        return 'off_topic'
    if '?' in text or re.match(r'^(?:can|should|how|what|could|is it|do i)\b', text, re.I):
        if re.search(r'\b(?:cv|resume|final.year project|cgpa|certificat|internship|summary|skills|experience)\b', text, re.I):
            return 'cv_question'
    return None


def route_message(state, text, step):
    """Return None only when natural language actually requires local Qwen."""
    text = ' '.join(text.strip().split())
    lower = text.casefold().rstrip('.!')
    section, field = step['section'], step['field']
    if state.get('support_check_pending'):
        if lower in ('resume cv', 'continue cv', 'continue with my cv', 'continue with the cv',
                     'i am safe', "i'm safe", 'no i am safe', 'no'):
            return control('resume_cv')
        return control('support_needed')
    if state.get('mode') == 'edit_existing' and lower in ('cancel', 'cancel this', 'cancel this step', 'cancel edit', 'stop adding', 'never mind', 'nevermind'):
        return control('cancel_edit')
    topic = guidance_request(text)
    if topic:
        return control('career_guidance', topic=topic)
    if state.get('guidance_choice_pending'):
        if lower in ('no', 'no thanks', 'keep all', 'continue', 'next', 'continue without changes'):
            return control('dismiss_guidance')
        if lower in ('yes', 'yes please', 'all of them', 'use your suggestions', 'use suggestions', 'add them all', 'okay', 'ok', 'sure'):
            return control('guidance_choice')
    career_change = re.fullmatch(r'(?:change|set|update) my career level to (.+)', text, re.I)
    if career_change:
        selected = profile_name(career_change[1])
        if selected:
            response = response_update('target', 'career_level', PROFILES[selected][1])
            response['_control'] = {'intent': 'answer', 'question_profile': selected}
            return _edit_target(response, state, 'target')
        return control('clarification', notice='Choose Student, Fresher, Junior, Mid-Level, Senior, Executive or other.')
    if section == 'personal' and field in ('linkedin', 'github', 'portfolio'):
        link = re.fullmatch(r'\[[^\]]*\]\((https?://\S+)\)', text, re.I)
        value = link[1] if link else text
        if re.fullmatch(r'https?://\S+', value, re.I):
            return response_update(section, field, value)
    # Section requests must be routed before generic CV questions or scalar answers.
    request = section_request(text)
    if request:
        target, operation = request
        from chatbot.services.existing_cv_conversation import FIELDS
        if state.get('mode') == 'edit_existing':
            return control('edit_focus', section=target, operation=operation)
        if target in FIELDS and operation == 'add':
            return control('collection_focus', section=target)
        return control('focus', focus={'section': target, 'field': target})
    kind = classify(text)
    if kind:
        response = control(kind)
        if kind in ('off_topic', 'inappropriate'):
            response['intent'] = 'irrelevant'
        return response
    if lower in ('show progress', 'show collected information', 'show my information', 'review my cv'):
        return control('show_progress')
    if lower in ('go back', 'back', 'undo', 'undo last change'):
        return control('go_back')
    if state.get('mode') == 'edit_existing':
        correction = _explicit_correction(state, text)
        if correction is not None:
            return correction
    if state.get('section_followup'):
        correction = _explicit_correction(state, text)
        if correction is not None:
            correction.setdefault('_control', {})['dismiss_followup'] = True
            return correction
        from chatbot.services.section_followups import route_followup
        return route_followup(state, text)
    confirmation = state.get('optional_entry_confirmation')
    if confirmation:
        if lower in ('yes', 'yes add it', 'yes, add it', 'add it', 'confirm', 'confirmed'):
            if confirmation['section'] == 'certifications':
                return control('clarification', notice='Please provide the full certification title and issuer if available; confirmation alone does not establish a certification.')
            response = empty_ai_response(); response['section'] = confirmation['section']
            response['cv_updates'][confirmation['section']] = deepcopy(confirmation['entries'])
            response['_control'] = {'intent': 'confirm_optional'}
            return response
        if lower in ('no', 'no thanks', 'cancel', 'cancel this', 'cancel this step', 'never mind', 'nevermind'):
            return control('cancel_edit' if state.get('mode') == 'edit_existing' else 'dismiss_optional')
        if is_finish_command(text) or lower in ('finish', 'done', 'save', 'nothing else'):
            return control('clarification', notice='Confirm the optional entry or say "cancel" before finishing; I have not added it.')
    if state.get('mode') == 'edit_existing' and not confirmation and (
            is_finish_command(text) or lower in ('nothing else', 'done', 'save', 'no more changes')
            or (section == 'review' and lower == 'nothing')):
        response = control('finish'); response['next_action'] = 'complete'
        return response
    from chatbot.services.optional_answers import optional_chatter
    if section in ('languages', 'certifications', 'skills') and optional_chatter(text):
        exit_hint = 'Provide the requested CV detail, switch sections, or say "cancel".' if state.get('mode') == 'edit_existing' else 'Provide the requested CV detail or choose another CV section.'
        return control('clarification', notice='That looks like a conversational message, so I have not added it. ' + exit_hint)
    if state.get('date_confirmation_pending'):
        pending = state['date_confirmation_pending']
        if is_skip_command(text) or lower in ('omit', 'omit this date', 'omit date', 'skip this date', 'leave it blank', 'leave this date blank'):
            return control('omit_source_date')
        parsed = parse_education(text, pending['field']) if section in ('education', 'experience') else None
        values = {key: parsed[key] for key in ('start_date', 'end_date') if parsed and key in parsed}
        if not values:
            value = normalise_date(text)
            if re.fullmatch(r'(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?', value):
                values[pending['field']] = value
        if not values:
            return control('clarification', notice='Please confirm the month as well; I will not invent it.')
        response = empty_ai_response(); response['section'] = section
        # Validate both endpoints together. Partial years and a complete sibling
        # date are retained while the active field still needs its month.
        response['cv_updates'][section] = [values]
        # Carry the selected entry's identity, so multiple degrees/jobs stay separate.
        from cvs.chat_import import IDENTITIES
        entry = state['collected_data'][section][pending['index']]
        for key in IDENTITIES[section]:
            if parsed and parsed.get(key) and entry.get(key) and parsed[key].casefold() != entry[key].casefold():
                return control('clarification', notice='These dates are being collected for the listed entry. Confirm which education or job entry you want to change.')
        response['cv_updates'][section][0].update({key: entry[key] for key in IDENTITIES[section] if entry.get(key)})
        return response
    if state.get('pending_selection'):
        selection = state['pending_selection']
        source = 'collected_data' if selection.get('source') == 'collection' else 'existing_cv'
        entries = (state.get(source) or {}).get(selection['section']) or []
        index = int(text) - 1 if re.fullmatch(r'\d+', text) else None
        if index is None and selection.get('source') == 'collection':
            matches = [i for i, entry in enumerate(entries) if entry.get('name', '').casefold() == lower]
            if len(matches) == 1:
                index = matches[0]
        if index is not None and 0 <= index < len(entries):
            if selection.get('source') == 'collection':
                response = empty_ai_response(); response['section'] = selection['section']
                response['cv_updates'][selection['section']] = deepcopy(selection['updates'])
                response['_control'] = {'intent': 'collection_patch', 'section': selection['section'], 'index': index}
                return response
            else:
                return control('focus', focus={**selection, 'index': index}, clear_selection=True)
        return control('clarification', notice='Please select a listed entry number before editing it.')
    review_done = section == 'review' and lower in ('no', 'none', 'nothing')
    done_phrase = lower in (
        'no other thing', 'no other things', 'nothing else', 'no more things',
        'no other changes', 'no thanks', 'all done', "i'm done", 'i am done')
    if is_finish_command(text) or review_done or done_phrase or lower in ('save', 'done', "that's all", 'that is all', 'no more changes', 'finish my cv'):
        response = control('finish')
        response['next_action'] = 'complete'
        return response
    summary = labelled_summary(text)
    if summary:
        response = response_update('summary', 'summary', summary[0])
        if summary[1]:
            response['_control'] = {'intent': 'answer', 'unspecified_proficiency': True}
        return response
    if proficiency_unspecified(text) or (state.get('language_proficiency_pending') and (
            keep_languages_unchanged(text) or is_skip_command(text) or ABSENCE.fullmatch(text))):
        return control('answer', unspecified_proficiency=True)
    if section == 'languages' and keep_languages_unchanged(text):
        return control('clarification', notice='Please name the languages to include, or skip this section.')
    if state.get('experience_absence_pending') and lower in ('yes', 'confirm', 'yes no experience', 'i confirm', 'no experience'):
        return control('skip', skip_fields=['experience'], confirmed_absence=True)
    if is_skip_command(text) or ABSENCE.fullmatch(text):
        if section == 'education' and field in ('grade', 'start_date'):
            return control('skip_field', section=section, field=field)
        if section == 'personal' and field in OPTIONAL:
            return control('skip', skip_fields=[field])
        if section in ('education', 'experience', 'projects', 'certifications', 'achievements', 'languages', 'summary'):
            return control('skip', skip_fields=[section])
        if section == 'personal' and field in ('full_name', 'email'):
            label = 'full name' if field == 'full_name' else 'email address'
            return control('clarification', notice=f'Your {label} is required for this CV and cannot be skipped.')
        return control('clarification', notice='This field is needed to guide the interview. Please provide it.')
    # A selected subset changes presentation only; retain all source entries.
    choice = re.fullmatch(r'(?:select|display|use) (?:experiences? )?([\d, and]+)', lower)
    if choice:
        return control('select_experience', indexes=[int(n) - 1 for n in re.findall(r'\d+', choice[1])])
    choice = re.fullmatch(r'(?:select|display|use) (projects?|certifications?) ([\d, and]+)', lower)
    if choice:
        section = 'projects' if choice[1].startswith('project') else 'certifications'
        return control('select_entries', section=section, indexes=[int(n) - 1 for n in re.findall(r'\d+', choice[2])])
    if re.match(r'^(?:select|display|use) (?:projects?|certifications?)\b', lower):
        return control('clarification', notice='Please list the original entry numbers, for example: select projects 1, 2.')
    correction = _explicit_correction(state, text)
    if correction is not None:
        return correction
    # Explicit new-entry requests reuse the existing targeted editing workflow.
    from chatbot.services.existing_cv_conversation import REQUESTS
    request = REQUESTS.get(lower)
    if state.get('mode') != 'edit_existing' and request:
        if request[0] in ('projects', 'experience', 'education'):
            return control('collection_focus', section=request[0])
        return control('focus', focus={'section': request[0], 'field': request[0]})
    if state.get('mode') == 'edit_existing':
        request = REQUESTS.get(lower)
        if request:
            return control('edit_focus', section=request[0], operation=request[1])
        new_request = re.fullmatch(r'(?:i want to )?(?:add|edit|update)(?: my| a new| a| another)? (languages?|skills?|certifications?|education|experience|projects?|summary)', lower)
        if new_request:
            noun = new_request[1]
            target = {'language': 'languages', 'skill': 'skills', 'certification': 'certifications', 'project': 'projects'}.get(noun, noun)
            return control('edit_focus', section=target, operation='edit' if lower.startswith(('edit', 'update')) else 'add')
    if section == 'target' and field == 'career_level':
        label = re.sub(r"^(?:i am (?:a |an )?|i'm (?:a |an )?)", '', lower)
        selected = profile_name(label)
        if selected:
            response = response_update('target', 'career_level', PROFILES[selected][1])
            response['_control'] = {'intent': 'answer', 'question_profile': selected}
            return response
        return try_local_extraction(required_step=step, user_message=text)
    inline_language = re.fullmatch(r'(?:i want to )?add (.+?) (?:to my cv|to my languages|as a language)', text, re.I)
    if inline_language and not re.search(r'\b(?:project|skill|job|experience)\b', inline_language[1], re.I):
        response = empty_ai_response()
        response['section'] = 'languages'
        response['cv_updates']['languages'] = parse_languages(inline_language[1])
        return response
    # Explicit contact/name answers. Grouped prose is delegated intact to Qwen.
    match = re.fullmatch(r'(?:my (?:full )?name is|i am called) (.+)', text, re.I)
    if match and not re.search(r'[.;]|\band (?:I|my)\b', match[1], re.I):
        return response_update('personal', 'full_name', match[1])
    match = re.fullmatch(r'(?:my email is|email:)\s*(\S+)', text, re.I)
    if match:
        return response_update('personal', 'email', match[1].rstrip('.'))
    if section == 'education':
        education = parse_education(text, field)
        if education:
            response = empty_ai_response(); response['section'] = section
            response['cv_updates'][section] = [education]
            return response
        if looks_structured(text):
            return control('clarification', notice='Please check the pasted education JSON. Use distinct institution, degree, specialization and graduation date/year fields.')
        if re.fullmatch(DATE + r'[.!]?', text, re.I) and field not in ('start_date', 'end_date'):
            return control('clarification', notice='Please say whether this is your start date or graduation date.')
    if section in ('certifications', 'languages', 'achievements'):
        entries = structured_section_answer(text, section)
        if entries:
            response = empty_ai_response(); response['section'] = section
            response['cv_updates'][section] = entries
            return response
        if looks_structured(text) or text.startswith('"'):
            return control('clarification', notice='Please check the pasted list. Use text items, or named entries with the supported fields; no duplicate JSON properties.')
    if section == 'certifications':
        certificate = parse_certificate(text)
        if certificate:
            response = empty_ai_response(); response['section'] = section
            response['cv_updates'][section] = [certificate]
            return response
    if section == 'experience' and field in ('company', 'role'):
        if field == 'company' and lower in ('yes', 'yes i have', 'yes i did', 'i have', 'yes please'):
            return control('focus', focus={'section': 'experience', 'field': 'company'})
        labelled = re.fullmatch(r'(?:(?:my|the)\s+)?(company(?:\s+name)?|employer|job title|role)\s*(?::|=|\bis\b)\s*(.+)', text, re.I)
        if labelled:
            target = 'company' if labelled[1].casefold().startswith(('company', 'employer')) else 'role'
            value = labelled[2].strip()
            if target == 'role':
                from chatbot.services.entity_validation import clear_job_title
                value = re.sub(r'^(?:a|an)\s+', '', value, flags=re.I)
                if not clear_job_title(value):
                    return None  # A label alone is not evidence of an occupation.
            return response_update(section, target, value)
        employer = parse_employer(text)
        if employer:
            response = empty_ai_response(); response['section'] = section
            response['cv_updates'][section] = [employer]
            return response
        from chatbot.services.entity_validation import entity_problem
        problem = entity_problem(section, field, text, text)
        if problem:
            return control('clarification', notice=problem)
    if is_conversational_question(text):
        return None
    if section == 'projects' and field in ('name', 'description') and is_profile_paragraph(text):
        response = response_update('summary', 'summary', text)
        response['_control'] = {'intent': 'answer', 'notice': 'I kept that profile paragraph as your professional summary. Please provide the project details separately.'}
        return response
    if section == 'projects' and field == 'name':
        title = project_title(text)
        if title:
            return response_update(section, field, title)
        if re.match(r'^(?:built|developed|created|i\s+(?:built|developed|created|made))\b', text, re.I) and '?' not in text:
            response = empty_ai_response(); response['section'] = section
            response['cv_updates'][section] = [project_description(text)]
            response['_control'] = {'intent': 'collection_focus', 'section': section}
            if state.get('mode') == 'edit_existing':
                return None
            return response
    if section == 'education' and field == 'end_date':
        graduation = re.fullmatch(
            r'(?:i\s+(?:am\s+)?(?:graduated|graduate)(?:\s+in)?|'
            r'(?:i\s+)?(?:will|expect to)\s+graduate(?:\s+in)?|graduated(?:\s+in)?)'
            r'\s+((?:19|20)\d{2}(?:-\d{2})?)[.!]?', text, re.I)
        if graduation:
            return response_update(section, field, graduation[1])
    if section == 'experience' and field == 'responsibilities' and '?' not in text and re.match(
            r'^(?:i\s+)?(?:build|built|building|develop(?:ed|ing)?|design(?:ed|ing)?|'
            r'maintain(?:ed|ing)?|manage(?:d)?|managing|prepared|tested|supported)\b', text, re.I):
        return response_update(section, field, [text])
    if section == 'projects' and field == 'description' and '?' not in text:
        response = empty_ai_response(); response['section'] = section
        response['cv_updates'][section] = [project_description(text)]
        return response
    # Never store a question, command, or multi-clause answer as a scalar field.
    complex_text = bool(re.search(r'\b(?:I|my|worked|graduated|know|made|using|uses|builds|built|developed|have|change|update|add|remove|want|nahi|maine|hai)\b|[?;]|\band\b', text, re.I))
    if section == 'personal' and field in ('email', 'phone', 'linkedin', 'github', 'portfolio'):
        if not complex_text or ('@' in text and ' ' not in text):
            return response_update(section, field, text)
    if section == 'skills' or (section == 'projects' and field == 'technologies'):
        skills = extract_skills(text)
        if skills:
            return response_update(section, field, skills)
        if looks_structured(text):
            return control('clarification', notice='Please provide skills as a JSON list or groups of text lists, without duplicate or conflicting fields.')
    if re.fullmatch(r'[\w .\-]+\s+(?:basic|conversational|professional|fluent|native)(?:\s*(?:,|and)\s*[\w .\-]+\s+(?:basic|conversational|professional|fluent|native))*\.?', text, re.I):
        response = empty_ai_response()
        response['section'] = 'languages'
        response['cv_updates']['languages'] = []
        response['cv_updates']['languages'] = parse_languages(text)
        return response
    if section == 'projects' and field == 'description' and re.match(r'^(?:it|this project|the project)\b', text, re.I) and '?' not in text:
        return response_update(section, field, text)
    if section == 'experience' and field in ('responsibilities', 'highlights'):
        return None  # Unclear duties require semantic interpretation, not scalar storage.
    if section in ('languages', 'certifications') and (not complex_text or (section == 'languages' and not re.search(r'\b(?:I|my|worked|change|update|add|remove|want)\b|[?;]', text, re.I))):
        if section == 'languages':
            response = empty_ai_response()
            response['section'] = section
            response['cv_updates'][section] = parse_languages(text)
            return response
        values = [v.strip().rstrip('.') for v in re.split(r',|\band\b', text) if v.strip()]
        entries = []
        for value in values:
            match = re.fullmatch(r'(.+?)\s+(basic|conversational|professional|fluent|native)', value, re.I) if section == 'languages' else None
            entries.append({'name': match[1], 'proficiency': match[2].lower()} if match else {'name': value})
        response = empty_ai_response(); response['section'] = section
        response['cv_updates'][section] = entries
        return response
    if section == 'target' and field == 'target_role' and not re.search(r'\b(?:developer|engineer|designer|manager|analyst|teacher|nurse|accountant|specialist|consultant|director|officer|writer|student|architect|sales|marketing)\b', text, re.I):
        return None
    if not complex_text and len(text) < 256 and field not in ('edit_request', 'changes', 'select_entry', 'review'):
        if section == 'experience' and field == 'company':
            from chatbot.services.entity_validation import clear_employer_label
            if not clear_employer_label(text):
                return None
        if section == 'experience' and field in ('role', 'job_title'):
            from chatbot.services.entity_validation import clear_job_title
            if not clear_job_title(text):
                return None
        if section in ('personal', 'target', 'education', 'experience', 'projects'):
            return response_update(section, field, text)
    if section == 'summary' and field == 'summary' and '?' not in text:
        return response_update('summary', 'summary', text)
    return None


def apply_control(state, response):
    """Apply only bounded, supported transitions; Qwen cannot authorize arbitrary writes."""
    state = deepcopy(state)
    action = response.get('_control') or {}
    intent = action.get('intent')
    notice = action.get('notice', '')
    if action.get('dismiss_followup') or action.get('question_profile') or intent in (
            'dismiss_followup', 'focus', 'collection_focus', 'edit_focus', 'career_guidance', 'finish'):
        state.pop('section_followup', None)
    if intent == 'career_guidance':
        state['guidance_choice_pending'] = action.get('topic', 'all')
    elif intent != 'guidance_choice':
        state.pop('guidance_choice_pending', None)
    pending_date = state.get('date_confirmation_pending')
    if pending_date:
        entries = (response.get('cv_updates') or {}).get(pending_date['section']) or []
        answer = next((item[pending_date['field']] for item in entries if item.get(pending_date['field'])), '')
        answered = bool(re.fullmatch(r'(?:19|20)\d{2}-(?:0[1-9]|1[0-2])', answer)) or (
            answer == 'present' and pending_date['section'] == 'experience' and pending_date['field'] == 'end_date')
        if re.fullmatch(r'(?:19|20)\d{2}', answer):
            state['date_confirmation_pending']['year'] = answer
        if intent == 'omit_source_date':
            state.setdefault('omitted_source_dates', []).append(pending_date)
            notice = 'That date will be omitted from the CV. Your original year remains in the chat.'
        if answered or intent == 'omit_source_date':
            state.pop('date_confirmation_pending', None)
            if state.get('pending_field', {}).get('section') == pending_date['section']:
                state.pop('pending_field', None)
    languages = (response.get('cv_updates') or {}).get('languages') or []
    pending_languages = list(state.get('language_proficiency_pending') or [])
    for item in languages:
        if not isinstance(item, dict) or not item.get('name'):
            continue
        pending_languages = [name for name in pending_languages if name.casefold() != item['name'].casefold()]
        if not item.get('proficiency'):
            pending_languages.append(item['name'])
    if action.get('unspecified_proficiency') or intent == 'finish':
        pending_languages = []
    if pending_languages:
        state['language_proficiency_pending'] = pending_languages
    else:
        state.pop('language_proficiency_pending', None)
    supplied_skills = {skill.casefold() for skill in (response.get('cv_updates') or {}).get('skills') or []}
    if supplied_skills:
        state['removed_skills'] = [skill for skill in state.get('removed_skills', []) if skill.casefold() not in supplied_skills]
    if action.get('question_profile'):
        state['question_profile'] = action['question_profile']
    if intent == 'support_needed':
        state['support_check_pending'] = True
    elif intent == 'resume_cv':
        state.pop('support_check_pending', None)
    if intent == 'focus':
        state.pop('optional_entry_confirmation', None)
        state['pending_field'] = action['focus']
        if action.get('clear_selection'):
            state.pop('pending_selection', None)
    elif intent == 'select_entry':
        state['pending_selection'] = {'section': action['section'], 'field': action['field']}
    elif intent == 'entry_patch':
        section = action['section']
        entries = (response.get('cv_updates') or {}).get(section) or []
        if entries:
            patches = state.setdefault('entry_patches', [])
            patch = next((p for p in patches if p['section'] == section and p['index'] == action['index']), None)
            if patch is None:
                patch = {'section': section, 'index': action['index'], 'updates': {}}
                patches.append(patch)
            patch['updates'].update(entries[0])
            state.pop('pending_field', None)
            state['edit_focus'] = None
            notice = 'The proposed change is collected. Review it before saving.'
    elif intent == 'edit_focus':
        from chatbot.services.edit_controls import clear_prompts
        clear_prompts(state)
        state.update(edit_focus=action['section'], edit_operation=action['operation'],
                     edit_explicit_add=action['operation'] == 'add', edit_draft=[])
    elif intent == 'cancel_edit':
        from chatbot.services.edit_controls import cancel_edit
        cancel_edit(state)
        notice = 'Canceled this step. Previously collected changes are still pending and have not been saved.'
    elif intent == 'optional_confirmation':
        state['optional_entry_confirmation'] = {'section': action['section'], 'entries': deepcopy(action['entries'])}
    elif intent in ('confirm_optional', 'dismiss_optional'):
        state.pop('optional_entry_confirmation', None)
    elif intent == 'collection_focus':
        state.pop('optional_entry_confirmation', None)
        state['pending_entry'] = {'section': action['section'], 'draft': {}}
        state.pop('pending_selection', None)
    elif intent == 'collection_patch':
        state.setdefault('collection_entry_indexes', {})[action['section']] = action['index']
        state.pop('pending_selection', None)
    elif intent == 'skip_field':
        state.setdefault('field_status', {})[action['section'] + '.' + action['field']] = 'skipped'
        state.pop('pending_field', None)
    elif intent == 'select_entries':
        section = action['section']
        entries = guidance_data(state).get(section) or []
        indexes = action['indexes']
        if indexes and len(set(indexes)) == len(indexes) and all(type(i) is int and 0 <= i < len(entries) for i in indexes):
            state.setdefault('display_entry_indexes', {})[section] = indexes
            notice = f'Your selected {section} will be displayed in that order. All source entries remain in this conversation.'
        else:
            notice = 'Choose valid, distinct original entry numbers. Your previous selection is unchanged.'
    elif intent == 'select_experience':
        entries = (state.get('collected_data') or {}).get('experience') or []
        if state.get('mode') == 'edit_existing':
            from cvs.chat_import import merge_entries
            entries = deepcopy((state.get('existing_cv') or {}).get('experience') or [])
            entries = [dict(item, role=item.get('job_title', '')) for item in entries]
            entries = merge_entries(entries, state.get('edit_updates', {}).get('experience', []), 'experience')
        indexes = list(dict.fromkeys(action['indexes']))
        if 0 < len(indexes) <= 5 and all(0 <= i < len(entries) for i in indexes):
            state['display_experience_indexes'] = indexes
            notice = 'Your selected experiences will be displayed. The other source entries remain in this session.'
        else:
            notice = 'Select up to five valid experience numbers, for example: select experiences 1, 2, 3.'
    elif intent == 'remove_skills':
        # The exact named skill is the explicit user-approved target. Ambiguous removals never reach here.
        state['removed_skills'] = list(dict.fromkeys(state.get('removed_skills', []) + action['skills']))
        notice = 'Proposed removal: ' + ', '.join(action['skills']) + '. Review before saving.'
    elif intent == 'skip':
        for target in action.get('skip_fields', []):
            if state.get('optional_entry_confirmation', {}).get('section') == target:
                state.pop('optional_entry_confirmation', None)
            if target in OPTIONAL:
                state['personal_fields'][target] = 'skipped'
            elif target in ('education', 'experience', 'projects', 'certifications', 'achievements', 'languages', 'summary'):
                if target == 'experience' and state.get('career_level') == 'experienced' and not state.get('experience_absence_pending') and not action.get('confirmed_absence'):
                    state['experience_absence_pending'] = True
                    notice = 'Experience is useful for this career level. Please confirm that you have no employment, internship or freelance experience; this is allowed.'
                    continue
                state.setdefault('skipped_sections', [])
                if target not in state['skipped_sections']:
                    state['skipped_sections'].append(target)
                if target == 'experience' and state.get('career_level') == 'experienced':
                    state.setdefault('suitability_warnings', []).append('Experienced profile without employment history; absence confirmed by user.')
                if state.get('pending_field', {}).get('section') == target:
                    state.pop('pending_field', None)
                if state.get('pending_entry', {}).get('section') == target:
                    state.pop('pending_entry', None)
                if state.get('edit_focus') == target:
                    state['edit_focus'] = None
        if state.get('pending_field', {}).get('field') in action.get('skip_fields', []):
            state.pop('pending_field', None)
    optional = state.get('optional_entry_confirmation')
    if optional and intent != 'optional_confirmation' and (response.get('cv_updates') or {}).get(optional['section']):
        state.pop('optional_entry_confirmation', None)
    if intent == 'finish' and state.get('mode') == 'edit_existing':
        if state.get('edit_focus') in (None, 'skills', 'certifications', 'languages', 'achievements', 'summary', 'personal', 'target'):
            # Finish can leave an optional prompt without inventing an answer.
            from chatbot.services.edit_controls import cancel_edit
            cancel_edit(state)
        else:
            state.pop('language_proficiency_pending', None)
            state.pop('pending_selection', None)
    return state, notice


def _skill_retry_message(state):
    from chatbot.services.career_guidance import candidate_skills
    examples = ' or '.join(candidate_skills(state)[:2])
    example = f', such as {examples}' if examples else ''
    exit_hint = (' You can also say "cancel" or choose another section.'
                 if state.get('mode') == 'edit_existing' else '')
    return ("I couldn't recognize a clear CV skill in that reply. "
            "I'm here to help you describe your real abilities. "
            f'Which skill would you like to include{example}?' + exit_hint)


def model_feedback(response):
    """Accept bounded display-only Qwen feedback for rejected or unclear answers."""
    action = response.get('_control') or {}
    value = action.get('rejection_reason')
    if isinstance(value, str):
        reason = ' '.join(value.split())
        if (0 < len(reason) <= 320 and not re.search(r'[<>{}?]|https?://|www\.', reason, re.I)
                and not is_direct_abuse(reason)):
            return reason.rstrip('.!') + '.'
    return ''


def _rejection_reason(response):
    reason = model_feedback(response)
    if reason:
        return reason
    action = response.get('_control') or {}
    if action.get('intent') == 'inappropriate':
        return "Let's keep this professional. That sounds like a remark directed at me rather than information for your CV."
    return "That message doesn't describe CV information or a change I can apply."


def _retry_question(state, step):
    followup = question(state)
    if step['section'] == 'experience' and step['field'] in ('role', 'job_title'):
        followup += ' For example, Developer, Designer or Intern.'
    return followup


def present_response(response, state, errors=None, notice=''):
    from chatbot.services.question_engine import next_step
    step = next_step(state)
    response['section'] = step['section']
    action = (response.get('_control') or {}).get('intent')
    if action == 'support_needed':
        response.update(intent='give_suggestion', next_action='ask_question', assistant_message=(
            "I'm sorry you're feeling this way. Your safety matters. Are you in immediate danger or about to hurt yourself? "
            "If so, contact local emergency services now and reach out to someone you trust who can stay with you. "
            'We can pause the CV. When you are safe and ready, you can say "resume CV".'))
    elif action in ('off_topic', 'inappropriate') or response.get('intent') == 'irrelevant':
        detail = _rejection_reason(response) + ' That message was not added to your CV. '
        followup = (_skill_retry_message(state) if step['section'] == 'skills' else _retry_question(state, step))
        exit_hint = (' You can switch sections or say "cancel".'
                     if state.get('mode') == 'edit_existing' and step['section'] not in ('review', 'skills') else '')
        response.update(intent='irrelevant', next_action='ask_question',
                        assistant_message=detail + followup + exit_hint)
    elif action == 'cv_question':
        response.update(intent='give_suggestion', next_action='ask_question', assistant_message=(
            'Projects can demonstrate practical skills even without formal employment. Certifications and grades are optional; include only confirmed, relevant facts. '
            + guidance_message(state, (response.get('_control') or {}).get('topic', 'all')) + '\n\n' + question(state)))
    elif action == 'career_guidance':
        response.update(intent='give_suggestion', next_action='ask_question', assistant_message=(
            guidance_message(state, response['_control'].get('topic', 'all')) + '\n\n' + question(state)))
    elif action in ('guidance_choice', 'dismiss_guidance'):
        detail = ('Please name what you want to add or prioritize, for example "add another project" or "prioritize projects". Suggestions are not added automatically. '
                  if action == 'guidance_choice' else 'Your confirmed information is kept. ')
        response.update(intent='give_suggestion', next_action='ask_question', assistant_message=detail + question(state))
    elif action == 'show_progress':
        if state.get('mode') == 'edit_existing':
            from chatbot.services.progress_review import progress_message
            response.update(intent='give_suggestion', next_action='review',
                            assistant_message=progress_message(state) + '\n\n' + question(state))
            response.pop('_control', None)
            return response
        info = state.get('collected_data') or state.get('edit_updates') or {}
        response.update(intent='give_suggestion', next_action='review', assistant_message=(
            'Collected information: ' + json.dumps(info, ensure_ascii=False)[:7000] + '\n' + '\n'.join(recommendations(state)) + '\n' + question(state)))
    elif state.get('optional_entry_confirmation'):
        from chatbot.services.optional_answers import confirmation_question
        response.update(intent='clarify_information', next_action='ask_question',
                        assistant_message=confirmation_question(state['optional_entry_confirmation']))
    elif errors or action == 'clarification':
        fallback = ('I couldn’t identify your job title in that reply.'
                    if step['section'] == 'experience' and step['field'] in ('role', 'job_title') else
                    'Please clarify the details you would like to include.')
        detail = (' '.join(errors) if errors else
                  notice or model_feedback(response) or fallback)
        if (step['section'] == 'experience' and step['field'] in ('role', 'job_title')
                and not any(item.get('role') or item.get('job_title')
                            for item in response.get('cv_updates', {}).get('experience') or [])
                and 'no job title was added' not in detail.casefold()):
            detail += ' No job title was added.'
        exit_hint = (' You can also say "cancel" or choose another section.'
                     if state.get('mode') == 'edit_existing' else '')
        control_data = response.get('_control') or {}
        unclear_skill = (step['section'] == 'skills' and not any(response.get('cv_updates', {}).values())
                         and (control_data.get('requires_clarification') or control_data.get('evidence_warning')
                              or (action == 'clarification' and not notice)))
        response.update(intent='clarify_information', next_action='ask_question',
                        assistant_message=(_skill_retry_message(state) if unclear_skill else
                                           detail + ' ' + _retry_question(state, step) + exit_hint))
    elif action == 'finish' and step['section'] == 'review':
        response.update(intent='complete', next_action='complete', assistant_message='Your draft is ready. Review the collected details, optionally request an external Gemini review, then save when you approve.')
    else:
        response['next_action'] = 'review' if step['section'] == 'review' else 'ask_question'
        response['intent'] = 'update_cv' if any(value for value in response.get('cv_updates', {}).values()) else 'collect_information'
        response['assistant_message'] = (notice + ' ' if notice else '') + question(state)
        advice = automatic_guidance(state, response) if state.get('mode') != 'edit_existing' or action == 'edit_focus' else ''
        if advice:
            response['assistant_message'] += '\n\n' + advice
    response.pop('_control', None)
    return response
