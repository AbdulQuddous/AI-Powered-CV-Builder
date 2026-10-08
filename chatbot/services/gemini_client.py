import json

from django.conf import settings
from openai import (
    OpenAI,
    RateLimitError,
)

from chatbot.services.response_validator import (
    CHAT_RESPONSE_SCHEMA,
    InvalidAIResponse,
    validate_ai_response,
)


class AIServiceError(Exception):
    pass


class AIRateLimitError(AIServiceError):
    pass


class GeminiClient:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise AIServiceError(
                "GEMINI_API_KEY is not configured."
            )

        self.client = OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_BASE_URL,
        )

        self.model = settings.GEMINI_MODEL

    def generate(self, messages):
        try:
            response = (
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": (
                                "cv_conversation_response"
                            ),
                            "strict": True,
                            "schema": (
                                CHAT_RESPONSE_SCHEMA
                            ),
                        },
                    },
                )
            )

            content = (
                response
                .choices[0]
                .message
                .content
            )

            if not content:
                raise AIServiceError(
                    "Gemini returned an empty response."
                )

            data = json.loads(content)

            validate_ai_response(data)

            return data

        except RateLimitError as exc:
            raise AIRateLimitError(
                "Gemini rate limit exceeded."
            ) from exc

        except InvalidAIResponse:
            raise

        except json.JSONDecodeError as exc:
            raise AIServiceError(
                "Gemini returned invalid JSON."
            ) from exc

        except AIServiceError:
            raise

        except Exception as exc:
            raise AIServiceError(
                "Gemini API request failed."
            ) from exc