import json

from django.conf import settings
from google import genai
from google.genai import types

from ai.exceptions import (
    AIProviderError,
    AIStructuredOutputError,
)
import logging

logger = logging.getLogger(__name__)

class GeminiProvider:
    """
    Gemini implementation of LLMInterface.

    Exactly one generate_content invocation is made
    per service request that reaches this provider.

    SDK automatic HTTP retries are disabled.
    """

    def __init__(self):
        api_key = settings.GEMINI_API_KEY

        if not api_key:
            raise AIProviderError(
                "Gemini API key is not configured."
            )

        self.model = settings.M6_GEMINI_MODEL

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=settings.M6_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(
                    attempts=1,
                ),
            ),
        )

    def generate_structured(
        self,
        *,
        system_prompt,
        user_prompt,
        schema,
        max_output_tokens=2048,
    ):
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                ),
            )

        except Exception as exc:
            raise AIProviderError(
                "Gemini request failed."
            ) from exc

        try:
            if isinstance(response.parsed, dict):
                result = response.parsed
            else:
                result = json.loads(response.text or "")

            if not isinstance(result, dict):
                raise ValueError(
                    "Expected a JSON object."
                )

            return result

        except (ValueError, TypeError) as exc:

            finish_reason = None

            if response.candidates:
                finish_reason = str(
                    response.candidates[0].finish_reason
                )

            usage = getattr(
                response,
                "usage_metadata",
                None,
            )

            logger.warning(
                "M6 Gemini structured output invalid. "
                "model=%s finish_reason=%s "
                "output_characters=%s total_tokens=%s",
                self.model,
                finish_reason,
                len(response.text or ""),
                getattr(
                    usage,
                    "total_token_count",
                    None,
                ),
            )

            raise AIStructuredOutputError(
                "Gemini returned invalid structured output."
            ) from exc