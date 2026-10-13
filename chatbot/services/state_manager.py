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


# ============================================================
# SECTION FIELD DEFINITIONS
# ============================================================

EDUCATION_FIELD_ORDER = [
    "degree",
    "institution",
    "field_of_study",
    "end_date",
]

# These are useful, but do not block section completion.
EDUCATION_OPTIONAL_FIELDS = [
    "start_date",
    "grade",
]


EXPERIENCE_FIELD_ORDER = [
    "company",
    "role",
    "responsibilities",
]

EXPERIENCE_OPTIONAL_FIELDS = [
    "location",
    "start_date",
    "end_date",
]


PROJECT_FIELD_ORDER = [
    "name",
    "description",
    "technologies",
]

PROJECT_OPTIONAL_FIELDS = [
    "url",
]

EMPTY_LIKE_VALUES = {
    "",
    "none",
    "null",
    "n/a",
    "na",
    "no",
    "not available",
    "not applicable",
}


def is_meaningful_text(value):
    if value is None:
        return False

    if isinstance(value, str):
        return (
            value.strip().lower()
            not in EMPTY_LIKE_VALUES
        )

    return True
# ============================================================
# DEFAULT STATES
# ============================================================

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


def get_default_education_fields():
    return {
        "degree": "missing",
        "institution": "missing",
        "field_of_study": "missing",
        "start_date": "missing",
        "end_date": "missing",
        "grade": "missing",
    }


def get_default_experience_fields():
    return {
        "company": "missing",
        "role": "missing",
        "location": "missing",
        "start_date": "missing",
        "end_date": "missing",
        "responsibilities": "missing",
    }


def get_default_project_fields():
    return {
        "name": "missing",
        "description": "missing",
        "technologies": "missing",
        "url": "missing",
    }


