from django.test import SimpleTestCase

from ai.services.normalization import (
    normalize_extracted_cv,
)


class M6NormalizationTests(SimpleTestCase):

    def test_missing_fields_and_year_only_dates(self):

        cv = {
            "schema_version": "1.0",
            "meta": {
                "target_role": None,
                "career_level": "fresher",
                "template_id": None,
            },
            "personal": {
                "full_name": "Ali Khan",
                "email": "ali@example.com",
                "phone": None,
            },
            "summary": None,
            "skills": ["Python", "Django"],
            "education": [
                {
                    "degree": "BS Software Engineering",
                    "institution": "Example University",
                    "start_date": None,
                    "end_date": "2026",
                }
            ],
            "experience": None,
            "projects": None,
        }

        normalized, warnings = normalize_extracted_cv(
            cv
        )

        self.assertEqual(
            normalized["meta"]["template_id"],
            "",
        )

        self.assertEqual(
            normalized["personal"]["phone"],
            "",
        )

        self.assertEqual(
            normalized["experience"],
            [],
        )

        self.assertEqual(
            normalized["education"][0]["end_date"],
            "",
        )

        self.assertTrue(
            any(
                warning["code"] == "MONTH_REQUIRED"
                and warning["original_value"] == "2026"
                for warning in warnings
            )
        )