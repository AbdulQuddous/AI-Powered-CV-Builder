"""Recover the evidenced profile-as-projects bug without combining real projects."""
from copy import deepcopy

from chatbot.services.project_answers import is_profile_paragraph, project_title, project_description
from chatbot.services.content_handling import is_direct_abuse, is_self_harm_concern, is_conversational_question


def _candidate(session):
    state = session.conversation_state
    entries = state.get('collected_data', {}).get('projects') or []
    return (session.status in ('active', 'completed') and not session.cv_id
            and state.get('mode') != 'edit_existing' and not state.get('chat_saved_cv_id')
            and not state.get('edit_saved_cv_id') and not state.get('pending_entry')
            and len(entries) > 1 and all(isinstance(item, dict) and item.get('name')
                                       and not item.get('description') for item in entries))


def _evidence(session):
    from chatbot.services.response_normalizer import QUESTION_MAP
    from chatbot.services.section_answers import section_request
    from chatbot.services.local_extractor import is_finish_command, is_exact_skip_command
    expected = session.conversation_state['collected_data']['projects']
    previous, user, title, profile = None, None, None, None
    replacement, matched = None, False
    for message in session.messages.order_by('created_at', 'id').values('role', 'content', 'cv_updates'):
        if message['role'] == 'user':
            user = message['content']
            if previous and QUESTION_MAP[('projects', 'name')] in previous:
                title = project_title(user) or title
            if matched:
                request = section_request(user)
                if request and request[0] == 'projects':
                    return None
                if previous and QUESTION_MAP[('projects', 'description')] in previous:
                    if (not is_profile_paragraph(user) and not is_direct_abuse(user)
                            and not is_self_harm_concern(user) and not is_conversational_question(user)
                            and not is_finish_command(user) and not is_exact_skip_command(user) and '?' not in user):
                        answer = project_description(user)
                        replacement['description'] = answer['description']
                        technologies = replacement.setdefault('technologies', [])
                        technologies.extend(value for value in answer.get('technologies', []) if value not in technologies)
            continue
        if (user and title and is_profile_paragraph(user)
                and (message['cv_updates'] or {}).get('projects') == expected):
            # Exact equality excludes edited entries and other accepted projects.
            profile, replacement, matched = user, {'name': title}, True
        previous = message['content']
    return (expected, profile, replacement) if matched else None


def _clean(state, expected, profile, replacement):
    from chatbot.services.collection_memory import sync_project_progress
    if state.get('collected_data', {}).get('projects') != expected:
        return False
    data = state['collected_data']
    data['projects'] = [deepcopy(replacement)]
    if not data.get('summary'):
        data['summary'] = profile
        if 'summary' not in state.setdefault('completed_sections', []):
            state['completed_sections'].append('summary')
        state['missing_sections'] = [section for section in state.get('missing_sections', []) if section != 'summary']
    for key in ('pending_field', 'pending_selection'):
        if (state.get(key) or {}).get('section') == 'projects':
            state.pop(key, None)
    sync_project_progress(state, 0)
    statuses = state.setdefault('field_status', {})
    for path in list(statuses):
        if path.startswith('projects.'):
            statuses.pop(path)
    statuses.update({f'projects.0.{key}': 'answered' for key, value in replacement.items() if value})
    state['invalid_fields'] = [path for path, value in statuses.items() if value == 'invalid']
    state.pop('approved_review_changes', None)
    state.pop('review_decisions', None)
    return True


def repair_project_profile_split(session):
    if not _candidate(session):
        return False
    from django.db import transaction
    from chatbot.models import ChatSession, ChatMessage
    from chatbot.services.question_engine import next_step, question, recommendations
    with transaction.atomic():
        locked = ChatSession.objects.select_for_update().get(pk=session.pk, user_id=session.user_id)
        if not _candidate(locked):
            session.refresh_from_db()
            return False
        evidence = _evidence(locked)
        if not evidence:
            return False
        state = deepcopy(locked.conversation_state)
        _clean(state, *evidence)
        if state.get('undo_state'):
            _clean(state['undo_state'], *evidence)
        state['recommendations'] = recommendations(state)
        locked.current_section = state['current_section'] = next_step(state)['section']
        locked.conversation_state = state
        locked.save(update_fields=['conversation_state', 'current_section', 'updated_at'])
        ChatMessage.objects.create(session=locked, role='assistant', intent='clarify_information',
            section=locked.current_section, next_action='ask_question', content=(
                'I separated the profile paragraph from your project and restored the title and details you supplied. '
                'Your original messages are preserved. Please review the collected draft. ' + question(state)))
        session.refresh_from_db()
        return True
