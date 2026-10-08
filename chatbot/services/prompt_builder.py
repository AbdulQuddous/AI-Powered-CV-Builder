import json

from chatbot.prompts.cv_assistant import (
    SYSTEM_PROMPT,
)
from chatbot.services.state_manager import (
    get_required_conversation_step,
)


MAX_HISTORY_MESSAGES = 20


def build_messages(
    session,
    pending_user_message,
):
    """
    Build provider-independent messages for Groq.

    M5 controls:
    - current workflow section
    - required field/section

    Groq controls:
    - natural language
    - information extraction
    - next question wording

    The pending user message has not yet been
    persisted when this function executes.
    """

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    state = (
        session.conversation_state
        or {}
    )

    # =========================================
    # Current M5 state
    # =========================================

    state_context = {
        "conversation_state": state,
        "cv_id": session.cv_id,
    }

    messages.append(
        {
            "role": "system",
            "content": (
                "CURRENT M5 CONVERSATION "
                "STATE:\n"
                + json.dumps(
                    state_context,
                    ensure_ascii=False,
                )
            ),
        }
    )

    # =========================================
    # Deterministic conversation control
    # =========================================

    required_step = (
        get_required_conversation_step(
            state
        )
    )

    section = required_step["section"]
    field = required_step["field"]

    messages.append(
        {
            "role": "system",
            "content": (
                "STRICT M5 CONVERSATION "
                "CONTROL:\n\n"

                f"Required section: "
                f"'{section}'\n"

                f"Required field/item: "
                f"'{field}'\n\n"

                "M5 has already determined "
                "which part of the CV must be "
                "handled next.\n"

                "You MUST follow this workflow "
                "instruction.\n\n"

                "The latest user message appears "
                "after the conversation history.\n\n"

                "RULE 1:\n"
                "First inspect whether the newest "
                "user message answers or updates "
                "the required field or section.\n\n"

                "RULE 2:\n"
                "If it provides useful information, "
                "extract that information into "
                "cv_updates.\n\n"

                "RULE 3:\n"
                "Then ask EXACTLY ONE useful "
                "question for the next missing "
                "piece of information appropriate "
                "to the workflow.\n\n"

                "RULE 4:\n"
                "Do not jump to another unrelated "
                "CV section.\n\n"

                "RULE 5:\n"
                "Do not skip required sections.\n\n"

                "RULE 6:\n"
                "If the required item is a section "
                "name such as 'education', "
                "'skills', 'experience', "
                "'projects', or 'summary', ask "
                "exactly ONE useful question for "
                "that section.\n\n"

                "Examples:\n\n"

                "education -> ask one education "
                "question\n"

                "skills -> ask for relevant "
                "technical skills\n"

                "experience -> ask one experience "
                "question\n"

                "projects -> ask one project "
                "question\n"

                "summary -> ask for or help "
                "construct the professional "
                "summary\n\n"

                "RULE 7:\n"
                "The response section should "
                "correspond to the section the "
                "assistant is currently asking "
                "about.\n\n"

                "RULE 8:\n"
                "If next_action is "
                "'ask_question', the "
                "assistant_message MUST actually "
                "contain exactly one question.\n\n"

                "RULE 9:\n"
                "Never return next_action="
                "'ask_question' with a statement "
                "such as 'Got it.' and no "
                "question.\n"
            ),
        }
    )

    # =========================================
    # Conversation history
    # =========================================

    history = list(
        session.messages.order_by(
            "-created_at"
        )[:MAX_HISTORY_MESSAGES]
    )

    history.reverse()

    for message in history:
        messages.append(
            {
                "role": message.role,
                "content": message.content,
            }
        )

    # =========================================
    # New pending user message
    # =========================================

    messages.append(
        {
            "role": "user",
            "content": (
                pending_user_message
            ),
        }
    )

    return messages