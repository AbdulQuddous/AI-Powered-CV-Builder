# cv_imports/services/text_cleaner.py

import re


def clean_extracted_text(text):

    if not text:
        return ""

    # Normalize Windows/Mac line endings.
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove null characters.
    text = text.replace("\x00", "")

    # Replace repeated spaces/tabs with one space.
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # Remove spaces before new lines.
    text = re.sub(
        r" +\n",
        "\n",
        text,
    )

    # Remove spaces after new lines.
    text = re.sub(
        r"\n +",
        "\n",
        text,
    )

    # Collapse excessive blank lines.
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()