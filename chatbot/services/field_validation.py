"""Conversational field rules. M10 remains the persisted document authority."""
import re
import unicodedata
import phonenumbers
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator

from chatbot.services.conversation_router import empty_ai_response
from cvs.validation import validator
from chatbot.services.structured_answers import looks_structured, parse_structured
from chatbot.services.education_answers import reversed_date_range


ALIASES = {'drf': 'Django REST Framework', 'js': 'JavaScript', 'javascript': 'JavaScript', 'nodejs': 'Node.js',
           'node.js': 'Node.js', 'nextjs': 'Next.js', 'next.js': 'Next.js',
           'postgres': 'PostgreSQL', 'postgresql': 'PostgreSQL', 'restapi': 'REST APIs',
           'restapis': 'REST APIs', 'rest api': 'REST APIs', 'rest apis': 'REST APIs',
           'django restframework': 'Django REST Framework', 'django/drf': 'Django REST Framework',
           'djnago': 'Django'}
KNOWN_SKILLS = ['Django REST Framework', 'REST APIs', 'Python', 'Django', 'PostgreSQL',
                'JavaScript', 'TypeScript', 'HTML', 'CSS', 'React', 'MySQL', 'Git',
                'C++', 'C#', 'Node.js', '.NET', 'DRF', 'JS', 'Bootstrap', 'Docker', 'Gemini',
                'Next.js', 'NextJS', 'Flask', 'JWT', 'Whisper', 'MediaPipe', 'Sentence Transformers', 'GitHub', 'AI', 'NLP',
                'Postman', 'Java', 'SQL', 'AWS', 'Linux', 'Excel', 'Communication']


def find_technologies(text):
    """Find literal technology mentions in prose; a title/framework never implies a stack."""
    terms = {value.casefold(): value for value in KNOWN_SKILLS if value not in ('Communication', 'Excel')}
    terms.update(ALIASES)
    spans, matches = [], []
    for term in sorted(terms, key=len, reverse=True):
        pattern = r'(?<![\w+#])' + re.escape(term) + r'(?![\w+#])'
        for match in re.finditer(pattern, text, re.I):
            if any(match.start() < end and match.end() > start for start, end in spans):
                continue
            spans.append(match.span()); matches.append((match.start(), terms[term]))
    # A clearly named tool at the end of an explicit "using NAME" clause can be
    # retained even outside the vocabulary. Require a capitalized name and a
    # clause boundary; ordinary prose such as "using browser recordings" or
    # "using New York data" must not become technology labels.
    named_tool = (r'\b(?i:using)\s+(?P<tool>[A-Z][\w+#/-]*(?:\.[\w+#/-]+)*'
                  r'(?:\s+[A-Z][\w+#/-]*(?:\.[\w+#/-]+)*)*)(?=\s*(?:[,;.!?)]|$))')
    for match in re.finditer(named_tool, text):
        start, end = match.span('tool')
        if not any(start < known_end and end > known_start for known_start, known_end in spans):
            spans.append((start, end)); matches.append((start, match['tool']))
    return unique_skills([value for _, value in sorted(matches)])


def unique_skills(values):
    result, seen = [], set()
    canonical = {name.casefold(): name for name in KNOWN_SKILLS}
    for raw in values:
        key = raw.strip().casefold()
        value = ALIASES.get(key, canonical.get(key, raw.strip()))
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return result


