from ai.exceptions import (
    InvalidAIInputError,
    AIStructuredOutputError,
)
from ai.llm.factory import get_llm_provider
from ai.prompts.cv_tasks import EXTRACTION_SYSTEM
from ai.schemas.contracts import (
    get_cv_errors,
    load_cv_schema,
    gemini_compatible_schema,
)
from ai.services.cache import cached_ai_result
import logging
from jsonschema import validators
from ai.services.normalization import normalize_extracted_cv
logger = logging.getLogger(__name__)

def extract_cv(
    raw_text,
    *,
    user_id,
    llm=None,
):
    if not isinstance(raw_text, str):
        raise InvalidAIInputError(
            "Raw CV text must be a string."
        )

    raw_text = raw_text.strip()

    if len(raw_text) < 20:
        raise InvalidAIInputError(
            "Not enough CV text was provided."
        )

    if len(raw_text) > 20000:
        raise InvalidAIInputError(
            "CV text exceeds the supported limit."
        )

    schema = load_cv_schema()
    provider_schema = gemini_compatible_schema(schema)

    def generate():
        provider = llm or get_llm_provider()

        extracted = provider.generate_structured(
            system_prompt=EXTRACTION_SYSTEM,
            user_prompt=(
                "Extract all supported CV information.\n"
                "Include every required field.\n"
                "Use empty strings for unknown string values.\n"
                "Use empty arrays for missing collections.\n"
                "Use YYYY-MM for dates only when the month "
                "is explicitly available.\n"
                "If only the year is known, use an empty "
                "date string.\n"
                "Never invent missing information.\n\n"
                "<cv_document>\n"
                f"{raw_text}\n"
                "</cv_document>"
            ),
            schema=provider_schema,
            max_output_tokens=8192,
        )

        # Fix safe formatting problems locally.
        cv, warnings = normalize_extracted_cv(
            extracted
        )

        # Validate against authoritative M10 schema.
        errors = get_cv_errors(cv)

        if errors:
            schema_validator = (
                validators.validator_for(schema)(schema)
            )

            details = [
                {
                    "field": ".".join(
                        map(str, error.absolute_path)
                    ) or "$",
                    "rule": error.validator,
                }
                for error in schema_validator.iter_errors(cv)
            ]

            logger.warning(
                "M6 extraction schema errors: %s",
                details[:15],
            )

            raise AIStructuredOutputError(
                "Extracted CV failed M10 validation."
            )

        return {
            "cv": cv,
            "warnings": warnings,
        }

    result, cache_hit = cached_ai_result(
        user_id=user_id,
        operation="cv_extraction_v2",
        payload={
            "raw_text": raw_text,
            "schema": schema,
        },
        generate=generate,
    )

    return {
        **result,
        "cached": cache_hit,
    }