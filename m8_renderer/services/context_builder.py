from .skill_groups import group_skills


def text(value):
    """
    Return safe plain-text values without converting
    dictionaries or lists to Python representations.
    """
    if value is None or isinstance(value, bool):
        return ""

    if isinstance(value, (str, int, float)):
        return str(value).strip()

    return ""


def first(item, *keys):
    if not isinstance(item, dict):
        return ""

    for key in keys:
        value = text(item.get(key))

        if value:
            return value

    return ""


def string_list(value):
    """
    Convert an existing list into plain-text items.
    No AI interpretation or CV content generation.
    """
    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        if isinstance(item, dict):
            value_text = first(
                item,
                "name",
                "title",
                "text",
                "value",
            )
        else:
            value_text = text(item)

        if value_text:
            result.append(value_text)

    return result


def join_parts(*values):
    return " | ".join(
        value for value in values if value
    )


def date_range(item):
    start = first(item, "start_date")
    end = first(item, "end_date")

    if item.get("is_current"):
        end = "Present"

    if start and end:
        return f"{start} - {end}"

    return start or end


def normalize_entry(section, item):
    """
    Convert one CV section item into:
    title, subtitle, description and bullets.
    """
    if isinstance(item, str):
        return {
            "title": item.strip(),
            "subtitle": "",
            "description": "",
            "bullets": [],
        }

    if not isinstance(item, dict):
        return None

    title = ""
    subtitle = ""
    description = ""
    bullets = []

    if section == "experience":
        title = first(
            item,
            "job_title",
            "role",
            "position",
            "title",
        )

        subtitle = join_parts(
            first(item, "company", "organization"),
            first(item, "location"),
            date_range(item),
        )

        description = first(item, "description")

        bullets = string_list(
            item.get("highlights")
            or item.get("responsibilities")
            or []
        )

    elif section == "education":
        title = first(item, "degree")

        subtitle = join_parts(
            first(item, "institution"),
            first(item, "field_of_study"),
            date_range(item),
        )

        grade = first(item, "grade")

        if grade:
            description = f"Grade: {grade}"

    elif section == "projects":
        title = first(item, "name", "title")

        description = first(item, "description")

        technologies = item.get("technologies", [])

        if isinstance(technologies, str):
            technologies = [
                part.strip()
                for part in technologies.split(",")
                if part.strip()
            ]

        tech_list = string_list(technologies)

        if tech_list:
            subtitle = "Technologies: " + ", ".join(
                tech_list
            )

        project_url = first(item, "url")

        bullets = string_list(
            item.get("highlights") or []
        )

        if project_url:
            bullets.append(project_url)

    elif section == "certifications":
        title = first(
            item,
            "name",
            "title",
            "certification",
        )

        subtitle = join_parts(
            first(item, "issuer", "organization"),
            first(item, "date", "issue_date"),
        )
        url = first(item, "url")
        if url:
            bullets.append(url)

    elif section == "achievements":
        title = first(item, "title", "name")

        description = first(
            item,
            "description",
            "details",
        )

    elif section == "languages":
        title = first(item, "name", "language")

        subtitle = first(
            item,
            "proficiency",
            "level",
        )

    return {
        "title": title,
        "subtitle": subtitle,
        "description": description,
        "bullets": bullets,
    }


def build_section(data, key, label):
    raw_entries = data.get(key, [])

    if not isinstance(raw_entries, list):
        raw_entries = []

    entries = []

    for item in raw_entries:
        entry = normalize_entry(key, item)

        if entry and any([
            entry["title"],
            entry["subtitle"],
            entry["description"],
            entry["bullets"],
        ]):
            entries.append(entry)

    return {
        "key": key,
        "label": label,
        "items": entries,
    }


def build_context(cv_data):
    """
    Convert the shared CV JSON into a presentation context.

    This function:
    - Does not modify the original JSON.
    - Does not query the database.
    - Does not call Gemini.
    - Does not save anything.
    """
    if not isinstance(cv_data, dict):
        raise ValueError("cv_data must be an object")

    personal = cv_data.get("personal", {})

    if not isinstance(personal, dict):
        personal = {}

    personal = {
        key: text(personal.get(key))
        for key in [
            "full_name",
            "email",
            "phone",
            "location",
            "linkedin",
            "github",
            "portfolio",
        ]
    }

    contact = [
        personal[key]
        for key in [
            "email",
            "phone",
            "location",
            "linkedin",
            "github",
            "portfolio",
        ]
        if personal[key]
    ]

    meta = cv_data.get("meta", {})

    if not isinstance(meta, dict):
        meta = {}

    sections = [
        build_section(
            cv_data,
            "experience",
            "Professional Experience",
        ),
        build_section(
            cv_data,
            "projects",
            "Projects",
        ),
        build_section(
            cv_data,
            "education",
            "Education",
        ),
        build_section(
            cv_data,
            "certifications",
            "Certifications",
        ),
        build_section(
            cv_data,
            "achievements",
            "Achievements",
        ),
        build_section(
            cv_data,
            "languages",
            "Languages",
        ),
    ]

    skills = string_list(cv_data.get('skills', []))
    return {
        "personal": personal,
        "contact": contact,
        "target_role": text(
            meta.get("target_role")
        ),
        "summary": text(
            cv_data.get("summary")
        ),
        "skills": skills,
        "skill_groups": group_skills(skills),
        "sections": [
            section
            for section in sections
            if section["items"]
        ],
    }
