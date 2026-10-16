from django.conf import settings
from django.db import transaction

from chatbot.models import (
    ChatMessage,
    ChatSession,
)

from chatbot.services.qwen_client import QwenClient, build_qwen_messages
from chatbot.services.field_validation import validated_updates
from chatbot.services.message_routing import route_message, apply_control, present_response
from chatbot.services.question_engine import question, recommendations
from chatbot.services.collection_memory import merge_collection_entries, repair_split_education, sync_project_progress, FIELD_STATES
from chatbot.services.content_handling import repair_hostile_experience
from chatbot.services.optional_section_recovery import repair_optional_answers
from chatbot.services.project_recovery import repair_project_profile_split
from copy import deepcopy

from chatbot.services.response_normalizer import sanitize_ai_response_for_state
from chatbot.services.state_manager import (
    get_initial_state,
    get_required_conversation_step,
    update_state,
)
from chatbot.services.existing_cv_conversation import (
    INTRO, initial_edit_state, owned_populated_cv, prepare_existing_session,
)
from rest_framework.exceptions import APIException, ValidationError


class ConversationConflict(APIException):
    status_code = 409
    default_code = 'chat_session_conflict'
    default_detail = 'Conversation changed while processing. Reload the latest messages before retrying.'


INITIAL_ASSISTANT_MESSAGE = (
    "Let's build your CV. "
    "What role are you targeting?"
)


def create_chat_session(
    *,
    user,
    cv_id=None,
    initial_values=None,
):
    state = get_initial_state()
    existing_cv = owned_populated_cv(user, cv_id)
    if existing_cv:
        state = initial_edit_state(state, existing_cv)
    if initial_values:
        state.update(initial_values)
    if state.get('career_level') == 'student':
        state.update(career_level='other', question_profile='student')
    step = get_required_conversation_step(state)
    state['current_section'] = step['section']
    initial_message = INTRO if existing_cv else (
        question(state)
        if initial_values else INITIAL_ASSISTANT_MESSAGE
    )

    with transaction.atomic():
        session = ChatSession.objects.create(
            user=user,
            cv_id=cv_id,

            status=(
                ChatSession.Status.ACTIVE
            ),

            current_section=state['current_section'],

            conversation_state=state,

            model_name=(
                settings.CHAT_QWEN_MODEL
            ),
        )

        ChatMessage.objects.create(
            session=session,

            role=(
                ChatMessage.Role.ASSISTANT
            ),

            content=(
                initial_message
            ),

            intent="collect_information",

            section=state['current_section'],

            cv_updates={},

            next_action="ask_question",
        )

    return session


