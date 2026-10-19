import json

from jsonschema import validate, ValidationError

from ai.exceptions import (
    InvalidAIInputError,
    AIStructuredOutputError,
)
from ai.llm.factory import get_llm_provider
from ai.prompts.cv_tasks import WRITING_SYSTEM
from ai.schemas.contracts import WRITING_SCHEMA
from ai.services.cache import cached_ai_result
from ai.services.tailoring import wording_rejection, log_validation_failure


def improve_text(
    text,
    *,
    user_id,
    section,
    target_role="",
    job_description="",
    mode="rewrite",
    llm=None,
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

    payload = {
        "text": text,
        "section": section,
        "target_role": target_role,
        "job_description": job_description,
        "mode": mode,
    }

    def checked_response(response):
        try:
            validate(instance=response, schema=WRITING_SCHEMA)
        except ValidationError as exc:
            raise AIStructuredOutputError('Invalid rewriting response.', reason='schema_invalid') from exc
        rewritten = response['rewritten']
        if len(rewritten) > 5000:
            raise AIStructuredOutputError('Rewritten content exceeds the supported length.', reason='schema_invalid')
        # The JD guides relevance, but only the selected text establishes facts.
        reason = wording_rejection(text, rewritten, text, allow_existing_contacts=True)
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
                "only facts in the selected text. Lead with relevant evidence rather than "
                "only substituting synonyms. Preserve facts and proficiency levels. "
                "Explain the actual improvements in the change notes.\n\n"
                + json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
            schema=WRITING_SCHEMA,
            max_output_tokens=2500,
        )

        return checked_response(response)

    response, cache_hit = cached_ai_result(
        user_id=user_id,
        operation=f"cv_{mode}_v2",
        payload=payload,
        generate=generate,
    )
    response = checked_response(response)

    return {
        "original": text,
        "rewritten": response["rewritten"],
        "changes": response["changes"],
        "cached": cache_hit,
    }
