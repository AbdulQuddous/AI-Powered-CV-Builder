class AIError(Exception):
    """Base exception for the M6 module."""


class InvalidAIInputError(AIError):
    """Invalid input supplied to an AI service."""


class AIProviderError(AIError):
    """External AI provider could not complete a request."""

    REASONS = frozenset({
        'provider_unavailable', 'configuration_error', 'authentication_failed',
        'permission_denied', 'quota_exceeded', 'model_not_found',
        'invalid_request', 'timeout', 'connection_failed',
    })

    def __init__(self, message, *, reason='provider_unavailable'):
        super().__init__(message)
        self.reason = reason if reason in self.REASONS else 'provider_unavailable'


class AIStructuredOutputError(AIError):
    """AI output was rejected, with an optional content-free diagnostic reason."""

    REASONS = frozenset({
        "ai_output_invalid", "factual_validation", "schema_invalid", "source_mismatch",
        "response_invalid_json", "response_truncated", "response_empty",
        "response_invalid_structure", "response_blocked",
    })

    def __init__(self, message, *, reason="ai_output_invalid"):
        super().__init__(message)
        # Only fixed server-owned codes may reach logs or the API response.
        self.reason = reason if reason in self.REASONS else "ai_output_invalid"
