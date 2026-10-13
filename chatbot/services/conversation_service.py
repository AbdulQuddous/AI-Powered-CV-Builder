from django.conf import settings
from django.db import transaction

from chatbot.models import (
    ChatMessage,
    ChatSession,
)

from chatbot.services.gemini_client import (
    GeminiClient,
)

from chatbot.services.prompt_builder import (
    build_messages,
)

from chatbot.services.response_normalizer import (
    normalize_ai_response,
    sanitize_ai_response_for_state,
)

from chatbot.services.conversation_router import (
    try_local_extraction,
)

from chatbot.services.state_manager import (
    get_initial_state,
    get_required_conversation_step,
    update_state,
)


INITIAL_ASSISTANT_MESSAGE = (
    "Let's build your CV. "
    "What role are you targeting?"
)


def create_chat_session(
    *,
    user,
    cv_id=None,
):
    state = get_initial_state()

    with transaction.atomic():
        session = ChatSession.objects.create(
            user=user,
            cv_id=cv_id,

            status=(
                ChatSession.Status.ACTIVE
            ),

            current_section="target",

            conversation_state=state,

            model_name=(
                settings.GEMINI_MODEL
            ),
        )

        ChatMessage.objects.create(
            session=session,

            role=(
                ChatMessage.Role.ASSISTANT
            ),

            content=(
                INITIAL_ASSISTANT_MESSAGE
            ),

            intent="collect_information",

            section="target",

            cv_updates={},

            next_action="ask_question",
        )

    return session


def process_user_message(
    *,
    session,
    user_message,
):
    # =========================================
    # 1. Session must be active
    # =========================================

    if (
        session.status
        != ChatSession.Status.ACTIVE
    ):
        raise ValueError(
            "Chat session is not active."
        )

    # =========================================
    # 2. Determine what backend needs next
    # =========================================

    required_step = (
        get_required_conversation_step(
            session.conversation_state
        )
    )

    # =========================================
    # 3. Try zero-cost deterministic extraction
    #    wrapped in fail-safe so local parsing
    #    can never break the conversation.
    # =========================================

    local_response = None

    try:
        local_response = (
            try_local_extraction(
                required_step=required_step,
                user_message=user_message,
            )
        )
    except Exception:
        # Local optimization must NEVER
        # break the conversation.
        local_response = None

    # =========================================
    # 4. Fall back to Gemini only when local
    #    parsing cannot confidently understand
    #    the message.
    # =========================================

    if local_response is not None:
        ai_response = local_response

    else:
        messages = build_messages(
            session=session,
            pending_user_message=(
                user_message
            ),
        )

        client = GeminiClient()

        ai_response = client.generate(
            messages=messages
        )

    # =========================================
    # 4b. Sanitize BEFORE state mutation
    # =========================================
    # Irrelevant messages must never change CV
    # state. Gemini may occasionally return
    # unwanted updates even when intent is
    # "irrelevant", so the backend enforces
    # this rule before update_state() runs.
    # =========================================

    ai_response = (
        sanitize_ai_response_for_state(
            ai_response
        )
    )

    # =========================================
    # 5. Update deterministic state
    # =========================================

    new_state = update_state(
        session.conversation_state,
        ai_response,
    )

    # =========================================
    # 6. Backend decides NEXT step
    # =========================================

    ai_response = normalize_ai_response(
        ai_response=ai_response,
        new_state=new_state,
    )

    # =========================================
    # 7. Persist atomically
    # =========================================

    with transaction.atomic():
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

        session.conversation_state = (
            new_state
        )

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