def extract_skills(text):
    """Accept lists; parse prose only when every listed skill is explicitly named."""
    if looks_structured(text):
        value = parse_structured(text)
        if isinstance(value, dict) and set(value) == {'skills'}:
            value = value['skills']
        if isinstance(value, dict):
            groups = list(value.values())
            if not groups or not all(isinstance(group, list) for group in groups):
                return None
            value = [skill for group in groups for skill in group]
        if not isinstance(value, list) or not value or not all(isinstance(skill, str) and skill.strip() for skill in value):
            return None
        return unique_skills(value)
    text = text.strip().rstrip('.')
    text = re.sub(r'^(?:i\s+(?:would\s+)?like\s+to\s+(?:highlight|include|add)|'
                  r'(?:my\s+)?(?:technical\s+)?skills\s+(?:are|include)|'
                  r'i\s+want\s+to\s+highlight)\s*:?\s*', '', text, flags=re.I)
    # An explicit list introduction is grammar, not the first technology. Unknown
    # tools in a comma-separated list still retain their user-supplied names.
    text = re.sub(r'^(?:(?:i\s+)?(?:use|used|using)\s+)?(?:the\s+)?following\s+'
                  r'(?:technologies|tools|skills|tech stack)\s*:?\s*', '', text, flags=re.I)
    if text.casefold() in ('next', 'node'):
        return [{'next': 'Next.js', 'node': 'Node.js'}[text.casefold()]]
    if ',' in text and not re.search(r'\b(?:I|my|worked|know|using)\b', text, re.I):
        # Bare Next/Node are framework names only in an explicit skills list.
        listed = re.split(r',|;|\band\b', text)
        listed = [{'next': 'Next.js', 'node': 'Node.js'}.get(item.strip().casefold(), item) for item in listed]
        return unique_skills(listed)
    found = []
    remaining = text
    terms = {value.casefold(): value for value in KNOWN_SKILLS}
    terms.update(ALIASES)
    for skill in sorted(terms, key=len, reverse=True):
        pattern = r'(?<![\w+#.])' + re.escape(skill) + r'(?![\w+#.])'
        matches = list(re.finditer(pattern, remaining, re.I))
        if matches:
            found.extend((match.start(), terms[skill]) for match in matches)
            remaining = re.sub(pattern, lambda match: ' ' * len(match[0]), remaining, flags=re.I)
    if not remaining.strip(' ,;') or re.fullmatch(
            r'[\s,;]*(?:(?:I|know|and|worked|with|have|experience|in|also|use|using|skills|include|am|skilled|at|the|following)[\s,;]*)+', remaining, re.I):
        # Preserve the user's order instead of the vocabulary order.
        return unique_skills([value for _, value in sorted(found)])
    return None


def normalise_skill_list(values):
    """Split packed known lists while retaining unknown compound technology names."""
    result = []
    for value in values:
        result.extend(extract_skills(value) or [value])
    return unique_skills(result)


