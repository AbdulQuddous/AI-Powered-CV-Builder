from chatbot.services.local_extractor import (
    extract_exact_career_level,
    is_exact_skip_command,
    is_finish_command,
)


OPTIONAL_PERSONAL_FIELDS = {
    "linkedin",
    "github",
    "portfolio",
}


def empty_ai_response():
    """
    Return the exact response shape expected by M5.
    """

    return {
        "assistant_message": "",
        "intent": "collect_information",
        "section": "",
        "state_updates": {
            "target_role": None,
            "career_level": None,
            "skipped_personal_fields": [],
        },
        "cv_updates": {
            "personal": None,
            "summary": None,
            "skills": None,
            "education": None,
            "experience": None,
            "projects": None,
            "certifications": None,
            "achievements": None,
            "languages": None,
        },
        "next_action": "ask_question",
    }


def try_local_extraction(
    *,
    required_step,
    user_message,
):
    """
    Handle only very safe deterministic cases.

    Return:
        response dict -> handled locally

        None -> message is not safe to understand
                locally, so Gemini must handle it.
    """

    section = required_step[
        "section"
    ]

    field = required_step[
        "field"
    ]

    # ========================================================
    # 1. Final finish command
    # ========================================================

    if (
        section == "review"
        and is_finish_command(
            user_message
        )
    ):
        response = (
            empty_ai_response()
        )

        response["assistant_message"] = (
            "Your CV interview is complete. "
            "Your information is ready for "
            "final CV generation."
        )

        response["intent"] = "complete"
        response["section"] = "review"

        response["next_action"] = (
            "complete"
        )

        return response

    # ========================================================
    # 2. Exact career level
    # ========================================================

    if (
        section == "target"
        and field == "career_level"
    ):
        career_level = (
            extract_exact_career_level(
                user_message
            )
        )

        if career_level:
            response = (
                empty_ai_response()
            )

            response["section"] = (
                "target"
            )

            response[
                "state_updates"
            ][
                "career_level"
            ] = career_level

            return response

    # ========================================================
    # 3. Exact skip of current optional personal field
    # ========================================================

    if (
        section == "personal"
        and field
        in OPTIONAL_PERSONAL_FIELDS
        and is_exact_skip_command(
            user_message
        )
    ):
        response = (
            empty_ai_response()
        )

        response["section"] = (
            "personal"
        )

        response[
            "state_updates"
        ][
            "skipped_personal_fields"
        ] = [
            field
        ]

        return response

    # ========================================================
    # Everything else -> Gemini
    # ========================================================

    return None