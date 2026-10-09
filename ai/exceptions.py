class AIError(Exception):
    """Base exception for the M6 module."""


class InvalidAIInputError(AIError):
    """Invalid input supplied to an AI service."""


class AIProviderError(AIError):
    """External AI provider could not complete a request."""


class AIStructuredOutputError(AIError):
    """AI output does not match the expected structure."""