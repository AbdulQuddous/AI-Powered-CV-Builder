"""
Very small deterministic local parser.

IMPORTANT:
This module must NOT try to understand arbitrary natural language.

It only handles values/commands that can be interpreted
with very high confidence.

Everything else must fall back to the local provider.
"""

import re


# ============================================================
# Text normalization
# ============================================================

def normalize_text(text):
    return " ".join(
        str(text)
        .strip()
        .lower()
        .split()
    )


# ============================================================
# Career level
# ============================================================

CAREER_LEVEL_VALUES = {
    "fresher": "fresher",
    "i am a fresher": "fresher",
    "i'm a fresher": "fresher",
    "fresh graduate": "fresher",
    "i am a fresh graduate": "fresher",

    "student": "student",
    "i am a student": "student",
    "i'm a student": "student",

    "experienced": "experienced",
    "i am experienced": "experienced",
    "experienced professional": "experienced",

    "other": "other",
}


def extract_exact_career_level(text):
    """
    Only handles very obvious career-level answers.

    Anything more complicated should go to the local provider.
    """

    normalized = normalize_text(text)

    return CAREER_LEVEL_VALUES.get(
        normalized
    )


# ============================================================
# Finish / skip commands
# ============================================================

FINISH_COMMANDS = {
    "finish",
    "fnish",
    "finsh",
    "finsih",
    "finished",
    "complete",
    "complete cv",
    "finish cv",
    "finish the cv",
    "finish interview",
    "finish the interview",
    "everything looks correct",
    "looks correct",
    "everything is correct",
}


EXACT_SKIP_COMMANDS = {
    "no",
    "none",
    "skip",
    "skip it",
    "not available",
    "n/a",
    "i don't have one",
    "i dont have one",
    "i do not have one",
    "i don't have it",
    "i dont have it",
    "i do not have it",
}


def is_finish_command(text):
    normalized = normalize_text(text).rstrip('.!')

    return normalized in FINISH_COMMANDS


def is_exact_skip_command(text):
    """
    Only skip the CURRENT optional field when the
    complete message is an obvious skip command.

    Example:
        "no" -> safe

    But:
        "I have LinkedIn but no GitHub and portfolio"
        -> NOT handled locally
        -> the local provider
    """

    normalized = normalize_text(text)

    return normalized in EXACT_SKIP_COMMANDS


# ============================================================
# Profile links & skipped fields
# ============================================================
#
# NOTE: This module no longer tries to parse arbitrary URLs.
# URL/link parsing is intentionally delegated to the local provider.
#
# The only link-related logic kept here is explicit NEGATION
# detection ("no github", "I don't have a portfolio"),
# because that is a closed set of phrases we can match with
# very high confidence and it must not cost a the local provider call.
# ============================================================

PROFILE_FIELDS = {
    "linkedin",
    "github",
    "portfolio",
}


def extract_skipped_profile_fields(text):
    """
    Detect exactly which professional-link fields
    the user says they do not have.

    Examples:
    - "no portfolio"
    - "I have no GitHub"
    - "no portfolio and github account"
    """

    lowered = normalize_text(
        text
    )

    skipped = set()

    # --------------------------------------------------------
    # Direct negative phrases
    # --------------------------------------------------------

    for field in PROFILE_FIELDS:
        patterns = [
            rf"\bno\s+(?:a\s+)?{field}\b",
            rf"\bi have no\s+(?:a\s+)?{field}\b",
            rf"\bi don't have\s+(?:a\s+)?{field}\b",
            rf"\bi dont have\s+(?:a\s+)?{field}\b",
            rf"\bi do not have\s+(?:a\s+)?{field}\b",
            rf"\bwithout\s+(?:a\s+)?{field}\b",
        ]

        for pattern in patterns:
            if re.search(
                pattern,
                lowered,
                re.IGNORECASE,
            ):
                skipped.add(field)
                break

    # --------------------------------------------------------
    # Compound negatives
    #
    # Example:
    # "I have no portfolio and github account"
    # --------------------------------------------------------

    negative_match = re.search(
        r"\b(?:have\s+)?no\s+(.+)",
        lowered,
        re.IGNORECASE,
    )

    if negative_match:
        negative_part = (
            negative_match
            .group(1)
        )

        # Stop if user changes meaning:
        # "no portfolio but github is ..."
        negative_part = re.split(
            r"\b(?:but|however|except)\b|[.;]",
            negative_part,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]

        for field in PROFILE_FIELDS:
            if re.search(
                rf"\b{field}\b",
                negative_part,
                re.IGNORECASE,
            ):
                skipped.add(field)

    return sorted(skipped)


def extract_profile_information(text):
    """
    Return only NEGATION information about profile links.

    Provided links are NOT parsed locally — those go to
    the local provider, which is far better at recognizing URLs.

    Returns:
        {
            "values":  {},               # always empty
            "skipped": ["github", ...],  # may be empty
        }
    """

    skipped = extract_skipped_profile_fields(text)

    return {
        "values": {},
        "skipped": skipped,
    }
