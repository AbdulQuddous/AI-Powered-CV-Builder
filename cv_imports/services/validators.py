from pathlib import Path

from rest_framework.exceptions import ValidationError


ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
}

MAX_FILE_SIZE = 5 * 1024 * 1024


def validate_cv_file(uploaded_file):

    if uploaded_file is None:
        raise ValidationError(
            {"file": "A CV file is required."}
        )

    if uploaded_file.size == 0:
        raise ValidationError(
            {"file": "Uploaded file is empty."}
        )

    if uploaded_file.size > MAX_FILE_SIZE:
        raise ValidationError(
            {
                "file": (
                    "File size exceeds the "
                    "maximum allowed size of 5 MB."
                )
            }
        )

    extension = Path(
        uploaded_file.name
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            {
                "file": (
                    "Unsupported file type. "
                    "Only PDF and DOCX files "
                    "are allowed."
                )
            }
        )

    return ALLOWED_EXTENSIONS[extension]