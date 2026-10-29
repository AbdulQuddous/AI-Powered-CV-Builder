"""Conservative evidence checks for literal facts returned by local extraction.

Descriptions still require user review; this guard rejects unsupported identity,
contact, skill and numerical facts rather than attempting semantic fact proving.
"""
import re
from copy import deepcopy

from chatbot.services.field_validation import ALIASES
from chatbot.services.education_answers import education_dates, structured_education, parse_certificate


def comparable(text):
    return ' '.join(str(text).casefold().split())


def mentioned(value, message):
    value, message = comparable(value), comparable(message)
    if value in message:
        return True
    return any(value == comparable(canonical) and re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', message)
               for alias, canonical in ALIASES.items())


def _active_section(state):
    pending = state.get('pending_field') or {}
    return (pending.get('section') or state.get('edit_focus')
            or ('languages' if state.get('language_proficiency_pending') else None)
            or state.get('current_section'))


def _selected_names(state, context, existing, section):
    """Resolve an explicit active entry, never choose an arbitrary saved name."""
    pending = state.get('pending_field') or {}
    entries = existing.get(section) or context.get(section) or []
    if pending.get('section') == section and type(pending.get('index')) is int:
        index = pending['index']
        if 0 <= index < len(entries) and isinstance(entries[index], dict):
            return [entries[index].get('name')]
    drafts = state.get('edit_draft') or []
    if state.get('edit_focus') == section and state.get('edit_operation') == 'edit':
        targets = drafts if len(drafts) == 1 else entries if len(entries) == 1 else []
        return [item.get('name') for item in targets if isinstance(item, dict)]
    return []


def _proficiency_answer(message):
    return bool(re.fullmatch(
        r"(?:(?:i am|i'm|my proficiency is|proficiency(?: is)?|my level is|level(?: is)?)\s+)?"
        r'(?:basic|conversational|professional|fluent|native)[.!]?', message.strip(), re.I))


def _explicit_section(section, message):
    """A different add/edit section needs facts explicitly labelled by the user."""
    cues = {
        'languages': r'\b(?:languages?|speak|spoken|proficiency)\b|\S+\s+(?:basic|conversational|professional|fluent|native)\b',
        'certifications': r'\b(?:certifications?|certificates?|certified|credentials?|exam|courses?|bootcamp)\b',
        'skills': r'\b(?:skills?|technologies|tech stack|tools|programming|know|proficient in|experience with)\b',
        'personal': r'@|https?://|\b(?:my name|email|phone|location|linkedin|github|portfolio)\b',
        'education': r'\b(?:education|degree|university|college|school|studying|graduated)\b',
        'experience': r'\b(?:experience|employer|company|internship|job|worked|responsibilities)\b',
        'projects': r'\bprojects?\b', 'achievements': r'\b(?:achievements?|awards?|accomplishments?)\b',
        'summary': r'\bsummary\b|\b(?:profile|introduction)[ -]paragraph\b',
    }
    return bool(re.search(cues.get(section, r'(?!)'), message, re.I))


def _summary_supplied(message, document):
    from chatbot.services.section_answers import labelled_summary
    from chatbot.services.project_answers import is_profile_paragraph
    if document is None and '{' in message:
        from chatbot.services.structured_answers import parse_structured
        # A pasted CV object may follow an introductory sentence. It must still
        # be a complete valid object, with the existing duplicate-key checks.
        document = parse_structured(message[message.index('{'):])
    return bool(labelled_summary(message) or is_profile_paragraph(message)
                or isinstance(document, dict) and isinstance(document.get('summary'), str)
                or re.match(
                    r'^(?:(?:can|could|would)\s+you\s+|please\s+|i\s+(?:want|would like)\s+to\s+)?'
                    r'(?:write|generate|create|draft|rewrite|update|replace|change|edit|improve|add)\s+'
                    r'(?:(?:my|the|a)\s+)?(?:professional\s+)?'
                    r'(?:summary|(?:profile|introduction)(?:[ -]paragraph)?)\b', message, re.I))


def _clarify_without_changes(response, warning, section):
    from chatbot.services.conversation_router import empty_ai_response
    result = empty_ai_response()
    result['section'] = section
    result['_control'] = {
        'intent': 'clarification', 'evidence_warning': warning,
        'rejection_reason': (response.get('_control') or {}).get('rejection_reason'),
    }
    return result


