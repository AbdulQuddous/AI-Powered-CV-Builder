"""Explicit handoff from stored M5 proposals to M2's versioned document.

No extraction, provider calls, or conversation-state transitions occur here.
"""
import re
from copy import deepcopy

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, ValidationError

from chatbot.models import ChatMessage, ChatSession
from cvs import services
from cvs.validation import build_document, validate_document


class ChatImportConflict(APIException):
    status_code = 409
    default_code = "chat_import_conflict"


IDENTITIES = {
    "education": ("institution", "degree"),
    "experience": ("company", "role"),
    "projects": ("name",),
    "certifications": ("name",),
    "languages": ("name",),
}


def meaningful(value):
    return value is not None and value != "" and value != [] and value != {}


def merge_entries(entries, updates, section):
    """Match named records; attach an unnamed follow-up only when unambiguous."""
    for update in updates:
        if isinstance(update, str) and section in ("projects", "certifications", "languages"):
            update = {"name": update}
        if not isinstance(update, dict):
            if meaningful(update) and update not in entries:
                entries.append(deepcopy(update))
            continue
        update = {key: value for key, value in update.items() if meaningful(value)}
        if not update:
            continue
        keys = IDENTITIES.get(section, ())
        named = any(update.get(key) for key in keys)
        matches = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            common = [key for key in keys if update.get(key) and entry.get(key)]
            if common and all(str(update[key]).casefold() == str(entry[key]).casefold() for key in common):
                matches.append(index)
        if not named:
            matches = [index for index, item in enumerate(entries) if isinstance(item, dict)]
            if len(matches) > 1:
                raise ValidationError({"detail": f"A {section} update has no identifying name. Review the conversation before saving."})
        if len(matches) == 1:
            entry = entries[matches[0]]
            update = deepcopy(update)
            for field in ("start_date", "end_date", "date"):
                supplied = text(update.get(field))
                saved = text(entry.get(field))
                # A year-only proposal must not erase a month already confirmed
                # in the editor for that same year.
                if re.fullmatch(r"\d{4}", supplied) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", saved) and saved[:4] == supplied:
                    update[field] = saved
            entry.update(update)
        elif len(matches) > 1:
            raise ValidationError({"detail": f"Multiple {section} entries match an update. Review the conversation before saving."})
        else:
            entries.append(deepcopy(update))
    return entries


def collected_updates(session):
    if session.conversation_state.get('mode') == 'edit_existing':
        updates = deepcopy(session.conversation_state.get('edit_updates', {'personal': {}}))
        if session.conversation_state.get('edit_new_projects'):
            updates.setdefault('projects', [])
        return updates
    if 'collected_data' in session.conversation_state:
        result = deepcopy(session.conversation_state['collected_data'])
        if 'summary' in session.conversation_state.get('skipped_sections', []):
            result.pop('summary', None)
        return result
    result = {"personal": {}}
    messages = session.messages.filter(role=ChatMessage.Role.ASSISTANT).exclude(intent="irrelevant").order_by("created_at", "id")
    for message in messages:
        updates = message.cv_updates
        if not isinstance(updates, dict):
            continue
        for section, value in updates.items():
            if not meaningful(value):
                continue
            if section == "personal" and isinstance(value, dict):
                result[section].update({key: deepcopy(item) for key, item in value.items() if meaningful(item)})
            elif section in IDENTITIES and isinstance(value, list):
                result[section] = merge_entries(result.get(section, []), value, section)
            elif section in ("skills", "achievements") and isinstance(value, list):
                existing = result.setdefault(section, [])
                for item in value:
                    if item not in existing:
                        existing.append(deepcopy(item))
            elif section == "summary":
                result[section] = value
    if 'summary' in session.conversation_state.get('skipped_sections', []):
        result.pop('summary', None)
    return result


