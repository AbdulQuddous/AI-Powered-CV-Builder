from django.conf import settings

from ai.exceptions import AIProviderError
from ai.llm.gemini_client import GeminiProvider


def get_llm_provider():
    provider = getattr(
        settings,
        "M6_AI_PROVIDER",
        "gemini",
    )

    if provider == "gemini":
        return GeminiProvider()

    raise AIProviderError(
        "Unsupported AI provider."
    )