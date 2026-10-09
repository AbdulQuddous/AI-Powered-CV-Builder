import copy
import re


LIST_FIELDS = (
    "skills",
    "education",
    "experience",
    "projects",
    "certifications",
    "achievements",
    "languages",
)

PERSONAL_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
    "portfolio",
)

META_FIELDS = (
    "target_role",
    "career_level",
    "template_id",
)

EDUCATION_FIELDS = (
    "degree",
    "institution",
    "field_of_study",
    "start_date",
    "end_date",
    "grade",
)


def normalize_extracted_cv(cv):
    """
    Apply safe normalization to extracted CV JSON.

    Does not invent months, jobs, skills, or achievements.

    Returns:
        normalized_cv, warnings
    """

    cv = copy.deepcopy(cv)
    warnings = []

    if not isinstance(cv, dict):
        return cv, warnings

    # Schema version is structural metadata.
    if cv.get("schema_version") is None:
        cv["schema_version"] = "1.0"

    # Normalize metadata.
    meta = cv.get("meta")

    if meta is None:
        meta = {}
        cv["meta"] = meta

    if isinstance(meta, dict):
        for field in META_FIELDS:
            if meta.get(field) is None:
                meta[field] = ""

    # Normalize personal information.
    personal = cv.get("personal")

    if personal is None:
        personal = {}
        cv["personal"] = personal

    if isinstance(personal, dict):
        for field in PERSONAL_FIELDS:
            if personal.get(field) is None:
                personal[field] = ""

    # Normalize summary.
    if cv.get("summary") is None:
        cv["summary"] = ""

    # Normalize missing collections.
    for field in LIST_FIELDS:
        if cv.get(field) is None:
            cv[field] = []

    # Normalize education.
    education = cv.get("education")

    if isinstance(education, list):

        for index, item in enumerate(education):

            if not isinstance(item, dict):
                continue

            for field in EDUCATION_FIELDS:
                if item.get(field) is None:
                    item[field] = ""

            for date_field in (
                "start_date",
                "end_date",
            ):
                value = item.get(date_field)

                if not isinstance(value, str):
                    continue

                # M10 requires YYYY-MM or empty.
                # A year alone cannot provide a month.
                if re.fullmatch(
                    r"\d{4}",
                    value,
                ):
                    warnings.append({
                        "code": "MONTH_REQUIRED",
                        "section": "education",
                        "field": (
                            f"education.{index}.{date_field}"
                        ),
                        "original_value": value,
                        "message": (
                            "The source contains only a year. "
                            "Confirm the month before saving "
                            "a complete education date."
                        ),
                    })

                    item[date_field] = ""

    return cv, warnings