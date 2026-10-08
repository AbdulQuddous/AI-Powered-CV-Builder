from copy import deepcopy


CV_SECTIONS = [
    "personal",
    "summary",
    "skills",
    "education",
    "experience",
    "projects",
    "certifications",
    "achievements",
    "languages",
]


CORE_SECTION_ORDER = [
    "education",
    "skills",
    "experience",
    "projects",
    "summary",
]


PERSONAL_FIELD_ORDER = [
    "full_name",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
    "portfolio",
]


OPTIONAL_PERSONAL_FIELDS = {
    "linkedin",
    "github",
    "portfolio",
}


def get_default_personal_fields():
    return {
        "full_name": "missing",
        "email": "missing",
        "phone": "missing",
        "location": "missing",
        "linkedin": "missing",
        "github": "missing",
        "portfolio": "missing",
    }


def get_initial_state():
    return {
        "target_role": None,
        "career_level": None,

        "current_section": "target",

        "personal_fields": (
            get_default_personal_fields()
        ),

        "next_personal_field": None,

        "completed_sections": [],

        "missing_sections": [
            "personal",
            "education",
            "skills",
            "experience",
            "projects",
            "summary",
        ],

        "message_count": 0,
    }


def ensure_state(state):
    """
    Ensure old or partial conversation state remains
    compatible with the current M5 state structure.
    """

    default = get_initial_state()

    if not isinstance(state, dict):
        return default

    merged = deepcopy(default)

    for key, value in state.items():
        if key != "personal_fields":
            merged[key] = value

    incoming_personal = state.get(
        "personal_fields",
        {},
    )

    if isinstance(incoming_personal, dict):
        personal_fields = (
            get_default_personal_fields()
        )

        personal_fields.update(
            incoming_personal
        )

        merged["personal_fields"] = (
            personal_fields
        )

    return merged


def update_conversation_metadata(
    state,
    ai_response,
):
    """
    Store conversation-level information that is
    not part of normal CV updates.

    Includes:
    - target role
    - career level
    - skipped optional personal fields
    """

    state_updates = (
        ai_response.get("state_updates")
        or {}
    )

    target_role = state_updates.get(
        "target_role"
    )

    career_level = state_updates.get(
        "career_level"
    )

    if target_role:
        state["target_role"] = target_role

    if career_level:
        state["career_level"] = (
            career_level
        )

    skipped_fields = (
        state_updates.get(
            "skipped_personal_fields"
        )
        or []
    )

    personal_fields = state.get(
        "personal_fields",
        get_default_personal_fields(),
    )

    for field in skipped_fields:
        if field in OPTIONAL_PERSONAL_FIELDS:
            personal_fields[field] = (
                "skipped"
            )

    state["personal_fields"] = (
        personal_fields
    )

    return state


def update_personal_field_state(
    state,
    cv_updates,
):
    """
    Mark personal fields as collected when the
    AI extracted an actual value.
    """

    personal = cv_updates.get(
        "personal"
    )

    if not isinstance(personal, dict):
        return state

    personal_fields = state.get(
        "personal_fields",
        get_default_personal_fields(),
    )

    for field in PERSONAL_FIELD_ORDER:
        value = personal.get(field)

        if value not in (
            None,
            "",
        ):
            personal_fields[field] = (
                "collected"
            )

    state["personal_fields"] = (
        personal_fields
    )

    return state


def get_next_personal_field(state):
    """
    Return the first personal field that has
    not been collected or explicitly skipped.
    """

    state = ensure_state(state)

    personal_fields = state.get(
        "personal_fields",
        {},
    )

    for field in PERSONAL_FIELD_ORDER:
        field_status = personal_fields.get(
            field,
            "missing",
        )

        if field_status == "missing":
            return field

    return None


def get_required_conversation_step(state):
    """
    Determine the next deterministic conversation
    step.

    M5 decides the workflow.
    Groq only:
    - understands the user's response,
    - extracts structured information,
    - phrases the next question.
    """

    state = ensure_state(state)

    # =========================================
    # 1. Target role
    # =========================================

    if not state.get("target_role"):
        return {
            "section": "target",
            "field": "target_role",
        }

    # =========================================
    # 2. Career level
    # =========================================

    if not state.get("career_level"):
        return {
            "section": "target",
            "field": "career_level",
        }

    # =========================================
    # 3. Personal information
    # =========================================

    next_personal_field = (
        get_next_personal_field(state)
    )

    if next_personal_field:
        return {
            "section": "personal",
            "field": next_personal_field,
        }

    # =========================================
    # 4. Core CV sections
    # =========================================

    completed_sections = set(
        state.get(
            "completed_sections",
            [],
        )
    )

    for section in CORE_SECTION_ORDER:
        if section not in completed_sections:
            return {
                "section": section,

                # At this stage we only track
                # completion at section level.
                "field": section,
            }

    # =========================================
    # 5. Review
    # =========================================

    return {
        "section": "review",
        "field": "review",
    }


def update_state(
    state,
    ai_response,
):
    state = ensure_state(state)

    state["message_count"] += 1

    # =========================================
    # 1. Conversation metadata
    # =========================================

    state = update_conversation_metadata(
        state,
        ai_response,
    )

    # =========================================
    # 2. AI-proposed CV updates
    # =========================================

    cv_updates = (
        ai_response.get("cv_updates")
        or {}
    )

    # =========================================
    # 3. Personal progress
    # =========================================

    state = update_personal_field_state(
        state,
        cv_updates,
    )

    # =========================================
    # 4. Completed sections
    # =========================================

    completed_sections = set(
        state.get(
            "completed_sections",
            [],
        )
    )

    next_personal_field = (
        get_next_personal_field(state)
    )

    # Personal is complete only when every
    # personal field was collected or skipped.
    if (
        state.get("target_role")
        and state.get("career_level")
        and next_personal_field is None
    ):
        completed_sections.add(
            "personal"
        )

    # NOTE:
    # For now a non-empty section update marks
    # that section complete.
    #
    # We will improve this later with field-level
    # completeness after verifying the overall
    # deterministic workflow.
    for key, value in cv_updates.items():
        if key == "personal":
            continue

        if (
            key in CV_SECTIONS
            and value not in (
                None,
                "",
                [],
                {},
            )
        ):
            completed_sections.add(
                key
            )

    state["completed_sections"] = sorted(
        completed_sections
    )

    # =========================================
    # 5. Missing core sections
    # =========================================

    required_sections = {
        "personal",
        "education",
        "skills",
        "experience",
        "projects",
        "summary",
    }

    state["missing_sections"] = sorted(
        required_sections
        - completed_sections
    )

    # =========================================
    # 6. Determine deterministic next step
    # =========================================

    required_step = (
        get_required_conversation_step(
            state
        )
    )

    state["current_section"] = (
        required_step["section"]
    )

    if (
        required_step["section"]
        == "personal"
    ):
        state[
            "next_personal_field"
        ] = required_step["field"]

    else:
        state[
            "next_personal_field"
        ] = None

    return state