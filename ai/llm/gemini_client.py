import json
import logging

from django.conf import settings
from google import genai
from google.genai import types
from google.genai.errors import APIError
import httpx

from ai.exceptions import (
    AIProviderError,
    AIStructuredOutputError,
)
logger = logging.getLogger(__name__)


def _enum_value(value, enum_class):
    """Return only SDK-defined metadata values, never arbitrary provider text."""
    if isinstance(value, enum_class):
        return value.value
    if isinstance(value, str) and value in {item.value for item in enum_class}:
        return value
    return None


def _token_count(usage, name):
    value = getattr(usage, name, None)
    return value if type(value) is int and value >= 0 else None


def provider_failure_reason(error):
    """Return fixed codes only; SDK messages may contain credentials or CV text."""
    if isinstance(error, APIError):
        details = error.details.get('error', {}) if isinstance(error.details, dict) else {}
        detail_items = details.get('details', []) if isinstance(details, dict) else []
        detail_items = detail_items if isinstance(detail_items, list) else []
        reasons = {item.get('reason') for item in detail_items
                   if isinstance(item, dict) and isinstance(item.get('reason'), str)}
        if reasons & {'API_KEY_INVALID', 'API_KEY_EXPIRED'}:
            return 'authentication_failed'
        return {400: 'invalid_request', 401: 'authentication_failed',
                403: 'permission_denied', 404: 'model_not_found',
                408: 'timeout', 429: 'quota_exceeded', 504: 'timeout'}.get(
                    error.code if type(error.code) is int else None, 'provider_unavailable')
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return 'timeout'
    if isinstance(error, httpx.TransportError):
        return 'connection_failed'
    return 'provider_unavailable'


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
                "Gemini API key is not configured.", reason='configuration_error',
            )

        self.model = settings.M6_GEMINI_MODEL

        try:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=settings.M6_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as exc:
            raise AIProviderError('Gemini client could not be configured.', reason='configuration_error') from exc

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
            reason = provider_failure_reason(exc)
            code = getattr(exc, 'code', None)
            safe_code = code if type(code) is int and 100 <= code <= 599 else None
            logger.warning('M6 Gemini request failed. reason=%s upstream_code=%s', reason, safe_code)
            raise AIProviderError(
                "Gemini request failed.", reason=reason,
            ) from exc

        candidates = getattr(response, "candidates", None) or []
        finish_reason = _enum_value(
            getattr(candidates[0], "finish_reason", None) if candidates else None,
            types.FinishReason,
        )
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = _enum_value(getattr(feedback, "block_reason", None), types.BlockedReason)
        text = response.text or ""

        def reject(reason):
            usage = getattr(response, "usage_metadata", None)
            logger.warning(
                "M6 Gemini structured output invalid. "
                "reason=%s model=%s finish_reason=%s block_reason=%s "
                "output_characters=%s output_tokens=%s thought_tokens=%s "
                "total_tokens=%s max_output_tokens=%s",
                reason,
                self.model,
                finish_reason,
                block_reason,
                len(text),
                _token_count(usage, "candidates_token_count"),
                _token_count(usage, "thoughts_token_count"),
                _token_count(usage, "total_token_count"),
                max_output_tokens,
            )
            raise AIStructuredOutputError(
                "Gemini returned invalid structured output.", reason=reason,
            )

        # Even parseable JSON may be only part of the requested review after a
        # token limit. Never cache or approve an incomplete provider response.
        if finish_reason == "MAX_TOKENS":
            reject("response_truncated")
        if (block_reason and block_reason != "BLOCKED_REASON_UNSPECIFIED") or finish_reason in {
            "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
            "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION",
        }:
            reject("response_blocked")

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed
        if not text.strip():
            reject("response_empty")
        try:
            result = json.loads(text)
        except (ValueError, TypeError):
            reject("response_invalid_json")
        if not isinstance(result, dict):
            reject("response_invalid_structure")
        return result
