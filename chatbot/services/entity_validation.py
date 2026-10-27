"""Reject obvious non-entities without treating a role match as factual proof.

Unknown employers and international names are allowed. Ambiguous activities need
an explicit employer label; this does not establish that an employer exists.
"""
import re

from chatbot.services.content_handling import has_nonprofessional_claim, is_direct_abuse

_CREDENTIAL_WORD = re.compile(r'\b(?:certificate|certification|certified|diploma|qualification)\b', re.I)
_EXAM_CODE = re.compile(r'(?:[A-Z]{2,12}\d{0,6}|[A-Z0-9]{1,8}(?:[-/][A-Z0-9]{1,8})+|CS\d{2,3}[a-z]?)')
_ACTIVITY = re.compile(
    r'(?:(?:[\w\'’-]+\s+){0,3}(?:cooking|baking|gaming|fishing|gardening|singing|dancing|swimming|hiking)|'
    r'(?:playing|watching|eating|going to|travelling to|traveling to)\s+.{1,70})[.!]?', re.I)
_EMPLOYER_CUE = re.compile(
    r'\b(?:company|employer|organization|organisation|business)(?:\s+(?:name|is|was))?\s*[:=]|'
    r'\b(?:company|employer|organization|organisation|business)\s+(?:is|was|called|named)\b|'
    r'\b(?:work(?:ed)?|intern(?:ed)?)\s+(?:at|for)\b|\bas\s+.+?\s+at\b', re.I)
_NON_OCCUPATIONAL_LABEL = re.compile(
    r'(?:(?:(?:my|the)\s+)?(?:role|job title)\s*(?:is|:|=)\s*|'
    r"i(?:\s+am|['’]m|\s+was|\s+work(?:ed)?\s+as)\s+)?"
    r'(?:(?:a|an)\s+)?(?:murderer|serial killer|terrorist|robber|thief)[.!]?', re.I)
_DIRECT_HARM_CLAIM = re.compile(
    r'(?:(?:i|we)\s+(?:(?:am|are|was|were)\s+)?)?(?:murder(?:ed|ing)?|kill(?:ed|ing)?)\s+(?:of\s+)?'
    r'(?:people|persons?|humans?|civilians?)[.!]?', re.I)
_STUDY_CONTEXT = re.compile(
    r'\b(?:investigat\w*|profiling|prevent\w*|criminolog\w*|forensic\w*|'
    r'fiction\w*|literatur\w*|awareness|analysis|studies|psychology)\b', re.I)


def certificate_title_problem(value):
    """An issuer cannot turn a standalone person descriptor into a qualification."""
    subject = _CREDENTIAL_WORD.sub('', value).strip(' .,:;!?-\'"“”‘’')
    subject = re.sub(r'^(?:of|in|for)\s+', '', subject, flags=re.I)
    head = re.split(r'\s+(?:in|from|of)\s+', subject, maxsplit=1, flags=re.I)[0]
    if _NON_OCCUPATIONAL_LABEL.fullmatch(head) and not _STUDY_CONTEXT.search(value):
        return ('That describes a person rather than a qualification, so it was not added. '
                'An issuer, date or link does not establish a valid course title. '
                'Please provide the actual course or qualification title, or say "skip".')
    return None


def credential_code(value):
    return bool(_EXAM_CODE.fullmatch(value))


def clear_employer_label(value):
    """Recognize name-shaped short answers; delegate other prose to Qwen."""
    return bool(any(char.isupper() or (char.isalpha() and not char.isascii()) for char in value)
                or re.search(r'\b(?:company|systems|technologies|solutions|university|college|hospital|restaurant|studio|agency|inc|ltd|limited|llc|plc|corp|corporation)\.?$', value, re.I)
                or (len(value) <= 6 and any(char.isdigit() for char in value)))


