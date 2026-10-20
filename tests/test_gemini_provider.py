"""Exercise the installed Gemini SDK response boundary without network access."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from google.genai import types
from google.genai.errors import APIError
import httpx
from rest_framework import serializers

from ai.exceptions import AIProviderError, AIStructuredOutputError
from ai.llm.gemini_client import GeminiProvider
from ai.views import BaseAIAPIView


@override_settings(
    GEMINI_API_KEY="test-only-no-real-provider-access",
    M6_GEMINI_MODEL="test-gemini",
    M6_TIMEOUT_MS=1000,
)
class GeminiProviderTests(SimpleTestCase):
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["summary", "changes", "suggestions"],
        "properties": {
            "summary": {"type": "string"},
            "changes": {"type": "array", "items": {"type": "object"}},
            "suggestions": {"type": "array", "items": {"type": "string"}},
        },
    }
    result = {"summary": "Clearer wording.", "changes": [], "suggestions": []}
    private_text = "private-name private-email@example.com private-provider-key"

    def setUp(self):
        self.client_patch = patch("ai.llm.gemini_client.genai.Client")
        self.client_factory = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = self.client_factory.return_value
        self.provider = GeminiProvider()

    def response(self, text=None, *, finish_reason=types.FinishReason.STOP, **kwargs):
        parts = [types.Part.from_text(text=text)] if text is not None else []
        return types.GenerateContentResponse(
            candidates=[types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=finish_reason,
            )],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                candidates_token_count=42, thoughts_token_count=17, total_token_count=103,
            ),
            **kwargs,
        )

    def generate(self, response):
        self.client.models.generate_content.return_value = response
        return self.provider.generate_structured(
            system_prompt="Return a review.", user_prompt=self.private_text,
            schema=self.schema, max_output_tokens=12000,
        )

    def assert_rejected(self, response, reason):
        with self.assertLogs("ai.llm.gemini_client", level="WARNING") as captured:
            with self.assertRaises(AIStructuredOutputError) as error:
                self.generate(response)
        self.assertEqual(error.exception.reason, reason)
        log = "\n".join(captured.output)
        self.assertIn("reason=" + reason, log)
        self.assertIn("model=test-gemini", log)
        self.assertIn("max_output_tokens=12000", log)
        for private in self.private_text.split():
            self.assertNotIn(private, log)
        self.assertTrue(all(record.exc_info is None for record in captured.records))
        self.client.models.generate_content.assert_called_once()
        return log

    def test_sdk_parsed_dictionary_and_native_json_schema_are_supported(self):
        wire = self.response(json.dumps(self.result)).model_dump(exclude_none=True)
        response = types.GenerateContentResponse._from_response(
            response=wire, kwargs={"config": {"response_json_schema": self.schema}},
        )
        self.assertEqual(response.parsed, self.result)
        self.assertEqual(self.generate(response), self.result)
        config = self.client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_json_schema, self.schema)
        self.assertIsNone(config.response_schema)
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.max_output_tokens, 12000)
        self.assertEqual(self.client_factory.call_args.kwargs["http_options"].retry_options.attempts, 1)

    def test_json_text_is_parsed_when_sdk_parsed_value_is_unavailable(self):
        response = self.response(json.dumps(self.result))
        self.assertIsNone(response.parsed)
        self.assertEqual(self.generate(response), self.result)

    def test_malformed_json_logs_only_fixed_metadata(self):
        log = self.assert_rejected(self.response('{"private":"' + self.private_text), "response_invalid_json")
        self.assertIn("finish_reason=STOP", log)
        self.assertIn("output_tokens=42", log)
        self.assertIn("thought_tokens=17", log)
        self.assertIn("total_tokens=103", log)

    def test_non_object_json_is_rejected(self):
        self.assert_rejected(self.response("[]"), "response_invalid_structure")

    def test_empty_response_with_missing_candidates_is_reported_safely(self):
        log = self.assert_rejected(types.GenerateContentResponse(), "response_empty")
        self.assertIn("finish_reason=None", log)
        self.assertIn("output_characters=0", log)

    def test_empty_safety_candidate_is_reported_without_provider_text(self):
        log = self.assert_rejected(self.response(finish_reason=types.FinishReason.SAFETY), "response_blocked")
        self.assertIn("finish_reason=SAFETY", log)

    def test_prompt_block_without_candidates_hides_block_message(self):
        response = types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY,
                block_reason_message=self.private_text,
            ),
        )
        log = self.assert_rejected(response, "response_blocked")
        self.assertIn("block_reason=SAFETY", log)

    def test_truncated_json_reports_the_token_limit(self):
        log = self.assert_rejected(self.response(
            '{"summary":"' + self.private_text, finish_reason=types.FinishReason.MAX_TOKENS,
        ), "response_truncated")
        self.assertIn("finish_reason=MAX_TOKENS", log)

    def test_token_limit_rejects_even_a_parseable_partial_review(self):
        self.assert_rejected(self.response(
            json.dumps(self.result), finish_reason=types.FinishReason.MAX_TOKENS,
            parsed=self.result,
        ), "response_truncated")

    def test_sdk_failure_stays_a_safe_provider_error_and_is_not_retried(self):
        self.client.models.generate_content.side_effect = RuntimeError(self.private_text)
        with self.assertRaises(AIProviderError) as error:
            self.generate(None)
        self.assertEqual(str(error.exception), "Gemini request failed.")
        self.client.models.generate_content.assert_called_once()

    def test_sdk_failure_maps_to_503_without_exposing_details(self):
        self.client.models.generate_content.side_effect = RuntimeError(self.private_text)
        response = BaseAIAPIView().execute(
            serializers.Serializer, SimpleNamespace(data={}), lambda data: self.generate(None),
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"]["code"], "ai_provider_unavailable")
        for private in self.private_text.split():
            self.assertNotIn(private, json.dumps(response.data))

    def test_structured_failure_exports_only_a_fixed_reason(self):
        with self.assertLogs("ai", level="WARNING") as captured:
            response = BaseAIAPIView().execute(
                serializers.Serializer, SimpleNamespace(data={}),
                lambda data: self.generate(self.response(self.private_text)),
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"]["code"], "ai_output_invalid")
        self.assertEqual(response.data["error"]["reason"], "response_invalid_json")
        exposed = json.dumps(response.data) + "\n".join(captured.output)
        for private in self.private_text.split():
            self.assertNotIn(private, exposed)

    def test_legacy_errors_and_unknown_reasons_keep_existing_api_contract(self):
        for reason in ("ai_output_invalid", self.private_text):
            with self.subTest(reason="default" if reason == "ai_output_invalid" else "unrecognised"):
                handler = Mock(side_effect=AIStructuredOutputError(self.private_text, reason=reason))
                with self.assertLogs("ai.views", level="WARNING") as captured:
                    response = BaseAIAPIView().execute(serializers.Serializer, SimpleNamespace(data={}), handler)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.data["error"], {
                    "code": "ai_output_invalid", "message": "AI returned an invalid response.",
                })
                self.assertNotIn(self.private_text, "\n".join(captured.output))

    def test_tailoring_rejection_reasons_are_supported(self):
        for reason in ("factual_validation", "schema_invalid", "source_mismatch"):
            with self.subTest(reason=reason):
                handler = Mock(side_effect=AIStructuredOutputError(self.private_text, reason=reason))
                with self.assertLogs("ai.views", level="WARNING"):
                    response = BaseAIAPIView().execute(serializers.Serializer, SimpleNamespace(data={}), handler)
                self.assertEqual(response.data["error"]["reason"], reason)

    def test_sdk_http_failures_expose_fixed_reasons_without_raw_details_or_retries(self):
        for code, reason in [(400, 'invalid_request'), (401, 'authentication_failed'),
                             (403, 'permission_denied'), (404, 'model_not_found'),
                             (429, 'quota_exceeded'), (500, 'provider_unavailable'), (504, 'timeout')]:
            with self.subTest(code=code):
                self.client.models.generate_content.reset_mock()
                self.client.models.generate_content.side_effect = APIError(code, {
                    'error': {'message': self.private_text, 'status': 'UNTRUSTED_PRIVATE_STATUS'}})
                with self.assertLogs('ai', level='WARNING') as logs:
                    response = BaseAIAPIView().execute(serializers.Serializer, SimpleNamespace(data={}), lambda data: self.generate(None))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data['error']['code'], 'ai_provider_unavailable')
                self.assertEqual(response.data['error'].get('reason', 'provider_unavailable'), reason)
                self.client.models.generate_content.assert_called_once()
                exposed = json.dumps(response.data) + '\n'.join(logs.output)
                self.assertIn('reason=' + reason, exposed)
                self.assertIn('upstream_code=' + str(code), exposed)
                for value in [*self.private_text.split(), 'UNTRUSTED_PRIVATE_STATUS']:
                    self.assertNotIn(value, exposed)
                self.assertTrue(all(record.exc_info is None for record in logs.records))

    def test_invalid_api_key_metadata_is_classified_without_reading_provider_message(self):
        self.client.models.generate_content.side_effect = APIError(400, {'error': {
            'message': self.private_text, 'details': [{'reason': 'API_KEY_INVALID'}]}})
        with self.assertRaises(AIProviderError) as error:
            self.generate(None)
        self.assertEqual(error.exception.reason, 'authentication_failed')

    def test_timeout_connection_and_malformed_error_details_are_safe(self):
        for cause, reason in [(httpx.ReadTimeout(self.private_text), 'timeout'),
                              (httpx.ConnectError(self.private_text), 'connection_failed'),
                              (APIError(400, {'error': {'message': self.private_text, 'details': None}}), 'invalid_request')]:
            with self.subTest(reason=reason):
                self.client.models.generate_content.side_effect = cause
                with self.assertRaises(AIProviderError) as error:
                    self.generate(None)
                self.assertEqual(error.exception.reason, reason)
                self.assertNotIn(self.private_text, str(error.exception))

    def test_missing_key_or_sdk_initialization_error_is_a_configuration_failure(self):
        self.client_factory.reset_mock()
        with override_settings(GEMINI_API_KEY=''), self.assertRaises(AIProviderError) as error:
            GeminiProvider()
        self.assertEqual(error.exception.reason, 'configuration_error')
        self.client_factory.assert_not_called()
        self.client_factory.side_effect = ValueError(self.private_text)
        with self.assertRaises(AIProviderError) as error:
            GeminiProvider()
        self.assertEqual(error.exception.reason, 'configuration_error')
        self.assertNotIn(self.private_text, str(error.exception))

    def test_unknown_provider_reason_is_not_exposed_in_response_or_logs(self):
        error = AIProviderError(self.private_text, reason=self.private_text)
        with self.assertLogs('ai.views', level='WARNING') as logs:
            response = BaseAIAPIView().execute(serializers.Serializer, SimpleNamespace(data={}), Mock(side_effect=error))
        self.assertEqual(response.data['error']['code'], 'ai_provider_unavailable')
        self.assertNotIn('reason', response.data['error'])
        self.assertNotIn(self.private_text, json.dumps(response.data) + '\n'.join(logs.output))