def get_initial_state():
    return {
        "target_role": None,
        "career_level": None,

        "current_section": "target",

        "personal_fields": (
            get_default_personal_fields()
        ),

        "education_fields": (
            get_default_education_fields()
        ),

        "experience_fields": (
            get_default_experience_fields()
        ),

        "project_fields": (
            get_default_project_fields()
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


# ============================================================
# STATE COMPATIBILITY
# ============================================================

def _merge_field_state(
    default_fields,
    incoming_fields,
):
    result = deepcopy(default_fields)

    if isinstance(incoming_fields, dict):
        result.update(incoming_fields)

    return result


def ensure_state(state):
    """
    Keeps old sessions compatible when new state fields are added.
    """

    default = get_initial_state()

    if not isinstance(state, dict):
        return default

    merged = deepcopy(default)

    nested_fields = {
        "personal_fields",
        "education_fields",
        "experience_fields",
        "project_fields",
    }

    for key, value in state.items():
        if key not in nested_fields:
            merged[key] = value

    merged["personal_fields"] = (
        _merge_field_state(
            get_default_personal_fields(),
            state.get("personal_fields"),
        )
    )

    merged["education_fields"] = (
        _merge_field_state(
            get_default_education_fields(),
            state.get("education_fields"),
        )
    )

    merged["experience_fields"] = (
        _merge_field_state(
            get_default_experience_fields(),
            state.get("experience_fields"),
        )
    )

    merged["project_fields"] = (
        _merge_field_state(
            get_default_project_fields(),
            state.get("project_fields"),
        )
    )

    return merged


# ============================================================
# METADATA
# ============================================================

def update_conversation_metadata(
    state,
    ai_response,
):
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

    if (
        target_role
        and not state.get("target_role")
    ):
        state["target_role"] = target_role

    if (
        career_level
        and not state.get("career_level")
    ):
        state["career_level"] = career_level

    skipped_fields = (
        state_updates.get(
            "skipped_personal_fields"
        )
        or []
    )

    personal_fields = state[
        "personal_fields"
    ]

    for field in skipped_fields:
        if field in OPTIONAL_PERSONAL_FIELDS:
            personal_fields[field] = (
                "skipped"
            )

    return state


# ============================================================
# PERSONAL
# ============================================================

def update_personal_field_state(
    state,
    cv_updates,
):
    personal = cv_updates.get(
        "personal"
    )

    if not isinstance(personal, dict):
        return state

    fields = state["personal_fields"]

    for field in PERSONAL_FIELD_ORDER:
        value = personal.get(field)

        # Optional personal fields such as
        # LinkedIn, GitHub, and portfolio can
        # be explicitly skipped.
        if (
            field in OPTIONAL_PERSONAL_FIELDS
            and isinstance(value, str)
            and value.strip().lower()
            in EMPTY_LIKE_VALUES
        ):
            fields[field] = "skipped"
            continue

        if is_meaningful_text(value):
            fields[field] = "collected"

    return state


def get_next_personal_field(state):
    state = ensure_state(state)

    fields = state["personal_fields"]

    for field in PERSONAL_FIELD_ORDER:
        if fields.get(
            field,
            "missing",
        ) == "missing":
            return field

    return None


# ============================================================
# EDUCATION
# ============================================================

def update_education_field_state(
    state,
    cv_updates,
):
    education = cv_updates.get(
        "education"
    )

    if not isinstance(
        education,
        list,
    ):
        return state

    fields = state["education_fields"]

    for item in education:
        if not isinstance(item, dict):
            continue

        for field in (
            EDUCATION_FIELD_ORDER
            + EDUCATION_OPTIONAL_FIELDS
        ):
            value = item.get(field)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                fields[field] = (
                    "collected"
                )

    return state


def get_next_education_field(state):
    fields = state[
        "education_fields"
    ]

    for field in EDUCATION_FIELD_ORDER:
        if fields.get(
            field,
            "missing",
        ) == "missing":
            return field

    return None


# ============================================================
# EXPERIENCE
# ============================================================

def update_experience_field_state(
    state,
    cv_updates,
):
    experience = cv_updates.get(
        "experience"
    )

    if not isinstance(
        experience,
        list,
    ):
        return state

    fields = state[
        "experience_fields"
    ]

    for item in experience:
        if not isinstance(item, dict):
            continue

        for field in (
            EXPERIENCE_FIELD_ORDER
            + EXPERIENCE_OPTIONAL_FIELDS
        ):
            value = item.get(field)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                fields[field] = (
                    "collected"
                )

    return state


def get_next_experience_field(state):
    fields = state[
        "experience_fields"
    ]

    for field in EXPERIENCE_FIELD_ORDER:
        if fields.get(
            field,
            "missing",
        ) == "missing":
            return field

    return None


# ============================================================
# PROJECTS
# ============================================================

def update_project_field_state(
    state,
    cv_updates,
):
    projects = cv_updates.get(
        "projects"
    )

    if not isinstance(
        projects,
        list,
    ):
        return state

    fields = state[
        "project_fields"
    ]

    for item in projects:
        if not isinstance(item, dict):
            continue

        for field in (
            PROJECT_FIELD_ORDER
            + PROJECT_OPTIONAL_FIELDS
        ):
            value = item.get(field)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                fields[field] = (
                    "collected"
                )

    return state


def get_next_project_field(state):
    fields = state[
        "project_fields"
    ]

    for field in PROJECT_FIELD_ORDER:
        if fields.get(
            field,
            "missing",
        ) == "missing":
            return field

    return None


# ============================================================
# SIMPLE SECTIONS
# ============================================================

def has_meaningful_value(value):
    return value not in (
        None,
        "",
        [],
        {},
    )


# ============================================================
# NEXT REQUIRED STEP
# ============================================================

def get_required_conversation_step(state):
    state = ensure_state(state)
    if state.get('mode') == 'edit_existing':
        from chatbot.services.existing_cv_conversation import edit_step
        return edit_step(state)

    # --------------------------------------------------------
    # Target
    # --------------------------------------------------------

    if not state.get("target_role"):
        return {
            "section": "target",
            "field": "target_role",
        }

    if not state.get("career_level"):
        return {
            "section": "target",
            "field": "career_level",
        }

    # --------------------------------------------------------
    # Personal
    # --------------------------------------------------------

    next_field = (
        get_next_personal_field(state)
    )

    if next_field:
        return {
            "section": "personal",
            "field": next_field,
        }

    completed_sections = set(
        state.get(
            "completed_sections",
            [],
        )
    )

    # --------------------------------------------------------
    # Education
    # --------------------------------------------------------

    if "education" not in completed_sections:
        next_field = (
            get_next_education_field(
                state
            )
        )

        if next_field:
            return {
                "section": "education",
                "field": next_field,
            }

    # --------------------------------------------------------
    # Skills
    # --------------------------------------------------------

    if "skills" not in completed_sections:
        return {
            "section": "skills",
            "field": "skills",
        }

    # --------------------------------------------------------
    # Experience
    # --------------------------------------------------------

    if "experience" not in completed_sections:
        next_field = (
            get_next_experience_field(
                state
            )
        )

        if next_field:
            return {
                "section": "experience",
                "field": next_field,
            }

    # --------------------------------------------------------
    # Projects
    # --------------------------------------------------------

    if "projects" not in completed_sections:
        next_field = (
            get_next_project_field(
                state
            )
        )

        if next_field:
            return {
                "section": "projects",
                "field": next_field,
            }

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    if "summary" not in completed_sections:
        return {
            "section": "summary",
            "field": "summary",
        }

    # --------------------------------------------------------
    # Review
    # --------------------------------------------------------

    return {
        "section": "review",
        "field": "review",
    }


# ============================================================
# UPDATE STATE
# ============================================================

def update_state(
    state,
    ai_response,
    user_message=None,
):
    if isinstance(state, dict) and state.get('mode') == 'edit_existing':
        from chatbot.services.existing_cv_conversation import update_edit_state
        return update_edit_state(state, ai_response, user_message)
    state = ensure_state(state)

    state["message_count"] += 1

    # --------------------------------------------------------
    # 1. Metadata
    # --------------------------------------------------------

    state = update_conversation_metadata(
        state,
        ai_response,
    )

    cv_updates = (
        ai_response.get("cv_updates")
        or {}
    )

    # --------------------------------------------------------
    # 2. Update field-level progress
    # --------------------------------------------------------

    state = update_personal_field_state(
        state,
        cv_updates,
    )

    state = update_education_field_state(
        state,
        cv_updates,
    )

    state = update_experience_field_state(
        state,
        cv_updates,
    )

    state = update_project_field_state(
        state,
        cv_updates,
    )

    completed_sections = set(
        state.get(
            "completed_sections",
            [],
        )
    )

    # --------------------------------------------------------
    # 3. Personal completion
    # --------------------------------------------------------

    if (
        state.get("target_role")
        and state.get("career_level")
        and get_next_personal_field(
            state
        ) is None
    ):
        completed_sections.add(
            "personal"
        )

    # --------------------------------------------------------
    # 4. Education completion
    # --------------------------------------------------------

    if (
        get_next_education_field(
            state
        )
        is None
    ):
        completed_sections.add(
            "education"
        )
    else:
        completed_sections.discard(
            "education"
        )

    # --------------------------------------------------------
    # 5. Skills completion
    # --------------------------------------------------------

    skills = cv_updates.get("skills")

    if has_meaningful_value(skills):
        completed_sections.add(
            "skills"
        )

    # --------------------------------------------------------
    # 6. Experience completion
    # --------------------------------------------------------

    if (
        get_next_experience_field(
            state
        )
        is None
    ):
        completed_sections.add(
            "experience"
        )
    else:
        completed_sections.discard(
            "experience"
        )

    # --------------------------------------------------------
    # 7. Projects completion
    # --------------------------------------------------------

    if (
        get_next_project_field(
            state
        )
        is None
    ):
        completed_sections.add(
            "projects"
        )
    else:
        completed_sections.discard(
            "projects"
        )

    # --------------------------------------------------------
    # 8. Summary completion
    # --------------------------------------------------------

    summary = cv_updates.get(
        "summary"
    )

    if has_meaningful_value(summary):
        completed_sections.add(
            "summary"
        )

    # --------------------------------------------------------
    # 9. Optional sections
    # --------------------------------------------------------

    for section in [
        "certifications",
        "achievements",
        "languages",
    ]:
        value = cv_updates.get(
            section
        )

        if has_meaningful_value(value):
            completed_sections.add(
                section
            )

    state["completed_sections"] = sorted(
        completed_sections
    )

    # --------------------------------------------------------
    # 10. Missing sections
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 11. Determine next deterministic step
    # --------------------------------------------------------

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


EMPTY_LIKE_VALUES = {
    "",
    "none",
    "null",
    "n/a",
    "na",
    "no",
    "not available",
    "not applicable",
}


def is_meaningful_text(value):
    if value is None:
        return False

    if isinstance(value, str):
        return (
            value.strip().lower()
            not in EMPTY_LIKE_VALUES
        )

    return True
