import json

from jsonschema import validate, ValidationError

from ai.exceptions import (
    InvalidAIInputError,
    AIStructuredOutputError,
)
from ai.llm.factory import get_llm_provider
from ai.prompts.cv_tasks import WRITING_SYSTEM
from ai.schemas.contracts import WRITING_SCHEMA, gemini_compatible_schema
from ai.services.cache import cached_ai_result
from ai.services.tailoring import (
    evidence_for_path, log_validation_failure, private_strings, redact,
    source_context, wording_rejection, writable_text,
)
from ai.services.job_alignment import evidence_sources, job_requirements
from ai.services.tailoring_focus import tailoring_brief
from cvs.services import owned, check_version


def improve_text(
    text,
    *,
    user_id,
    section,
    target_role="",
    job_description="",
    mode="rewrite",
    llm=None,
    cv_id=None,
    expected_version=None,
    field_path=None,
):
    if mode not in ("rewrite", "improve"):
        raise InvalidAIInputError(
            "Unsupported writing operation."
        )

    if not isinstance(text, str) or not text.strip():
        raise InvalidAIInputError(
            "Text cannot be empty."
        )

    text = text.strip()

    if len(text) > 5000:
        raise InvalidAIInputError(
            "Text exceeds the supported limit."
        )

    if not isinstance(job_description, str) or len(job_description) > 10000:
        raise InvalidAIInputError("Job description exceeds the supported limit.")

    if not isinstance(target_role, str) or len(target_role) > 200:
        raise InvalidAIInputError('Target role exceeds the supported limit.')
    target_role, job_description = target_role.strip(), job_description.strip()
    contextual = any(value is not None for value in (cv_id, expected_version, field_path))
    evidence, sources = text, {'/selected_text': text}
    original_text = text
    personal = []
    if contextual:
        if (type(cv_id) is not int or cv_id < 1 or type(expected_version) is not int
                or expected_version < 1 or not isinstance(field_path, str)):
            raise InvalidAIInputError('Saved CV rewrites need the CV, version and selected field together.')
        cv = owned(user=user_id, cv_id=cv_id)
        check_version(cv, expected_version)
        fields = writable_text(cv.data)
        original = fields.get(field_path)
        if original is None or field_path.split('/')[1] != section:
            raise InvalidAIInputError('Choose an existing summary, work bullet, project description or achievement.')
        if ' '.join(original.split()) != ' '.join(text.split()):
            raise InvalidAIInputError('The selected text does not match the saved CV. Refresh it and choose the field again.')
        personal = private_strings(cv.data)
        if redact(original, personal) != original:
            raise InvalidAIInputError('Remove contact details from the selected wording before requesting an external rewrite.')
        context = source_context(cv.data, personal)
        evidence = evidence_for_path(field_path, original, context)
        all_sources = evidence_sources(context)
        prefix = '/' + '/'.join(field_path.strip('/').split('/')[:2]) + '/'
        sources = {path: value for path, value in all_sources.items() if (
            field_path == '/summary' or path == field_path or
            (section in ('experience', 'projects') and path.startswith(prefix)))}
        text = original.strip()
        original_text = original

    payload = {
        "text": text,
        "section": section,
        "target_role": redact(target_role, personal) if contextual else target_role,
        "job_description": redact(job_description, personal) if contextual else job_description,
        "mode": mode,
    }
    requirements = job_requirements(payload['job_description'])
    payload.update({'source_evidence': sources, 'job_requirements': requirements,
                    'tailoring_brief': tailoring_brief(section, payload['target_role'], requirements, sources,
                        selected_path=field_path if contextual else '/selected_text')})
    if contextual:
        payload.update(cv_id=cv_id, expected_version=expected_version, field_path=field_path)
    if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 100000:
        raise InvalidAIInputError('This saved CV context is too large for one rewrite. Shorten the selected entry first.')

    def checked_response(response):
        try:
            validate(instance=response, schema=WRITING_SCHEMA)
        except ValidationError as exc:
            raise AIStructuredOutputError('Invalid rewriting response.', reason='schema_invalid') from exc
        rewritten = response['rewritten']
        if len(rewritten) > 5000:
            raise AIStructuredOutputError('Rewritten content exceeds the supported length.', reason='schema_invalid')
        # The JD guides relevance; only the authorized source scope establishes facts.
        reason = wording_rejection(text, rewritten, evidence, personal, allow_existing_contacts=not contextual,
                                   allow_synthesis=contextual)
        if reason:
            log_validation_failure(reason)
            raise AIStructuredOutputError('Rewritten content changed an unsupported factual claim.', reason='factual_validation')
        return response

    def generate():
        provider = llm or get_llm_provider()

        response = provider.generate_structured(
            system_prompt=WRITING_SYSTEM,
            user_prompt=(
                f"Operation: {mode}\n"
                "Tailor the organization and emphasis to the supplied job context using "
                "only facts in source_evidence. The selected text identifies what to rewrite; "
                "source_evidence is the complete allowed factual scope. Use the tailoring_brief "
                "to lead with relevant contributions rather than "
                "only substituting synonyms. Preserve facts and proficiency levels. "
                "Explain the actual improvements in the change notes.\n\n"
                + json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
            schema=gemini_compatible_schema(WRITING_SCHEMA, compact=True),
            max_output_tokens=4000,
        )

        return checked_response(response)

    response, cache_hit = cached_ai_result(
        user_id=user_id,
        operation=f"cv_{mode}_v3",
        payload=payload,
        generate=generate,
    )
    response = checked_response(response)
    if contextual:
        check_version(owned(user=user_id, cv_id=cv_id), expected_version)

    return {
        "original": original_text,
        "rewritten": response["rewritten"],
        "changes": response["changes"],
        "cached": cache_hit,
    }
