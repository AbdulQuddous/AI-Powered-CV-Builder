"""Recognize direct abusive utterances without rejecting quoted workplace content."""
import re
from copy import deepcopy

# Match conversational forms, not occurrences of a word inside a CV description.
_PREFIX = r'(?:(?:o|oh|hey|please|just|well|ok|okay)\b[\s,!:.?\-]+){0,3}'
_INSULT = r'(?:idiot|stupid|useless|dumb|moron|dumbass|asshole|bastard)\b'
_FILLER = r'(?:(?:a|an|so|really|just|such|fucking)\s+){0,3}'
_DIRECT = re.compile(r'^' + _PREFIX + r'(?:'
    r'shut[\s\-]*up\b|'
    r'(?:fuck|screw)\s+(?:you|u)\b|'
    r'(?:you(?:\x27re)?|u)\s+(?:(?:are|r)\s+)?' + _FILLER + _INSULT + r'|'
    r'(?:are|r)\s+(?:you|u)\s+' + _FILLER + _INSULT + r'|'
    r'i\s+(?:will|want\s+to)\s+(?:kill|hurt)\s+(?:you|u)\b)', re.I)
_EXCLAMATION = re.compile(r'^' + _PREFIX + r'(?:'
    r'what\s+(?:(?:a|the)\s+)?(?:fuck|shit)|'
    r'wtf|stfu|fuck|shit|bullshit|idiot|go\s+to\s+hell)[.!?]*$', re.I)


def is_direct_abuse(text):
    text = ' '.join(text.strip().replace('’', "'").split())
    return bool(_DIRECT.match(text) or _EXCLAMATION.fullmatch(text))


def is_conversational_question(text):
    """Questions and messages addressing the assistant need interpretation."""
    return bool(re.match(r'^(?:(?:what|who|why|how|when|where|you|your|u)\b|'
                         r'(?:are|r|do|did|can|could|will|would)\s+(?:you|u)\b)', text, re.I))


def is_self_harm_concern(text):
    """Recognize first-person distress; quoted project/workplace text is not a crisis turn."""
    text = ' '.join(text.strip().replace('’', "'").split())
    return bool(re.match(
        r"^(?:should i|i(?:'m| am)?(?: going to| thinking about| want to| will| might| should| feel)?)\s+"
        r'(?:(?:commit|comit)\s+(?:suicide|sucide)|(?:kill|hurt|harm)\s+myself|end\s+my\s+life|die|suicidal)\b',
        text, re.I))


def _normalise(text):
    return ' '.join(text.casefold().split()).rstrip('.!?')


def _values(entries):
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in ('company', 'role', 'job_title', 'responsibilities', 'highlights'):
            value = entry.get(field)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, str):
                    yield field, item


def _clean_state(state, rejected):
    from chatbot.services.state_manager import get_default_experience_fields, EXPERIENCE_FIELD_ORDER
    entries = state.get('collected_data', {}).get('experience') or []
    cleaned = []
    for entry in entries:
        if not isinstance(entry, dict):
            cleaned.append(entry)
            continue
        entry = deepcopy(entry)
        for field, value in list(entry.items()):
            if isinstance(value, str) and (field, _normalise(value)) in rejected:
                entry.pop(field)
            elif isinstance(value, list):
                kept = [item for item in value if not isinstance(item, str) or (field, _normalise(item)) not in rejected]
                if kept != value:
                    if kept:
                        entry[field] = kept
                    else:
                        entry.pop(field)
        if entry:
            cleaned.append(entry)
    if cleaned == entries:
        return False
    state['collected_data']['experience'] = cleaned
    fields = get_default_experience_fields()
    for entry in cleaned:
        if not isinstance(entry, dict):
            continue
        for field in fields:
            if entry.get(field):
                fields[field] = 'collected'
    state['experience_fields'] = fields
    statuses = state.setdefault('field_status', {})
    for path in list(statuses):
        if path.startswith('experience.'):
            statuses.pop(path)
    for index, entry in enumerate(cleaned):
        if isinstance(entry, dict):
            for field, value in entry.items():
                if value not in (None, '', [], {}):
                    statuses[f'experience.{index}.{field}'] = 'answered'
    state['invalid_fields'] = [path for path, status in statuses.items() if status == 'invalid']
    complete = all(fields[field] == 'collected' for field in EXPERIENCE_FIELD_ORDER)
    completed, missing = set(state.get('completed_sections', [])), set(state.get('missing_sections', []))
    if complete:
        completed.add('experience'); missing.discard('experience')
    else:
        completed.discard('experience'); missing.add('experience')
        pending = state.get('pending_field') or {}
        if ('experience' not in state.get('skipped_sections', []) and not state.get('pending_entry')
                and pending.get('section', 'experience') == 'experience'):
            state['pending_field'] = {'section': 'experience', 'field': next(field for field in EXPERIENCE_FIELD_ORDER if fields[field] == 'missing')}
    state['completed_sections'], state['missing_sections'] = sorted(completed), sorted(missing)
    state.pop('approved_review_changes', None)
    state.pop('review_decisions', None)
    return True


def repair_hostile_experience(session):
    """Exclude only old facts proven copied from standalone hostile user turns.

    Runs lazily on owner-scoped resume/next turn. Saved CVs, quoted content, chat
    history and unverified facts are untouched. Locking preserves concurrent edits.
    """
    def eligible(obj):
        state = obj.conversation_state
        return (obj.status == 'active' and not obj.cv_id and state.get('mode') != 'edit_existing'
                and not state.get('chat_saved_cv_id')
                and any(is_direct_abuse(value) for _, value in _values(state.get('collected_data', {}).get('experience') or [])))
    if not eligible(session):
        return False
    from django.db import transaction
    from chatbot.models import ChatSession, ChatMessage
    from chatbot.services.question_engine import question, next_step
    with transaction.atomic():
        locked = ChatSession.objects.select_for_update().get(pk=session.pk, user_id=session.user_id)
        if not eligible(locked):
            session.refresh_from_db()
            return False
        rejected, user_message = set(), None
        for message in locked.messages.order_by('created_at', 'id').values('role', 'content', 'cv_updates'):
            if message['role'] == 'user':
                user_message = message['content']
            elif user_message and is_direct_abuse(user_message):
                for field, value in _values((message['cv_updates'] or {}).get('experience') or []):
                    if _normalise(value) == _normalise(user_message):
                        rejected.add((field, _normalise(value)))
        state = deepcopy(locked.conversation_state)
        if not rejected or not _clean_state(state, rejected):
            return False
        if state.get('undo_state'):
            _clean_state(state['undo_state'], rejected)
        locked.conversation_state = state
        locked.current_section = state['current_section'] = next_step(state)['section']
        locked.save(update_fields=['conversation_state', 'current_section', 'updated_at'])
        ChatMessage.objects.create(session=locked, role='assistant', intent='clarify_information',
            section=locked.current_section, next_action='ask_question',
            content='I excluded earlier non-CV messages that were mistakenly stored as experience. Your other details are preserved. ' + question(state))
        session.refresh_from_db()
        return True
