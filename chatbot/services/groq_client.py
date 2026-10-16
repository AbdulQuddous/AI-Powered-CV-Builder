import json

from django.conf import settings
from openai import OpenAI

from chatbot.services.response_validator import (
    CHAT_RESPONSE_SCHEMA,
    InvalidAIResponse,
    validate_ai_response,
)


from chatbot.services.errors import AIServiceError


class GroqClient:
    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise AIServiceError(
                "GROQ_API_KEY is not configured."
            )

        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=settings.GROQ_BASE_URL,
        )

        self.model = settings.GROQ_MODEL

    def generate(self, messages):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "cv_conversation_response",
                        "strict": True,
                        "schema": CHAT_RESPONSE_SCHEMA,
                    },
                },
            )

            content = (
                response.choices[0]
                .message
                .content
            )

            if not content:
                raise AIServiceError(
                    "AI returned an empty response."
                )

            data = json.loads(content)

            validate_ai_response(data)

            return data

        except InvalidAIResponse:
            raise

        except json.JSONDecodeError as exc:
            raise AIServiceError(
                "AI returned invalid JSON."
            ) from exc

        except Exception as exc:
            raise AIServiceError(
                "Groq API request failed."
            ) from exc
