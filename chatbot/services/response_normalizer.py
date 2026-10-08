from chatbot.services.state_manager import (
    get_required_conversation_step,
)


QUESTION_MAP = {
    # ========================================================
    # Target
    # ========================================================

    ("target", "target_role"): (
        "What job role are you targeting with this CV?"
    ),

    ("target", "career_level"): (
        "What is your current career level: "
        "fresher, student, experienced, or other?"
    ),

    # ========================================================
    # Personal
    # ========================================================

    ("personal", "full_name"): (
        "What is your full name?"
    ),

    ("personal", "email"): (
        "What is your email address?"
    ),

    ("personal", "phone"): (
        "What is your phone number?"
    ),

    ("personal", "location"): (
        "What is your current city or location?"
    ),

    ("personal", "linkedin"): (
        "Do you have a LinkedIn profile URL "
        "you would like to include?"
    ),

    ("personal", "github"): (
        "Do you have a GitHub profile URL "
        "you would like to include?"
    ),

    ("personal", "portfolio"): (
        "Do you have a portfolio website "
        "you would like to include?"
    ),

    # ========================================================
    # Education
    # ========================================================

    ("education", "degree"): (
        "What degree did you complete?"
    ),

    ("education", "institution"): (
        "Which institution or university did you attend?"
    ),

    ("education", "field_of_study"): (
        "What was your field of study?"
    ),

    ("education", "end_date"): (
        "When did you graduate or expect to graduate?"
    ),

    # ========================================================
    # Skills
    # ========================================================

    ("skills", "skills"): (
        "What technical skills would you like "
        "to highlight?"
    ),

    # ========================================================
    # Experience
    # ========================================================

    ("experience", "company"): (
        "Which company or organization did you "
        "work or intern at?"
    ),

    ("experience", "role"): (
        "What was your role or job title?"
    ),

    ("experience", "responsibilities"): (
        "What were your main responsibilities "
        "in this role?"
    ),

    # ========================================================
    # Projects
    # ========================================================

    ("projects", "name"): (
        "What project would you like to include "
        "in your CV?"
    ),

    ("projects", "description"): (
        "Could you briefly describe what this "
        "project does?"
    ),

    ("projects", "technologies"): (
        "What technologies did you use for "
        "this project?"
    ),

    # ========================================================
    # Summary
    # ========================================================

    ("summary", "summary"): (
        "Please provide a brief professional "
        "summary for your CV."
    ),
}


def has_cv_updates(ai_response):
    cv_updates = (
        ai_response.get("cv_updates")
        or {}
    )

    for value in cv_updates.values():
        if value not in (
            None,
            "",
            [],
            {},
        ):
            return True

    return False


def normalize_ai_response(
    *,
    ai_response,
    new_state,
):
    """
    Gemini extracts information.
    M5 state machine determines what comes next.
    """

    required_step = (
        get_required_conversation_step(
            new_state
        )
    )

    section = required_step[
        "section"
    ]

    field = required_step[
        "field"
    ]

    # ========================================================
    # Completion
    # ========================================================

    if (
        section == "review"
        and ai_response.get(
            "next_action"
        ) == "complete"
    ):
        ai_response[
            "section"
        ] = "review"

        ai_response[
            "intent"
        ] = "complete"

        ai_response[
            "next_action"
        ] = "complete"

        # Keep Gemini's completion message.
        return ai_response

    # ========================================================
    # Review
    # ========================================================

    if section == "review":
        ai_response[
            "section"
        ] = "review"

        if has_cv_updates(
            ai_response
        ):
            ai_response[
                "intent"
            ] = "update_cv"
        else:
            ai_response[
                "intent"
            ] = (
                "collect_information"
            )

        ai_response[
            "next_action"
        ] = "review"

        ai_response[
            "assistant_message"
        ] = (
            "Please review your CV information. "
            "If everything looks correct, tell me "
            "to finish the CV interview."
        )

        return ai_response

    # ========================================================
    # Normal collection
    # ========================================================

    ai_response[
        "section"
    ] = section

    if has_cv_updates(
        ai_response
    ):
        ai_response[
            "intent"
        ] = "update_cv"
    else:
        ai_response[
            "intent"
        ] = (
            "collect_information"
        )

    ai_response[
        "next_action"
    ] = "ask_question"

    question = QUESTION_MAP.get(
        (
            section,
            field,
        )
    )

    if question:
        ai_response[
            "assistant_message"
        ] = question

    else:
        ai_response[
            "assistant_message"
        ] = (
            f"Could you provide more "
            f"information about your "
            f"{section}?"
        )

    return ai_response