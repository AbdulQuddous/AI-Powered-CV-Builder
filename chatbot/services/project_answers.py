"""Keep a project's literal title, descriptive facts and professional profile separate."""
import re

from chatbot.services.field_validation import find_technologies


def is_profile_paragraph(text):
    first_sentence = re.split(r'\.\s', text, maxsplit=1)[0]
    return (len(text) > 180 and bool(re.search(r'\b(?:graduate|intern|professional|developer|engineer)\b', first_sentence, re.I))
            and bool(re.search(r'\b(?:hands.on experience|years? of experience|comfortable with|strong foundation|worked on|independent .+ projects)\b', text, re.I)))


def project_title(text):
    """Unwrap explicit naming requests, preserving spelling instead of inventing a title."""
    text = text.strip().rstrip('.!')
    if is_profile_paragraph(text):
        return None
    text = re.sub(r"^(?:(?:i\s+(?:want|would like)\s+to\s+)?add\s+(?:(?:a|an|another|a new)\s+)?|"
                  r"(?:(?:my|the)\s+)?project\s+(?:(?:name|title)\s+is\s+|is\s+(?:called|named)\s+)|"
                  r"(?:it\s+is|it's)\s+(?:called|named)\s+)", '', text, flags=re.I).strip()
    if (not text or len(text) > 160 or len(text.split()) > 20 or re.search(r'[?;•\n]|\b(?:using|uses|builds|built|developed|worked|graduated|have|makes|manages)\b', text, re.I)):
        return None
    # Short naming answers can contain conjunctions; first-person prose needs interpretation.
    if re.match(r'^(?:i|my|can|could|what|how|please)\b', text, re.I):
        return None
    return text


def project_description(text):
    entry = {'description': text}
    technologies = find_technologies(text)
    if technologies:
        entry['technologies'] = technologies
    return entry