def process_user_message(
    *,
    session,
    user_message,
    request_id=None,
    expected_updated_at=None,
):
    # Retries with a client receipt return the committed response, including after completion.
    if request_id:
        receipt = session.conversation_state.get('message_receipts', {}).get(str(request_id))
        if receipt:
            if receipt['text'] != user_message:
                raise ConversationConflict('This message ID was already used for different text.')
            return session.messages.get(pk=receipt['assistant_id'])
    if session.status != ChatSession.Status.ACTIVE:
        raise ValueError('Chat session is not active.')
    prepare_existing_session(session)
    repair_hostile_experience(session)
    repair_optional_answers(session)
    repair_project_profile_split(session)
    if expected_updated_at and session.updated_at != expected_updated_at:
        raise ConversationConflict()
    original_updated_at = session.updated_at
    from chatbot.services.state_manager import ensure_state
    state = ensure_state(session.conversation_state)
    # Upgrade collection memory from existing proposals without discarding legacy history.
    if state.get('mode') != 'edit_existing' and 'collected_data' not in state:
        from cvs.chat_import import collected_updates
        state['collected_data'] = collected_updates(session)
    state = repair_split_education(session, state)
    session.conversation_state = state
    required_step = get_required_conversation_step(state)
    ai_response = route_message(state, user_message, required_step)
    if ai_response is None:
        ai_response = QwenClient().generate(build_qwen_messages(session, user_message))
        from chatbot.services.extraction_guard import guard_extraction
        ai_response = guard_extraction(ai_response, user_message, state)
        if (ai_response.get('_control') or {}).get('intent') == 'finish':
            ai_response['_control']['intent'] = 'clarification'
    ai_response = sanitize_ai_response_for_state(ai_response)
    pending = state.get('pending_field') or {}
    if 'index' in pending and (ai_response.get('cv_updates') or {}).get(pending['section']):
        ai_response['_control'] = {'intent': 'entry_patch', 'section': pending['section'], 'index': pending['index']}
    action = (ai_response.get('_control') or {}).get('intent')
    blocked = ai_response.get('intent') == 'irrelevant' or action in (
        'off_topic', 'inappropriate', 'support_needed', 'cv_question', 'show_progress', 'clarification')
    if blocked:
        ai_response['cv_updates'] = empty_updates()
        ai_response['state_updates'] = {}
    ai_response, errors, statuses = validated_updates(ai_response, state)
    uncertain = (ai_response.get('_control') or {}).get('uncertain_fields') or []
    for path in uncertain:
        statuses[path] = 'needs_clarification'
    if (ai_response.get('_control') or {}).get('requires_clarification'):
        errors.append('Please clarify ' + (', '.join(uncertain) if uncertain else 'the details you would like to include') + '. I have kept the confirmed information.')
    if (ai_response.get('_control') or {}).get('evidence_warning'):
        errors.append(ai_response['_control']['evidence_warning'])
    if action == 'go_back':
        previous = state.get('undo_state')
        new_state = deepcopy(previous) if previous else deepcopy(state)
        notice = 'Last change undone.' if previous else 'There is no earlier change to undo. You can say change my email, for example.'
        new_state['message_count'] = state.get('message_count', 0) + 1
    else:
        state_response = deepcopy(ai_response)
        if action == 'entry_patch':
            state_response['cv_updates'][ai_response['_control']['section']] = None
        new_state = update_state(state, state_response, user_message=user_message if not blocked else None)
        new_state, notice = apply_control(new_state, ai_response)
        if new_state.get('mode') != 'edit_existing':
            from cvs.chat_import import IDENTITIES
            collected = new_state.setdefault('collected_data', {'personal': {}})
            for section, value in ai_response['cv_updates'].items():
                if not value:
                    continue
                if section in new_state.get('skipped_sections', []):
                    new_state['skipped_sections'].remove(section)
                if section == 'personal':
                    collected.setdefault(section, {}).update(value)
                elif section in IDENTITIES:
                    pending_entry = new_state.get('pending_entry')
                    if pending_entry and pending_entry['section'] == section:
                        for item in value:
                            pending_entry['draft'].update(item)
                        from chatbot.services.existing_cv_conversation import FIELDS
                        if all(pending_entry['draft'].get(key) for key in FIELDS[section]):
                            collected.setdefault(section, []).append(deepcopy(pending_entry['draft']))
                            new_state.pop('pending_entry', None)
                            if section == 'projects':
                                sync_project_progress(new_state, len(collected[section]) - 1)
                        continue
                    project_index = None
                    if section == 'projects':
                        project_index = new_state.get('collection_entry_indexes', {}).get(section)
                        if project_index is None and len(collected.get(section) or []) == 1:
                            project_index = 0
                    try:
                        collected[section] = merge_collection_entries(collected.get(section, []), value, section, required_step, index=project_index)
                        if section == 'projects':
                            if len(value) == 1 and value[0].get('name'):
                                matches = [i for i, entry in enumerate(collected[section])
                                           if entry.get('name', '').casefold() == value[0]['name'].casefold()]
                                project_index = matches[0] if len(matches) == 1 else None
                            sync_project_progress(new_state, project_index)
                    except ValidationError:
                        errors.append('Please identify which entry these details belong to.')
                        if section == 'projects':
                            new_state['pending_selection'] = {'section': section, 'field': required_step['field'],
                                'source': 'collection', 'updates': [
                                    {key: deepcopy(item) for key, item in entry.items() if key != 'name'}
                                    for entry in value]}
                        ai_response['cv_updates'][section] = None
                        # Failed merges cannot mark unsaved fields answered or advance the interview.
                        field_key = FIELD_STATES.get(section)
                        if field_key:
                            new_state[field_key] = deepcopy(state[field_key])
                        completed = set(new_state['completed_sections'])
                        if section in state.get('completed_sections', []):
                            completed.add(section)
                        else:
                            completed.discard(section)
                        new_state['completed_sections'] = sorted(completed)
                        missing = set(new_state.get('missing_sections', []))
                        if section in state.get('missing_sections', []):
                            missing.add(section)
                        else:
                            missing.discard(section)
                        new_state['missing_sections'] = sorted(missing)
                        for path in statuses:
                            if path.startswith(section + '.'):
                                statuses[path] = 'needs_clarification'
                elif isinstance(value, list):
                    saved = collected.setdefault(section, [])
                    saved.extend(item for item in value if item not in saved)
                else:
                    collected[section] = value
        # Corrections to target metadata are intentional; model cannot set IDs or completion.
        for key in ('target_role', 'career_level'):
            value = (ai_response.get('state_updates') or {}).get(key)
            if value:
                new_state[key] = 'other' if value == 'student' else value
                if value == 'student':
                    new_state['question_profile'] = 'student'
        if not blocked and action not in ('finish', 'show_progress'):
            undo = deepcopy(state)
            undo.pop('undo_state', None)
            undo.pop('message_receipts', None)
            new_state['undo_state'] = undo
    field_status = new_state.setdefault('field_status', {})
    field_status.update(statuses)
    for skipped in (ai_response.get('_control') or {}).get('skip_fields', []):
        if skipped in new_state.get('skipped_sections', []) or new_state.get('personal_fields', {}).get(skipped) == 'skipped':
            field_status[skipped] = 'skipped'
    new_state['invalid_fields'] = [key for key, value in field_status.items() if value == 'invalid']
    if errors:
        invalid = next((path for path, value in statuses.items() if value == 'invalid'), None)
        if invalid:
            bits = invalid.split('.')
            new_state['pending_field'] = {'section': bits[0], 'field': bits[-1]}
            entry_action = ai_response.get('_control') or {}
            if 'index' in pending and pending.get('section') == bits[0]:
                new_state['pending_field']['index'] = pending['index']
            elif entry_action.get('intent') == 'entry_patch':
                new_state['pending_field']['index'] = entry_action['index']
    elif new_state.get('pending_field') and any(ai_response['cv_updates'].values()):
        pending = new_state['pending_field']
        value = ai_response['cv_updates'].get(pending['section'])
        field = pending['field']
        answered = value and (field == pending['section'] or field == 'changes'
            or isinstance(value, dict) and value.get(field)
            or isinstance(value, list) and any(isinstance(item, dict) and item.get(field) for item in value))
        if answered:
            new_state.pop('pending_field', None)
    new_state['recommendations'] = recommendations(new_state)
    if action == 'finish' and get_required_conversation_step(new_state)['section'] == 'review':
        # Completion depends on the built M10 document, never on a provider's complete flag.
        from cvs.chat_import import build_chat_document
        session.conversation_state = new_state
        try:
            build_chat_document(session, current=new_state.get('existing_cv'))
        except ValidationError:
            errors.append('The draft cannot yet be saved. Select at most five experiences and check required structure and dates.')
    ai_response = present_response(ai_response, new_state, errors, notice)
    new_state['current_section'] = get_required_conversation_step(new_state)['section']

    # =========================================
    # 7. Persist atomically
    # =========================================

    with transaction.atomic():
        locked = ChatSession.objects.select_for_update().get(pk=session.pk, user_id=session.user_id)
        if request_id:
            receipt = locked.conversation_state.get('message_receipts', {}).get(str(request_id))
            if receipt:
                if receipt['text'] != user_message:
                    raise ConversationConflict()
                return locked.messages.get(pk=receipt['assistant_id'])
        if locked.status != ChatSession.Status.ACTIVE or locked.updated_at != original_updated_at:
            raise ConversationConflict()
        # User message
        ChatMessage.objects.create(
            session=session,

            role=ChatMessage.Role.USER,

            content=user_message,
        )

        # Assistant message
        assistant_message = (
            ChatMessage.objects.create(
                session=session,

                role=(
                    ChatMessage.Role.ASSISTANT
                ),

                content=(
                    ai_response[
                        "assistant_message"
                    ]
                ),

                intent=(
                    ai_response[
                        "intent"
                    ]
                ),

                section=(
                    ai_response[
                        "section"
                    ]
                ),

                cv_updates=(
                    ai_response[
                        "cv_updates"
                    ]
                ),

                next_action=(
                    ai_response[
                        "next_action"
                    ]
                ),
            )
        )

        # =====================================
        # State section must match backend flow
        # =====================================

        session.current_section = (
            new_state.get(
                "current_section",
                ai_response["section"],
            )
        )

        if request_id:
            receipts = deepcopy(locked.conversation_state.get('message_receipts', {}))
            receipts[str(request_id)] = {'text': user_message, 'assistant_id': assistant_message.pk}
            new_state['message_receipts'] = dict(list(receipts.items())[-20:])
        session.conversation_state = new_state

        # =====================================
        # Final completion
        # =====================================

        if (
            ai_response["next_action"]
            == "complete"
        ):
            session.status = (
                ChatSession.Status.COMPLETED
            )

        session.save(
            update_fields=[
                "current_section",
                "conversation_state",
                "status",
                "updated_at",
            ]
        )

    return assistant_message


def empty_updates():
    from chatbot.services.conversation_router import empty_ai_response
    return empty_ai_response()['cv_updates']