def guard_extraction(response, message, state):
    result = deepcopy(response)
    from chatbot.services.question_engine import next_step
    from chatbot.services.entity_validation import entity_problem, narrative_problem
    step = next_step(state)
    control = result.get('_control') or {}
    projects = result.get('cv_updates', {}).get('projects') or []
    if (step['section'] == 'projects' and step['field'] == 'name'
            and isinstance(projects, list) and len(projects) == 1 and isinstance(projects[0], dict)
            and isinstance(projects[0].get('name'), str) and projects[0]['name']
            and result.get('intent') != 'irrelevant'
            and control.get('intent') not in ('off_topic', 'inappropriate', 'clarification')):
        from chatbot.services.project_answers import literal_project_details
        supplied = literal_project_details(message, projects[0]['name']) or {}
        for field, value in supplied.items():
            if not projects[0].get(field):
                projects[0][field] = value
    problem = narrative_problem(step['section'], step['field'], message)
    if not problem and step['section'] == 'review':
        problem = narrative_problem('summary', 'summary', message)
    # A provider cannot launder an invalid narrative into benign invented prose,
    # even from the review screen or a structured multi-section answer.
    from chatbot.services.structured_answers import looks_structured, parse_structured
    document = parse_structured(message) if looks_structured(message) else None
    candidates = document if isinstance(document, dict) else result.get('cv_updates', {})
    for section, value in candidates.items():
        if problem or not value:
            continue
        if section in ('summary', 'achievements'):
            problem = narrative_problem(section, section, value if document is not None else message)
        elif section in ('experience', 'projects') and isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                for field, item in entry.items():
                    if document is not None and section == 'projects' and field == 'name':
                        problem = entity_problem(section, field, item, message)
                    else:
                        problem = narrative_problem(section, field, item if document is not None else message)
                    if problem:
                        break
                if problem:
                    break
    if not problem and step['section'] == 'projects' and step['field'] == 'name' and document is None:
        from chatbot.services.project_answers import grouped_project, project_title, project_title_problem
        source = grouped_project(message)
        source_text = re.sub(r'^i\s+(?:have|hold|earned|received|completed)\s+(?:(?:a|an|the)\s+)?',
                             '', message.strip(), flags=re.I)
        title = source['name'] if source else project_title(source_text)
        if title:
            type_problem = project_title_problem(title, message)
            if type_problem:
                # Keep this retry about projects even if Qwen asks for a
                # certificate issuer or treats an ambiguous subject as abuse.
                return _clarify_without_changes({}, type_problem, step['section'])
            problem = entity_problem('projects', 'name', title, message)
    if not problem and step['section'] == 'experience' and step['field'] in ('company', 'role', 'job_title', 'responsibilities', 'highlights'):
        problem = entity_problem('experience', step['field'], message, message)
    elif not problem and step['section'] == 'certifications':
        source = parse_certificate(message)
        title = source['name'] if source else message if step['field'] in ('name', 'certifications', 'changes') else None
        if title is not None:
            title = re.sub(
                r'^(?:(?:could|can|would)\s+you\s+(?:please\s+)?(?:add|include)|'
                r'i\s+(?:want|would like)\s+to\s+(?:add|include)|please\s+(?:add|include))\s+',
                '', title.strip(), flags=re.I)
            problem = entity_problem('certifications', 'name', title, message)
    if problem:
        # Validate the source too: a model must not turn a rejected answer into
        # invented duties/qualifications, profile changes or a silent skip.
        if control.get('intent') in ('off_topic', 'inappropriate') or result.get('intent') == 'irrelevant':
            return result
        return _clarify_without_changes(result, problem, step['section'])
    unsupported_controls = {
        'skip': 'I haven’t skipped this section. Say "skip" if you want to leave it out, or provide the requested details.',
        'go_back': 'I haven’t undone any details. Say "go back" if you want to undo the previous change.',
        'finish': 'I haven’t finished the interview. Say "finish" when you are ready to review your details.',
        'remove_information': 'I haven’t removed any details. Please identify exactly what you want to remove.',
    }
    if control.get('intent') in unsupported_controls:
        # Explicit controls are handled locally before Qwen. Extraction output
        # alone cannot authorize skipping, undoing, finishing or deleting facts.
        return _clarify_without_changes(result, unsupported_controls[control['intent']], step['section'])
    unsupported = []
    context = state.get('collected_data') or state.get('edit_updates') or {}
    existing = state.get('existing_cv') or {}
    active = _active_section(state)
    # A completion date is not evidence of a start date just because the same
    # year appears in the answer. Check labelled endpoints independently.
    stated_education = structured_education(message) or education_dates(message)[0]
    literal = {'personal': {'full_name', 'email', 'phone', 'location', 'linkedin', 'github', 'portfolio'},
               'education': {'institution', 'degree', 'field_of_study', 'grade'},
               'experience': {'company', 'role', 'job_title', 'technologies', 'employment_type'},
               'projects': {'name', 'technologies', 'url'}, 'certifications': {'name', 'issuer', 'url'},
               'languages': {'name', 'proficiency'}}
    def contextual(section, field, value):
        # Existing entry identities may be needed to identify an anonymous correction.
        if field not in ('name', 'company', 'role', 'job_title', 'institution', 'degree'):
            return False
        if section in ('languages', 'certifications') and active not in (None, 'review', section):
            return False
        if section == 'languages':
            if field != 'name' or not _proficiency_answer(message):
                return False
            pending = state.get('language_proficiency_pending') or []
            targets = pending if len(pending) == 1 else _selected_names(state, context, existing, section)
            return any(name and comparable(name) == comparable(value) for name in targets)
        if section == 'certifications':
            if state.get('edit_operation') == 'add':
                return False
            targets = _selected_names(state, context, existing, section)
            return any(name and comparable(name) == comparable(value) for name in targets)
        if state.get('mode') == 'edit_existing' and (
                state.get('edit_operation') == 'add' or state.get('edit_explicit_add')):
            # A new job/degree/project may reuse its own confirmed draft identity,
            # never a role or name copied from another saved or proposed entry.
            drafts = (state.get('edit_draft') or []) if state.get('edit_focus') == section else []
            return any(isinstance(entry, dict) and comparable(entry.get(field, '')) == comparable(value)
                       for entry in drafts)
        for entry in (context.get(section) or []) + (existing.get(section) or []):
            if isinstance(entry, dict) and comparable(entry.get(field, '')) == comparable(value):
                return True
        return False
    for section, updates in result.get('cv_updates', {}).items():
        if not updates:
            continue
        if section == 'summary' and active != 'summary' and not _summary_supplied(message, document):
            result['cv_updates'][section] = None
            unsupported.append('summary')
            continue
        if (state.get('mode') == 'edit_existing' and active in ('languages', 'certifications', 'skills')
                and section != active and not _explicit_section(section, message)):
            result['cv_updates'][section] = None
            unsupported.append(section)
            continue
        if section == 'skills':
            supported = [skill for skill in updates if mentioned(skill, message)]
            if len(supported) != len(updates): unsupported.append('skills')
            result['cv_updates'][section] = supported or None
            continue
        entries = [updates] if isinstance(updates, dict) else updates if isinstance(updates, list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            had_optional_name = section in ('languages', 'certifications') and bool(entry.get('name'))
            for field, value in list(entry.items()):
                if not value:
                    continue
                if section == 'personal' and not mentioned(value, message):
                    accepted_personal = {**(existing.get('personal') or {}), **(context.get('personal') or {})}
                    if comparable(accepted_personal.get(field, '')) == comparable(value):
                        entry.pop(field)
                        continue
                if section == 'projects' and field == 'name':
                    from chatbot.services.project_answers import is_profile_paragraph
                    if is_profile_paragraph(message) and not contextual(section, field, value):
                        entry.pop(field)
                        unsupported.append('projects.name (please provide a project title separately from your profile)')
                        continue
                if section == 'projects' and field == 'name' and re.fullmatch(
                        r'(?:a |an )?(?:django|python|react|javascript|web|mobile) (?:project|app|application)', str(value), re.I
                ) and not re.search(r'\b(?:called|named|title)\b', message, re.I):
                    entry.pop(field)
                    unsupported.append('projects.name (please confirm the actual title)')
                    continue
                if field in literal.get(section, set()):
                    values = value if isinstance(value, list) else [value]
                    supported = [v for v in values if mentioned(v, message) or contextual(section, field, v)]
                    if len(supported) != len(values):
                        unsupported.append(f'{section}.{field}')
                        if isinstance(value, list): entry[field] = supported or None
                        else: entry.pop(field)
                if (section == 'education' and field in ('start_date', 'end_date')
                        and any(key in stated_education for key in ('start_date', 'end_date'))
                        and field not in stated_education):
                    entry.pop(field, None)
                    unsupported.append(f'{section}.{field}')
                    continue
                if field in ('start_date', 'end_date', 'date') and re.match(r'^\d{4}', str(value)) and str(value)[:4] not in message:
                    entry.pop(field, None)
                    unsupported.append(f'{section}.{field}')
                    continue
                if field in ('start_date', 'end_date', 'date') and re.fullmatch(r'\d{4}-\d{2}', str(value)):
                    year, month = value.split('-')
                    month_words = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december')
                    if 1 <= int(month) <= 12 and year in message and value not in message and not any(word in message.lower() for word in (month_words[int(month)-1], month_words[int(month)-1][:3])):
                        entry[field] = year
                        unsupported.append(f'{section}.{field} month')
            if had_optional_name and not entry.get('name'):
                # A rejected name cannot leave an issuer/date/proficiency that
                # later attaches to another entry or advances the interview.
                entry.clear()
    if unsupported:
        if unsupported == ['summary']:
            warning = 'I left out a summary that wasn’t supplied or requested. Any other confirmed details were kept.'
        elif all(field.startswith('education.') for field in unsupported):
            warning = 'Let’s fill in only the education details you know.'
        elif all(field in ('experience.role', 'experience.job_title') for field in unsupported):
            kept_role = any(item.get('role') or item.get('job_title')
                            for item in result['cv_updates'].get('experience') or [])
            warning = ('Some suggested job titles weren’t clear in your reply. I kept the titles you provided.'
                       if kept_role else 'I couldn’t confirm a job title from that reply, so no job title was added.')
        elif all(field.startswith('experience.') for field in unsupported):
            warning = 'I’ve kept only the work details you provided. Let’s fill in the missing details.'
        else:
            warning = ('Please confirm extracted details that were not explicit in your answer: '
                       + ', '.join(dict.fromkeys(unsupported)) + '.')
        result.setdefault('_control', {})['evidence_warning'] = warning
    return result
