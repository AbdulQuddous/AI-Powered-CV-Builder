import re

from ai.exceptions import InvalidAIInputError
from ai.schemas.contracts import get_cv_errors


def warning(
    code,
    section,
    message,
    severity="medium",
):
    return {
        "code": code,
        "section": section,
        "severity": severity,
        "source": "rule",
        "message": message,
    }


def validate_cv_rules(cv):
    if not isinstance(cv, dict):
        raise InvalidAIInputError(
            "CV must be a JSON object."
        )

    warnings = []

    # 1. Shared schema validation
    schema_errors = get_cv_errors(cv)

    for message in schema_errors[:10]:
        warnings.append(
            warning(
                "CV_SCHEMA_INVALID",
                "general",
                message,
                "high",
            )
        )

    # 2. Personal information
    personal = cv.get("personal") or {}

    if not isinstance(personal, dict):
        personal = {}

    for field in ("full_name", "email", "phone"):
        value = personal.get(field)

        if not value or not str(value).strip():
            warnings.append(
                warning(
                    f"MISSING_{field.upper()}",
                    "personal",
                    f"{field.replace('_', ' ').title()} is missing.",
                    "high",
                )
            )

    # 3. Summary
    summary = cv.get("summary") or ""

    if isinstance(summary, str):
        if not summary.strip():
            warnings.append(
                warning(
                    "SUMMARY_MISSING",
                    "summary",
                    "Professional summary is missing.",
                )
            )

        elif len(summary.split()) > 100:
            warnings.append(
                warning(
                    "SUMMARY_TOO_LONG",
                    "summary",
                    "Consider shortening the professional summary.",
                    "low",
                )
            )

    # 4. Skills
    skills = cv.get("skills") or []

    if not isinstance(skills, list):
        skills = []

    normalized_skills = []

    for skill in skills:
        if isinstance(skill, str):
            normalized_skills.append(skill.strip().lower())

        elif isinstance(skill, dict):
            name = skill.get("name")

            if isinstance(name, str):
                normalized_skills.append(
                    name.strip().lower()
                )

    normalized_skills = [
        skill
        for skill in normalized_skills
        if skill
    ]

    if not normalized_skills:
        warnings.append(
            warning(
                "SKILLS_MISSING",
                "skills",
                "No technical or professional skills were provided.",
            )
        )

    if len(normalized_skills) != len(set(normalized_skills)):
        warnings.append(
            warning(
                "DUPLICATE_SKILLS",
                "skills",
                "Duplicate skills were detected.",
                "low",
            )
        )

    # 5. Experience
    experience = cv.get("experience") or []

    if isinstance(experience, list) and len(experience) > 5:
        warnings.append(
            warning(
                "EXPERIENCE_COUNT_HIGH",
                "experience",
                "Consider prioritizing the five most relevant experiences.",
                "low",
            )
        )

    # 6. Education
    education = cv.get("education") or []

    if not education:
        warnings.append(
            warning(
                "EDUCATION_MISSING",
                "education",
                "Education information is missing.",
            )
        )

    # 7. Projects
    projects = cv.get("projects") or []

    career_level = (
        cv.get("meta", {}).get("career_level")
        if isinstance(cv.get("meta"), dict)
        else None
    )

    if career_level in ("fresher", "student") and not projects:
        warnings.append(
            warning(
                "PROJECTS_RECOMMENDED",
                "projects",
                "Relevant academic or personal projects can strengthen a fresher CV.",
                "low",
            )
        )

    return {
        "valid": not bool(schema_errors),
        "warnings": warnings,
        "source": "rules",
    }