from typing import Any, Protocol


class LLMInterface(Protocol):
    """
    Contract used by every M6 AI service.

    Business services must never depend directly
    on the Gemini SDK.
    """

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        ...