def clear_job_title(value):
    """Common role shapes stay local; unfamiliar titles use model interpretation."""
    return bool(re.search(
        r'\b(?:developer|engineer|designer|analyst|manager|intern|assistant|associate|consultant|'
        r'specialist|director|officer|architect|administrator|lead|head|chief|founder|owner|'
        r'researcher|scientist|technician|teacher|professor|nurse|doctor|accountant|lawyer|'
        r'chef|cook|baker|server|driver|operator|mechanic|recruiter|writer|editor|artist|'
        r'trainer|coach|coordinator|representative|freelancer|supervisor|ceo|cto|cfo|coo|sre|sde|swe|qa)\b', value, re.I))


def obvious_noise(value):
    """High-confidence keyboard/random patterns, not an English dictionary."""
    value = _CREDENTIAL_WORD.sub('', value).strip(' :-')
    if credential_code(value):
        return False
    if re.fullmatch(r'[a-z0-9]+', value):
        groups = re.findall(r'\d+', value)
        letters = ''.join(char for char in value if char.isalpha())
        if len(value) >= 7 and len(groups) >= 2 and len(letters) >= 3:
            return True
        if groups and len(value) >= 6 and len(letters) >= 3 and not re.search('[aeiouy]', letters):
            return True
    lowered = value.casefold()
    return bool(re.fullmatch(r'(?:asdf[a-z]*|qwerty[a-z]*|zxcv[a-z]*|([a-z])\1{4,})', lowered)
                or re.fullmatch(r'[b-df-hj-np-tv-xz]{7,}', value))


def project_noise(value):
    """Shared project-field noise check, without requiring a word/tool catalogue."""
    value = value.strip().strip('.,;:!?')
    return bool(obvious_noise(value) or re.fullmatch(r'[a-z]{3,}\d{2,}[a-z]{1,2}', value, re.I))


def narrative_problem(section, field, value):
    fields = {'summary': ('summary', 'changes'), 'achievements': ('achievements', 'changes'),
              'experience': ('responsibilities', 'highlights', 'changes'),
              'projects': ('description', 'changes')}
    if field not in fields.get(section, ()):
        return None
    values = value if isinstance(value, list) else [value]
    if any(isinstance(item, str) and has_nonprofessional_claim(item) for item in values):
        return ('That reply includes claims of harming people, rather than professional CV details, '
                'so it was not added. Please describe your qualifications, skills or actual work. '
                'You can also skip this section.')
    return None