def validate_value(field, value):
    if not isinstance(value, str):
        raise ValidationError('Please provide text for this field.')
    value = value.strip()
    if not value:
        raise ValidationError('Please provide a value, or skip this optional field.')
    if len(value) > (5000 if field in ('summary', 'description', 'responsibilities', 'highlights', 'achievements') else 255):
        raise ValidationError('Please shorten this answer before continuing.')
    if field == 'full_name':
        if not any(c.isalpha() for c in value) or any(
                not (unicodedata.category(c).startswith(('L', 'M')) or c in " -'’.·") for c in value):
            raise ValidationError("Please enter your name using letters, spaces, hyphens or apostrophes.")
    elif field == 'email':
        if value.endswith('@'):
            raise ValidationError('Your email appears incomplete. Please enter the part after @.')
        try:
            EmailValidator()(value)
        except ValidationError:
            raise ValidationError("That doesn't look like a valid email address. Include @ and a valid domain, for example name@gmail.com.")
    elif field in ('company', 'role', 'job_title', 'degree', 'institution', 'field_of_study') and (
            re.fullmatch(r'(?:https?://|www\.)\S+', value, re.I) or looks_structured(value)):
        raise ValidationError('Please provide the actual name or title, rather than a website URL or unparsed JSON.')
    elif field == 'phone':
        # Conservative international format check; no claim of number ownership.
        # National numbers outside the explicitly supported PK mobile format need a country code.
        if not re.fullmatch(r'\+?[0-9][0-9 ()-]*', value):
            raise ValidationError('Please enter a phone number with digits and, for international numbers, a +country code.')
        digits = re.sub(r'\D', '', value)
        if not (re.fullmatch(r'03\d{9}', digits) or (value.startswith('+') and 8 <= len(digits) <= 15 and digits[0] != '0')):
            raise ValidationError('Please include your country code (for example +923001234567), or a Pakistani mobile such as 03001234567.')
        parsed = None
        try:
            parsed = phonenumbers.parse(value, None if value.startswith('+') else 'PK')
            if not phonenumbers.is_valid_number(parsed):
                raise phonenumbers.NumberParseException(0, 'Invalid number')
        except phonenumbers.NumberParseException:
            country = f'+{parsed.country_code}' if parsed is not None else 'the supplied country code'
            raise ValidationError(f'That number does not match the numbering rules for {country}. Check the area code and subscriber number, or provide another number with its country code.')
    elif field in ('url', 'linkedin', 'github', 'portfolio'):
        try:
            URLValidator(schemes=['http', 'https'])(value)
        except ValidationError:
            raise ValidationError('Please provide a complete http:// or https:// URL, or skip it.')
    elif field in ('degree', 'institution', 'field_of_study'):
        if not any(character.isalpha() for character in value):
            raise ValidationError('Please provide the academic name or title; give dates as start date and graduation date.')
        if field == 'institution':
            from chatbot.services.education_answers import parse_education
            parsed = parse_education(value)
            if parsed and set(parsed) <= {'start_date', 'end_date'}:
                raise ValidationError('Please provide the institution or university name. Dates are collected separately.')
    elif field in ('start_date', 'end_date', 'date'):
        if field == 'end_date' and value.lower() in ('present', 'current', 'ongoing'):
            return 'present'
        if not re.fullmatch(r'(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?', value):
            raise ValidationError('Please enter a date as YYYY-MM (for example 2026-06), or a year if the month is unknown.')
    elif field == 'grade':
        match = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)', value)
        if match:
            score, scale = map(float, match.groups())
            if scale <= 0 or score < 0 or score > scale:
                raise ValidationError('Your grade exceeds its scale. Please check it, or omit the optional grade.')
        elif re.fullmatch(r'\d+(?:\.\d+)?', value):
            raise ValidationError('What grading scale does this use? Enter, for example, 3.5/4.0, or skip the optional grade.')
        elif value.endswith('%'):
            try:
                if not 0 <= float(value[:-1]) <= 100:
                    raise ValueError
            except ValueError:
                raise ValidationError('Please enter a percentage between 0 and 100, or omit the grade.')
    return value


def _explicit_name(message, value):
    prefix = r'(?:(?:my (?:full )?name is|i am called)|(?:change|update|edit) my (?:full )?name to)\s+'
    if re.match(r'^' + prefix + re.escape(value) + r'(?=$|[.,;]|\s+and\s+)', message.strip(), re.I):
        return True
    if looks_structured(message):
        document = parse_structured(message)
        if isinstance(document, dict):
            personal = document.get('personal', document)
            return isinstance(personal, dict) and personal.get('full_name') == value
    return False


