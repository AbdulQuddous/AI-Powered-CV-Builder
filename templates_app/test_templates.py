# tests/test_templates.py

from django.test import TestCase
from rest_framework.test import APIClient

from templates_app.models import CVTemplate


class TemplateAPITests(TestCase):

    def setUp(self):

        self.client = APIClient()

        CVTemplate.objects.all().update(is_available=False)
        self.modern, _ = CVTemplate.objects.update_or_create(
            id="modern", defaults=dict(
            name="Modern",
            description="Modern professional template",
            category="modern",
            ats_compatible=True,
            supported_levels=[
                "fresher",
                "junior",
                "mid"
            ],
            supported_roles=[
                "software_engineering",
                "backend"
            ],
            preview_image=(
                "cv_templates/previews/modern.png"
            ),
            template_path="cv_templates/modern.html",
            is_available=True)
        )

        self.disabled = CVTemplate.objects.create(
            id="disabled-template",
            name="Disabled Template",
            category="professional",
            ats_compatible=True,
            supported_levels=["fresher"],
            supported_roles=["general"],
            template_path=(
                "cv_templates/disabled.html"
            ),
            is_available=False
        )

    def test_list_templates(self):

        response = self.client.get(
            "/api/templates/"
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            len(response.data),
            1
        )

        self.assertEqual(
            response.data[0]["id"],
            "modern"
        )

    def test_get_template_detail(self):

        response = self.client.get(
            "/api/templates/modern/"
        )

        self.assertEqual(
            response.status_code,
            200
        )

        self.assertEqual(
            response.data["name"],
            "Modern"
        )

        self.assertTrue(
            response.data["ats_compatible"]
        )

    def test_invalid_template_returns_404(self):

        response = self.client.get(
            "/api/templates/not-found/"
        )

        self.assertEqual(
            response.status_code,
            404
        )

    def test_disabled_template_not_listed(self):

        response = self.client.get(
            "/api/templates/"
        )

        ids = [
            item["id"]
            for item in response.data
        ]

        self.assertNotIn(
            "disabled-template",
            ids
        )

    def test_disabled_template_detail_returns_404(self):

        response = self.client.get(
            "/api/templates/disabled-template/"
        )

        self.assertEqual(
            response.status_code,
            404
        )

    def test_template_path_not_exposed(self):

        response = self.client.get(
            "/api/templates/modern/"
        )

        self.assertNotIn(
            "template_path",
            response.data
        )