def entity_problem(section, field, value, message=''):
    problem = narrative_problem(section, field, value)
    if problem:
        return problem
    if section == 'certifications' and field == 'name' and isinstance(value, str):
        problem = certificate_title_problem(value)
        if problem:
            return problem
    if section == 'projects' and isinstance(value, str):
        from chatbot.services.optional_answers import optional_chatter
        if field == 'name':
            from chatbot.services.project_answers import explicitly_named_project
            # A short mixed code can be intentional; naming it establishes intent.
            if not explicitly_named_project(message, value) and (project_noise(value) or optional_chatter(value)):
                return ('I couldn’t recognize a clear project name in that reply, so it was not added. '
                        'Please give the actual project name, for example Task Tracker. '
                        'If that code is its real name, say "My project is called ...".')
        elif field == 'description':
            body = re.sub(r'^(?:(?:my|the)\s+)?(?:project\s+)?description\s*(?::|=|\bis\b)\s*',
                          '', value.strip(), flags=re.I)
            words = [word for word in re.split(r'[,;\s]+', body) if word]
            if (optional_chatter(body) or (words and all(project_noise(word) for word in words))
                    or not any(char.isalpha() for char in body)
                    or re.fullmatch(r'https?://\S+|\S+@\S+', body, re.I)):
                return ('I couldn’t recognize what this project does from that reply, so the description was not added. '
                        'Please describe the problem it solves or what it does in a short sentence.')
            from chatbot.services.field_validation import extract_skills, find_technologies
            tools = re.sub(r'^(?:i\s+)?(?:use|used|using|built with)\s+', '', body, flags=re.I)
            named_tools = find_technologies(tools)
            if named_tools and extract_skills(tools) == named_tools:
                return ('That looks like a list of tools rather than a project description. '
                        'Please describe what the project does; you can also provide its technologies.')
        elif field == 'technologies':
            if (optional_chatter(value) or any(project_noise(word) for word in re.split(r'[,;\s]+', value) if word)
                    or not any(char.isalpha() for char in value)
                    or re.fullmatch(r'https?://\S+|\S+@\S+', value, re.I)):
                return ('I couldn’t recognize a technology name in that text, so it was not added. '
                        'Please list the actual tools, languages or frameworks you used, separated by commas.')
    # These are whole-value type checks, never a ban on discussing crime in
    # legitimate investigative, medical, prevention or fictional work.
    if section == 'experience':
        if field in ('role', 'job_title') and isinstance(value, str) and _NON_OCCUPATIONAL_LABEL.fullmatch(value.strip()):
            return 'That is not a professional job title. Please give your actual role or say "cancel" to leave this entry.'
        if field in ('responsibilities', 'highlights'):
            duties = value if isinstance(value, list) else [value]
            if any(isinstance(duty, str) and (_DIRECT_HARM_CLAIM.fullmatch(duty.strip())
                   or _NON_OCCUPATIONAL_LABEL.fullmatch(duty.strip())) for duty in duties):
                return 'That describes harming people, rather than a professional work responsibility. Please describe your actual work, or say "cancel".'
            from chatbot.services.optional_answers import optional_chatter
            if any(isinstance(duty, str) and (project_noise(duty)
                   or optional_chatter(duty) or not any(char.isalpha() for char in duty)
                   or re.fullmatch(r'(?=.*[a-z])(?=.*\d)[a-z\d]+[.!]?', duty.strip(), re.I))
                   for duty in duties):
                return ('I couldn’t identify a work responsibility in that reply, so it was not added. '
                        'Please describe a task you performed, your contribution or a confirmed result.')
    labels = {'experience': ('company', 'role', 'job_title'),
              'certifications': ('name', 'issuer'), 'languages': ('name',)}
    if field not in labels.get(section, ()) or not isinstance(value, str):
        return None
    noun = 'certification title' if section == 'certifications' and field == 'name' else {
        'company': 'company or employer name', 'role': 'job title', 'job_title': 'job title',
        'issuer': 'issuing organization', 'name': 'language name',
    }.get(field, 'CV detail')
    if obvious_noise(value):
        return f'That looks like random text rather than a {noun}. Please enter the actual {noun}.'
    # Check whole abusive labels as well as the original conversational message.
    # A longer, explicitly quoted work/project title remains eligible.
    if is_direct_abuse(value) and len(value.split()) <= 5:
        return f'Please provide the actual {noun}; abusive messages are not CV details.'
    if re.fullmatch(r'(?:https?://\S+|\S+@\S+|\+?[\d ()-]{7,}|(?:19|20)\d{2}(?:-\d{2})?)', value, re.I):
        return f'Please give the actual {noun}. Contact details, dates and website URLs belong in their own fields.'
    if section == 'experience' and field in ('company', 'role', 'job_title'):
        explicit_employer = bool(_EMPLOYER_CUE.search(message))
        if _ACTIVITY.fullmatch(value) and not (field == 'company' and explicit_employer):
            return (f'That describes an activity or skill, rather than a {noun}. '
                    f'Please give your {noun}; for example "Company: Bitech Systems" or "Job title: Chef".')
        if field != 'company' or not explicit_employer:
            from chatbot.services.field_validation import extract_skills
            from chatbot.services.section_answers import LANGUAGES
            if extract_skills(value) or value.casefold() in {name.casefold() for name in LANGUAGES}:
                return ('That looks like a skill or language. Please name your employer, or clarify with "Company: NAME".'
                        if field == 'company' else 'That looks like a skill or language. Please give your job title, such as Backend Developer or Chef.')
        if field in ('role', 'job_title') and re.search(r'\b(?:inc|ltd|llc|company|technologies)\.?$', value, re.I):
            return 'That looks like an employer name. Please give your role or job title at that organization.'
    return None