def text(value):
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def strings(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [text(item) for item in value if text(item)]


def date(value, section, field, warnings):
    value = text(value)
    if value and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        label = field.replace("_", " ")
        warnings.append(f"{section.capitalize()} {label} ({value}) needs a confirmed year and month. Add it in the CV editor; the original value remains in your chat history.")
        return ""
    return value


def canonical_entry(section, item, warnings):
    if section == "achievements":
        if isinstance(item, dict):
            return ": ".join(text(item.get(key)) for key in ("title", "description") if text(item.get(key)))
        return text(item)
    if isinstance(item, str):
        item = {"name": item}
    if not isinstance(item, dict):
        raise ValidationError({"detail": f"Unsupported {section} entry in the conversation."})
    fields = {
        "education": ("degree", "institution", "field_of_study", "start_date", "end_date", "grade"),
        "experience": ("company", "job_title", "location", "start_date", "end_date"),
        "projects": ("name", "description", "url"),
        "certifications": ("name", "issuer", "date", "url"),
        "languages": ("name", "proficiency"),
    }[section]
    entry = {key: text(item.get(key)) for key in fields}
    for key in ("start_date", "end_date", "date"):
        if key in entry:
            if section == 'experience' and key == 'end_date' and (
                item.get('is_current') or text(item.get('end_date')).lower() in ('present', 'current', 'ongoing')
            ):
                entry[key] = ''
                continue
            entry[key] = date(item.get(key), section, key, warnings)
    if section == "experience":
        entry["job_title"] = text(item.get("role") or item.get("job_title"))
        entry["is_current"] = bool(item.get("is_current")) or text(item.get("end_date")).lower() in ("present", "current", "ongoing")
        entry["highlights"] = strings(item.get("responsibilities") or item.get("highlights"))
        if entry["is_current"]:
            entry["end_date"] = ""
    elif section == "projects":
        technologies = item.get("technologies")
        entry["technologies"] = strings(technologies.split(",") if isinstance(technologies, str) else technologies)
        entry["highlights"] = strings(item.get("highlights"))
    elif section == "languages":
        entry["proficiency"] = entry["proficiency"].lower()
        if entry["proficiency"] not in ("", "basic", "conversational", "professional", "fluent", "native"):
            warnings.append(f"Language proficiency '{entry['proficiency']}' needs confirmation in the CV editor.")
            entry["proficiency"] = ""
    return entry


def build_chat_document(session, current=None):
    document = deepcopy(current) if current is not None else build_document({})
    updates = collected_updates(session)
    warnings = []
    entry_warnings = {}

    def canonical_at(section, index, item):
        local_warnings = []
        result = canonical_entry(section, item, local_warnings)
        entry_warnings.setdefault((section, index), []).extend(local_warnings)
        return result

    for key, value in updates["personal"].items():
        if key in document["personal"]:
            document["personal"][key] = text(value)
    for section, value in updates.items():
        if section == "personal":
            continue
        if section == "summary":
            document[section] = text(value)
        elif section == "skills":
            document[section] = list(dict.fromkeys(document[section] + strings(value)))
        elif section in (*IDENTITIES, "achievements"):
            existing = document[section]
            additions = []
            if section == 'projects' and session.conversation_state.get('mode') == 'edit_existing':
                additions = session.conversation_state.get('edit_new_projects') or []
            if section == "experience":
                existing = [dict(item, role=item["job_title"]) for item in existing]
            if section == "achievements":
                value = [canonical_entry(section, item, warnings) for item in value]
            # Merge sparse proposals first, then fill required structural defaults.
            entries = merge_entries(existing + deepcopy(additions), value, section)
            document[section] = [canonical_at(section, index, item) for index, item in enumerate(entries)]
    state = session.conversation_state or {}
    for patch in state.get('entry_patches', []):
        section, index = patch['section'], patch['index']
        if section not in ('education', 'experience', 'projects') or type(index) is not int or not 0 <= index < len(document[section]):
            raise ValidationError({'detail': 'The selected entry is no longer available. Reopen the latest CV.'})
        raw = deepcopy(document[section][index])
        if section == 'experience':
            raw['role'] = raw['job_title']
            raw['responsibilities'] = raw['highlights']
        raw.update(patch['updates'])
        document[section][index] = canonical_at(section, index, raw)
    removed = {item.casefold() for item in state.get('removed_skills', [])}
    document['skills'] = [skill for skill in document['skills'] if skill.casefold() not in removed]
    indexes = state.get('display_experience_indexes')
    if indexes is not None:
        if not (0 < len(indexes) <= 5 and all(type(i) is int and 0 <= i < len(document['experience']) for i in indexes)):
            raise ValidationError({'detail': 'Please select up to five valid experiences.'})
        document['experience'] = [document['experience'][i] for i in indexes]
    for section, indexes in (state.get('display_entry_indexes') or {}).items():
        if (section not in ('projects', 'certifications') or not isinstance(indexes, list) or not indexes
                or any(type(i) is not int or not 0 <= i < len(document[section]) for i in indexes)
                or len(set(indexes)) != len(indexes)):
            raise ValidationError({'detail': 'Choose valid, distinct original project or certification numbers.'})
        document[section] = [document[section][i] for i in indexes]
    # Omitted source entries need no date fixes in the displayed document.
    for (section, index), messages in entry_warnings.items():
        selection = (state.get('display_experience_indexes') if section == 'experience'
                     else (state.get('display_entry_indexes') or {}).get(section))
        if selection is None or index in selection:
            warnings.extend(messages)
    if state.get('mode') == 'edit_existing':
        state = state.get('edit_metadata_updates') or {}
    for key in ("target_role", "career_level"):
        if state.get(key):
            value = state[key]
            if key == "career_level" and value == "student":
                value = "other"  # M2's existing enum has no student value.
                warnings.append("M2 stores student career level as 'other'; your education is preserved.")
            document["meta"][key] = value
    if not document["meta"]["template_id"]:
        document["meta"]["template_id"] = session.conversation_state.get('template_id') or 'modern'
    changes = session.conversation_state.get('approved_review_changes', [])
    if changes:
        from ai.services.final_review import fingerprint
        if fingerprint(document) != session.conversation_state.get('review_decisions', {}).get('fingerprint'):
            raise ValidationError({'detail': 'The draft changed after review approval. Review the latest draft again.'})
    for change in changes:
        # Server-created, fingerprint-bound proposals; never arbitrary paths from the browser.
        from ai.services.final_review import apply_change
        apply_change(document, change)
    return validate_document(document), list(dict.fromkeys(warnings))


@transaction.atomic
def save_chat_cv(*, user, session_id, expected_version=None):
    session = get_object_or_404(ChatSession.objects.select_for_update(), id=session_id, user=user)
    if session.status != ChatSession.Status.COMPLETED:
        raise ChatImportConflict("Finish the conversation before saving its collected details.")
    # Approval may be the first request after an older draft was collected.
    # Apply the same evidence-based recovery used by the draft review endpoint.
    from chatbot.services.optional_section_recovery import repair_optional_answers
    repair_optional_answers(session)
    cv = services.owned(user=user, cv_id=session.cv_id, lock=True) if session.cv_id else None
    editing = session.conversation_state.get('mode') == 'edit_existing'
    if cv and (session.conversation_state.get('chat_saved_cv_id') == cv.id
               or session.conversation_state.get('edit_saved_cv_id') == cv.id):
        # Approved proposals are immutable. Retrying approval must not replay
        # subset indexes against reordered saved entries or later manual edits.
        return cv, []
    document, warnings = build_chat_document(session, current=cv.data if cv else None)
    if cv:
        if document == cv.data:
            session.conversation_state['chat_saved_cv_id'] = cv.id
            session.save(update_fields=['conversation_state', 'updated_at'])
            return cv, warnings
        if expected_version is None:
            raise ChatImportConflict("Retrieve the saved CV's current version before saving these details.")
        cv = services.update_cv(user=user, cv_id=cv.id, values={"data": document, "expected_version": expected_version})
    else:
        name = session.conversation_state.get('cv_name') or (document["meta"]["target_role"] or "AI-assisted") + " CV"
        cv = services.create_cv(user=user, values={"name": name[:255], "data": document})
        session.cv_id = cv.id
        session.save(update_fields=["cv_id", "updated_at"])
    if editing:
        session.conversation_state['edit_saved_cv_id'] = cv.id
        session.save(update_fields=['conversation_state', 'updated_at'])
    session.conversation_state['chat_saved_cv_id'] = cv.id
    session.save(update_fields=['conversation_state', 'updated_at'])
    return cv, warnings
