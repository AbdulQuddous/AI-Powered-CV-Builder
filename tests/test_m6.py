from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from ai.exceptions import AIStructuredOutputError
from ai.services.writing import improve_text
from ai.services.analysis import analyze_cv
from ai.validators.rules import validate_cv_rules


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        return self.response


@override_settings(
    M6_GEMINI_MODEL="test-gemini",
    M6_CACHE_SECONDS=3600,
)
class M6Tests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def test_rewriting_uses_one_call(self):
        fake = FakeLLM({
            "rewritten": "Developed APIs using Django.",
            "changes": ["Improved wording"],
        })

        result = improve_text(
            "made APIs using django",
            user_id=1,
            section="experience",
            llm=fake,
        )

        self.assertEqual(fake.calls, 1)
        self.assertFalse(result["cached"])

    def test_identical_rewrite_uses_cache(self):
        fake = FakeLLM({
            "rewritten": "Developed APIs using Django.",
            "changes": ["Improved wording"],
        })

        arguments = {
            "text": "made APIs using django",
            "user_id": 1,
            "section": "experience",
            "llm": fake,
        }

        first = improve_text(**arguments)
        second = improve_text(**arguments)

        self.assertEqual(fake.calls, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])

    def test_rewriting_rejects_invented_numbers(self):
        fake = FakeLLM({
            "rewritten": (
                "Improved API performance by 60%."
            ),
            "changes": ["Added performance metric"],
        })

        with self.assertRaises(
            AIStructuredOutputError
        ):
            improve_text(
                "Worked on Django APIs.",
                user_id=1,
                section="experience",
                llm=fake,
            )

    @patch(
        "ai.validators.rules.get_cv_errors",
        return_value=[],
    )
    def test_rule_validation_is_local(self, mock_schema):
        cv = {
            "personal": {
                "full_name": "Ali",
                "email": "",
                "phone": "",
            },
            "skills": [
                "Python",
                "Django",
                "Python",
            ],
        }

        result = validate_cv_rules(cv)

        codes = {
            item["code"]
            for item in result["warnings"]
        }

        self.assertIn(
            "DUPLICATE_SKILLS",
            codes,
        )

        self.assertIn(
            "MISSING_EMAIL",
            codes,
        )

    @patch(
        "ai.validators.rules.get_cv_errors",
        return_value=[],
    )
    def test_basic_analysis_does_not_call_ai(
        self,
        mock_schema,
    ):
        fake = FakeLLM({
            "suggestions": [],
            "strengths": [],
            "gaps": [],
            "match_score": 0,
        })

        cv = {
            "personal": {
                "full_name": "Ali",
                "email": "ali@example.com",
                "phone": "03000000000",
            },
            "summary": "Python developer",
            "skills": ["Python"],
            "education": [],
        }

        result = analyze_cv(
            cv,
            user_id=1,
            use_ai=False,
            llm=fake,
        )

        self.assertEqual(fake.calls, 0)
        self.assertEqual(result["source"], "rules")

    @patch(
        "ai.validators.rules.get_cv_errors",
        return_value=[],
    )
    def test_combined_analysis_reuses_result(
        self,
        mock_schema,
    ):
        fake = FakeLLM({
            "suggestions": [],
            "strengths": ["Python", "Django"],
            "gaps": ["Testing"],
            "match_score": 75,
        })

        cv = {
            "personal": {
                "full_name": "Ali",
                "email": "ali@example.com",
                "phone": "03000000000",
            },
            "summary": "Python developer",
            "skills": ["Python", "Django"],
            "education": [],
        }

        arguments = {
            "cv": cv,
            "user_id": 1,
            "target_role": "Backend Developer",
            "use_ai": True,
            "llm": fake,
        }

        first = analyze_cv(**arguments)
        second = analyze_cv(**arguments)

        self.assertEqual(fake.calls, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])