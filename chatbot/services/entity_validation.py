"""Reject obvious non-entities without treating a role match as factual proof.

Unknown employers and international names are allowed. Ambiguous activities need
an explicit employer label; this does not establish that an employer exists.
"""
import re

from chatbot.services.content_handling import is_direct_abuse

_CREDENTIAL_WORD = re.compile(r'\b(?:certificate|certification|certified|diploma|qualification)\b', re.I)
_EXAM_CODE = re.compile(r'(?:[A-Z]{2,12}\d{0,6}|[A-Z0-9]{1,8}(?:[-/][A-Z0-9]{1,8})+|CS\d{2,3}[a-z]?)')
_ACTIVITY = re.compile(
    r'(?:(?:[\w\'’-]+\s+){0,3}(?:cooking|baking|gaming|fishing|gardening|singing|dancing|swimming|hiking)|'
    r'(?:playing|watching|eating|going to|travelling to|traveling to)\s+.{1,70})[.!]?', re.I)
_EMPLOYER_CUE = re.compile(
    r'\b(?:company|employer|organization|organisation|business)(?:\s+(?:name|is|was))?\s*[:=]|'
    r'\b(?:company|employer|organization|organisation|business)\s+(?:is|was|called|named)\b|'
    r'\b(?:work(?:ed)?|intern(?:ed)?)\s+(?:at|for)\b|\bas\s+.+?\s+at\b', re.I)


def credential_code(value):
    return bool(_EXAM_CODE.fullmatch(value))


def clear_employer_label(value):
    """Recognize name-shaped short answers; delegate other prose to Qwen."""
    return bool(any(char.isupper() or (char.isalpha() and not char.isascii()) for char in value)
                or re.search(r'\b(?:company|systems|technologies|solutions|university|college|hospital|restaurant|studio|agency|inc|ltd|llc)\.?$', value, re.I)
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


def entity_problem(section, field, value, message=''):
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