def validated_updates(response, state, *, user_message=''):
    """Keep valid sibling fields; reject unknown keys, invalid dates and contacts.

    This also runs after local extraction, so provider output never bypasses rules.
    Returns response, friendly errors, and field status paths.
    """
    response = deepcopy(response)
    errors, statuses = [], {}
    schema = validator().schema['properties']
    accepted = state.get('collected_data') or state.get('edit_updates') or {}
    for section, value in list(response.get('cv_updates', {}).items()):
        if value is None:
            continue
        if section not in schema or section in ('schema_version', 'meta'):
            response['cv_updates'].pop(section)
            errors.append('The extracted section is unsupported. Please clarify your answer.')
            continue
        if section == 'personal':
            entries = [value] if isinstance(value, dict) else []
        elif section in ('education', 'experience', 'projects', 'languages', 'certifications'):
            entries = value if isinstance(value, list) else []
        else:
            entries = None
        if entries is not None:
            clean_entries = []
            for index, item in enumerate(entries):
                confirmation = state.get('date_confirmation_pending') or {}
                if confirmation.get('section') == section:
                    index = confirmation['index']
                if isinstance(item, str) and section in ('languages', 'certifications'):
                    item = {'name': item}
                if not isinstance(item, dict):
                    errors.append(f'Please clarify the {section} entry.')
                    continue
                clean = {}
                allowed = set(schema[section].get('properties', {}) if section == 'personal' else schema[section]['items']['properties'])
                if section == 'experience':
                    allowed |= {'role', 'responsibilities', 'duration', 'employment_type', 'technologies'}
                if section == 'projects':
                    allowed |= {'contribution', 'features', 'github_url', 'live_demo'}
                if section == 'education':
                    allowed.add('is_current')  # Source state only: M10 has no study-status field.
                for field, raw in item.items():
                    path = f'{section}.{index}.{field}' if section != 'personal' else f'personal.{field}'
                    if raw in (None, '', []):
                        continue
                    try:
                        if field not in allowed:
                            raise ValidationError('The extracted field is unsupported. Please clarify it.')
                        if section == 'personal' and field == 'full_name' and isinstance(raw, str):
                            from chatbot.services.local_extractor import is_skip_command
                            if is_skip_command(raw) and not _explicit_name(user_message, raw.strip()):
                                raise ValidationError('That looks like a skip request. Your full name is required; please enter your name.')
                        from chatbot.services.entity_validation import entity_problem
                        # Technology strings may contain both valid and invalid
                        # names. Split them before checking each individual tool.
                        problem = (None if section == 'projects' and field == 'technologies' else
                                   entity_problem(section, field, raw, user_message))
                        if problem:
                            raise ValidationError(problem)
                        if field == 'is_current':
                            if type(raw) is not bool:
                                raise ValidationError('Please confirm whether this is current.')
                            clean[field] = raw
                        elif section == 'projects' and field == 'technologies':
                            tools, tool_errors = [], []
                            for item_value in raw if isinstance(raw, list) else [raw]:
                                try:
                                    tool_text = validate_value(field, item_value)
                                    values = normalise_skill_list(re.split(r'[;\n]', tool_text))
                                except ValidationError as exc:
                                    tool_errors.extend(exc.messages)
                                    continue
                                for tool in values:
                                    problem = entity_problem(section, field, tool, user_message)
                                    if problem:
                                        if problem not in tool_errors:
                                            tool_errors.append(problem)
                                    else:
                                        tools.append(tool)
                            if not tools:
                                errors.extend(tool_errors or [
                                    'No technologies were added. Please list the actual tools, languages or frameworks you used.'])
                                statuses[path] = 'invalid'
                                continue
                            clean[field] = unique_skills(tools)
                            if tool_errors:
                                errors.append('Some entries did not look like technology names and were not added. '
                                              'The recognized tools were kept.')
                        elif isinstance(raw, list):
                            if field not in ('responsibilities', 'highlights', 'technologies', 'features'):
                                raise ValidationError('Please provide a single text value for this field.')
                            clean[field] = [validate_value(field, entry) for entry in raw]
                            if field == 'technologies':
                                clean[field] = normalise_skill_list(clean[field])
                        elif field == 'technologies' and isinstance(raw, str):
                            clean[field] = normalise_skill_list([validate_value(field, raw)])
                        else:
                            clean[field] = validate_value(field, raw)
                        if field == 'proficiency' and clean[field] not in ('basic', 'conversational', 'professional', 'fluent', 'native'):
                            raise ValidationError('Choose basic, conversational, professional, fluent or native proficiency.')
                        statuses[path] = 'answered'
                    except ValidationError as exc:
                        clean.pop(field, None)
                        statuses[path] = 'invalid'
                        errors.extend(exc.messages)
                previous = accepted.get(section) or []
                old = previous[index] if isinstance(previous, list) and len(previous) > index else {}
                # Existing focus is the reliable context for anonymous followups.
                if state.get('edit_focus') == section and state.get('edit_draft'):
                    old = state['edit_draft'][-1]
                if state.get('pending_entry', {}).get('section') == section:
                    old = state['pending_entry']['draft']
                pending = state.get('pending_field') or {}
                if pending.get('section') == section and 'index' in pending:
                    existing = state.get('existing_cv', {}).get(section) or []
                    if 0 <= pending['index'] < len(existing):
                        old = existing[pending['index']]
                merged = {**old, **clean}
                start, end = merged.get('start_date'), merged.get('end_date')
                if reversed_date_range(start, end):
                    for date_field in ('start_date', 'end_date'):
                        if date_field in clean:
                            clean.pop(date_field)
                            statuses[f'{section}.{index}.{date_field}'] = 'invalid'
                    errors.append('Your ending date is earlier than your starting date. Could you check the dates?')
                # Ongoing study can have an expected graduation date. Current
                # employment retains its separate, stricter end-date rule.
                if section == 'experience' and merged.get('is_current') and end and end != 'present':
                    clean.pop('end_date', None)
                    statuses[f'{section}.{index}.end_date'] = 'invalid'
                    errors.append('A current job cannot also have an ending date. Please confirm whether you still work there or provide its ending date.')
                if section in ('certifications', 'languages', 'projects') and item.get('name') and not clean.get('name'):
                    for field in clean:
                        statuses[f'{section}.{index}.{field}'] = 'needs_clarification'
                    clean = {}
                if clean:
                    clean_entries.append(clean)
            response['cv_updates'][section] = (clean_entries[0] if clean_entries else None) if section == 'personal' else (clean_entries or None)
        elif section == 'achievements' and isinstance(value, list):
            from chatbot.services.entity_validation import entity_problem
            clean = []
            for index, item in enumerate(value):
                path = f'achievements.{index}.achievements'
                try:
                    problem = entity_problem(section, section, item, user_message)
                    if problem:
                        raise ValidationError(problem)
                    clean.append(validate_value(section, item))
                    statuses[path] = 'answered'
                except ValidationError as exc:
                    statuses[path] = 'invalid'
                    errors.extend(exc.messages)
            response['cv_updates'][section] = clean or None
        elif section in ('skills', 'achievements'):
            try:
                if not isinstance(value, list):
                    raise ValidationError('Please provide a list.')
                response['cv_updates'][section] = [validate_value(section, item) for item in value]
                if section == 'skills':
                    response['cv_updates'][section] = normalise_skill_list(response['cv_updates'][section])
                    if len(response['cv_updates'][section]) > 100:
                        raise ValidationError('M10 supports 100 skills. Please choose which skills to display; your source message is retained.')
            except ValidationError as exc:
                response['cv_updates'][section] = None
                errors.extend(exc.messages)
        elif section == 'summary':
            try:
                from chatbot.services.entity_validation import entity_problem
                problem = entity_problem(section, section, value, user_message)
                if problem:
                    raise ValidationError(problem)
                response['cv_updates'][section] = validate_value('summary', value)
                statuses['summary.summary'] = 'answered'
            except ValidationError as exc:
                response['cv_updates'][section] = None
                statuses['summary.summary'] = 'invalid'
                errors.extend(exc.messages)
    metadata = response.get('state_updates') or {}
    if metadata.get('career_level') not in (None, '', 'student', 'fresher', 'experienced', 'other'):
        metadata['career_level'] = None
        errors.append('Please choose a supported career level.')
    if metadata.get('target_role'):
        try:
            metadata['target_role'] = validate_value('target_role', metadata['target_role'])
        except ValidationError as exc:
            metadata['target_role'] = None
            errors.extend(exc.messages)
    return response, list(dict.fromkeys(errors)), statuses
