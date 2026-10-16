import json
import re

from jsonschema import validate, ValidationError

from ai.exceptions import (
    InvalidAIInputError,
    AIStructuredOutputError,
)
from ai.llm.factory import get_llm_provider
from ai.prompts.cv_tasks import WRITING_SYSTEM
from ai.schemas.contracts import WRITING_SCHEMA
from ai.services.cache import cached_ai_result


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

    def generate():
        provider = llm or get_llm_provider()

        response = provider.generate_structured(
            system_prompt=WRITING_SYSTEM,
            user_prompt=(
                f"Operation: {mode}\n"
                "Improve the following CV content while "
                "preserving all factual information.\n\n"
                + json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
            schema=WRITING_SCHEMA,
            max_output_tokens=2500,
        )

        try:
            validate(
                instance=response,
                schema=WRITING_SCHEMA,
            )
        except ValidationError as exc:
            raise AIStructuredOutputError(
                "Invalid rewriting response."
            ) from exc

        rewritten = response["rewritten"]

        # Reject newly introduced numerical claims.
        # This is a defensive check, not a full
        # factual-consistency guarantee.
        source_numbers = set(
            re.findall(
                r"\b\d+(?:[.,]\d+)*%?",
                text,
            )
        )

        output_numbers = set(
            re.findall(
                r"\b\d+(?:[.,]\d+)*%?",
                rewritten,
            )
        )

        if output_numbers - source_numbers:
            raise AIStructuredOutputError(
                "Rewritten content contains unsupported numbers."
            )

        return response

    response, cache_hit = cached_ai_result(
        user_id=user_id,
        operation=f"cv_{mode}",
        payload=payload,
        generate=generate,
    )

    return {
        "original": text,
        "rewritten": response["rewritten"],
        "changes": response["changes"],
        "cached": cache_hit,
    }
