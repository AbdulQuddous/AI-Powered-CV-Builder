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

    # --- grouped contact first ---
    ("personal", "email"): (
        "Please share your contact information: "
        "your email address, phone number, "
        "and current city."
    ),

    # --- targeted follow-ups if email alone was given ---
    ("personal", "phone"): (
        "Please also share your phone number "
        "and current city."
    ),

    ("personal", "location"): (
        "What is your current city or location?"
    ),

    # --- grouped professional links first ---
    ("personal", "linkedin"): (
        "Please share your LinkedIn, GitHub, "
        "and portfolio links if you have them. "
        "You can also tell me which ones "
        "you don't have."
    ),

    ("personal", "github"): (
        "Please share your GitHub and portfolio "
        "links if available, or tell me which "
        "ones you don't have."
    ),

    ("personal", "portfolio"): (
        "Do you have a portfolio website? "
        "You can share it or say no portfolio."
    ),

    # ========================================================
    # Education
    # ========================================================

    # --- grouped education first ---
    ("education", "degree"): (
        "Please share your education details: "
        "degree, field of study, university, "
        "and graduation year. You can also "
        "include your start year and grade "
        "or CGPA if available."
    ),

    # --- targeted follow-ups ---
    ("education", "institution"): (
        "Which institution or university "
        "did you attend?"
    ),

    ("education", "field_of_study"): (
        "What was your field of study?"
    ),

    ("education", "end_date"): (
        "When did you graduate or when "
        "do you expect to graduate?"
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

    # --- grouped experience first ---
    ("experience", "company"): (
        "Please tell me about your most relevant "
        "job or internship: company, role, "
        "dates or location if available, and "
        "your main responsibilities."
    ),

    # --- targeted follow-ups ---
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

    # --- grouped project first ---
    ("projects", "name"): (
        "Tell me about a project you'd like "
        "to include: its name, what it does, "
        "and the main technologies you used."
    ),

    # --- targeted follow-ups ---
    ("projects", "description"): (
        "Could you briefly describe what "
        "this project does?"
    ),

    ("projects", "technologies"): (
        "What technologies did you use "
        "for this project?"
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


def sanitize_ai_response_for_state(
    ai_response,
):
    """
    Irrelevant messages must never change CV state.

    Gemini may occasionally return unwanted updates even
    when intent is irrelevant, so the backend enforces
    this rule.
    """

    if (
        ai_response.get("intent")
        != "irrelevant"
    ):
        return ai_response

    ai_response["state_updates"] = {
        "target_role": None,
        "career_level": None,
        "skipped_personal_fields": [],
    }

    ai_response["cv_updates"] = {
        "personal": None,
        "summary": None,
        "skills": None,
        "education": None,
        "experience": None,
        "projects": None,
        "certifications": None,
        "achievements": None,
        "languages": None,
    }

    return ai_response


def normalize_ai_response(
    *,
    ai_response,
    new_state,
):
    """
    Gemini extracts information.
    M5 state machine determines what comes next.
    """
    if isinstance(new_state, dict) and new_state.get('mode') == 'edit_existing':
        from chatbot.services.existing_cv_conversation import normalize_edit_response
        return normalize_edit_response(ai_response, new_state)

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
    # Irrelevant message
    # ========================================================
    # User said something unrelated to CV building.
    # Do not advance state; repeat the pending question
    # with a short notice.

    if (
        ai_response.get("intent")
        == "irrelevant"
    ):
        question = QUESTION_MAP.get(
            (
                section,
                field,
            )
        )

        if not question:
            question = (
                f"Could you provide more "
                f"information about your "
                f"{section}?"
            )

        ai_response[
            "section"
        ] = section

        ai_response[
            "intent"
        ] = "irrelevant"

        ai_response[
            "next_action"
        ] = (
            "ask_question"
        )

        ai_response[
            "assistant_message"
        ] = (
            "That doesn't seem related to "
            "your CV. Let's continue: "
            f"{question}"
        )

        return ai_response

    # ========================================================
    # Completion
    # ========================================================

    if (
        section == "review"
        and ai_response.get(
            "next_action"
        )
        == "complete"
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
