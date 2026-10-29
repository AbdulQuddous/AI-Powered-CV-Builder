"""Keep a project's literal title, descriptive facts and professional profile separate."""
import re

from chatbot.services.field_validation import find_technologies, unique_skills

_PROJECT_NAME_PREFIX = (
    r'(?:(?:(?:my|the)\s+)?project(?:\s+(?:name|title))?\s*'
    r'(?:[:=]\s*|is\s+(?:(?:called|named)\s+)?)|'
    r"(?:it\s+is|it's)\s+(?:called|named)\s+)")
_PROJECT_WORK = re.compile(
    r'\b(?:built|created|developed|designed|implemented|prototyped|researched|investigated|'
    r'evaluated|analysed|analyzed)\b|'
    r'\b(?:app|application|website|tool|platform|system|portal|research|study)\s+'
    r'(?:that|which|to|for|of|on)\b', re.I)


def explicitly_named_project(message, value):
    """An unusual title needs naming intent, never a known-project catalogue."""
    if re.match(r'^' + _PROJECT_NAME_PREFIX + re.escape(value)
                + r'(?=$|[.!;,]|\s+(?:and|using|with)\b)', message.strip(), re.I):
        return True
    from chatbot.services.structured_answers import looks_structured, parse_structured
    if looks_structured(message):
        data = parse_structured(message)
        if isinstance(data, dict):
            data = data.get('projects', [data])
        if isinstance(data, list):
            return any(isinstance(entry, dict) and isinstance(entry.get('name'), str)
                       and entry['name'].strip().casefold() == value.strip().casefold() for entry in data)
    return False


def is_profile_paragraph(text):
    first_sentence = re.split(r'\.\s', text, maxsplit=1)[0]
    return (len(text) > 180 and bool(re.search(r'\b(?:graduate|intern|professional|developer|engineer)\b', first_sentence, re.I))
            and bool(re.search(r'\b(?:hands.on experience|years? of experience|comfortable with|strong foundation|worked on|independent .+ projects)\b', text, re.I)))


def project_title(text):
    """Unwrap explicit naming requests, preserving spelling instead of inventing a title."""
    text = text.strip().rstrip('.!')
    if is_profile_paragraph(text):
        return None
    text = re.sub(r"^(?:(?:i\s+(?:want|would like)\s+to\s+)?add\s+(?:(?:a|an|another|a new|more)\s+)?|"
                  + _PROJECT_NAME_PREFIX + ')', '', text, flags=re.I).strip()
    if (not text or len(text) > 160 or len(text.split()) > 20 or re.search(r'[?;•\n]|\b(?:using|uses|builds|built|developed|worked|graduated|have|makes|manages)\b', text, re.I)):
        return None
    # Short naming answers can contain conjunctions; first-person prose needs interpretation.
    if re.match(r'^(?:i|my|can|could|what|how|please)\b', text, re.I):
        return None
    return text


def project_title_problem(value, message=''):
    """A qualification-shaped reply needs project context, not a topic blacklist."""
    from chatbot.services.local_extractor import _one_typing_error
    words = list(re.finditer(r'[a-z]+', value.casefold()))
    credential = False
    for index, word in enumerate(words):
        if not any(_one_typing_error(word[0], term)
                   for term in ('certificate', 'certification', 'diploma', 'qualification')):
            continue
        following = words[index + 1][0] if index + 1 < len(words) else ''
        if (not following or following in ('of', 'in', 'on', 'for', 'from', 'issued', 'issuer')
                or value[word.end():].lstrip().startswith(':')):
            credential = True
            break
    if not credential:
        return None
    # Only user-supplied work/research context can resolve the ambiguity. A
    # provider's invented description or another JSON entry cannot establish it.
    evidence = message
    from chatbot.services.structured_answers import looks_structured, parse_structured
    if looks_structured(message):
        data = parse_structured(message)
        entries = data.get('projects', [data]) if isinstance(data, dict) else data
        entries = entries if isinstance(entries, list) else []
        evidence = ' '.join(entry.get('description', '') for entry in entries or []
                            if isinstance(entry, dict) and isinstance(entry.get('description'), str)
                            and str(entry.get('name', '')).casefold() == value.casefold())
    else:
        evidence = re.sub(re.escape(value), '', evidence, count=1, flags=re.I)
    if _PROJECT_WORK.search(evidence):
        return None
    return ('That sounds like a certification or qualification rather than a project, so it was not added. '
            'Please share a project name and briefly say what you built or researched. '
            'If this is your actual project title, include its purpose to clarify. You can also say "skip".')


def project_description(text):
    entry = {'description': text}
    technologies = find_technologies(text)
    if technologies:
        entry['technologies'] = technologies
    return entry


def literal_project_details(text, title):
    """Retain an explicit title/purpose pair when extraction omits its tail."""
    prefix = (r'(?:(?:(?:can|could|would)\s+you\s+(?:please\s+)?|please\s+)?'
              r'(?:add|include|record)\s+|' + _PROJECT_NAME_PREFIX + ')')
    match = re.fullmatch(r'(?:' + prefix + r')?' + re.escape(title)
                         + r'\s*[,\n:—–]\s*(.+)', text.strip(), re.I | re.S)
    if not match:
        return None
    body = match[1].strip().rstrip('?').strip()
    if not _PROJECT_WORK.search(body):
        return None
    return project_description(body)


def grouped_project(text):
    """Keep a CV-style heading and its supplied bullet/line description together."""
    parts = re.split(r'\s*•\s*|\r?\n+', text.strip(), maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        return None
    heading, body = parts[0].strip(), parts[1].strip(' •\r\n')
    date = re.search(r'\s+((?:19|20)\d{2}(?:-\d{2})?)$', heading)
    title = project_title(heading[:date.start()] if date else heading)
    if not title:
        return None
    entry = {'name': title, **project_description(body)}
    if date:
        # M10 has no project date field. Retain it in the source description.
        entry['description'] = date[1] + ' · ' + entry['description']
    return entry


def retain_project_tools(response, state, step):
    """A description adds mentioned tools; an explicit tools answer can replace them."""
    if step['section'] != 'projects' or step['field'] != 'description':
        return
    drafts = state.get('pending_entry') or {}
    if drafts.get('section') == 'projects':
        previous = drafts.get('draft') or {}
    elif state.get('mode') == 'edit_existing' and state.get('edit_focus') == 'projects':
        entries = state.get('edit_draft') or []
        previous = entries[0] if len(entries) == 1 else {}
    else:
        entries = (state.get('collected_data') or {}).get('projects') or []
        index = (state.get('pending_field') or {}).get('index',
                    (state.get('collection_entry_indexes') or {}).get('projects'))
        previous = (entries[index] if type(index) is int and 0 <= index < len(entries)
                    else entries[0] if len(entries) == 1 else {})
    for entry in response.get('cv_updates', {}).get('projects') or []:
        if (entry.get('description') and entry.get('technologies') and previous.get('technologies')
                and (not entry.get('name') or entry['name'].casefold() == previous.get('name', '').casefold())):
            entry['technologies'] = unique_skills(previous['technologies'] + entry['technologies'])
