from pathlib import Path
from zipfile import ZipFile, BadZipFile

from rest_framework.exceptions import ValidationError


ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
}

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024


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

    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(1024)
        if extension == '.pdf':
            if b'%PDF-' not in header:
                raise ValidationError({'file': 'The file content is not a PDF document.'})
        else:
            uploaded_file.seek(0)
            with ZipFile(uploaded_file) as archive:
                names = set(archive.namelist())
                if not {'[Content_Types].xml', 'word/document.xml'} <= names:
                    raise ValidationError({'file': 'The file content is not a DOCX document.'})
                if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_SIZE:
                    raise ValidationError({'file': 'The DOCX expands beyond the supported processing size.'})
                if any(item.flag_bits & 1 for item in archive.infolist()):
                    raise ValidationError({'file': 'Encrypted DOCX documents are not supported.'})
    except (BadZipFile, OSError, ValueError) as exc:
        raise ValidationError({'file': 'The uploaded document is invalid or corrupted.'}) from exc
    finally:
        uploaded_file.seek(0)
    return ALLOWED_EXTENSIONS[extension]
