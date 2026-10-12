from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIClient

from docx import Document

from cvs.models import CV
from templates_app.models import CVTemplate


SAMPLE_CV = {
    "schema_version": "1.0",

    "meta": {
        "target_role": "Python Django Developer",
        "career_level": "fresher",
        "template_id": "modern",
    },

    "personal": {
        "full_name": "Ali Khan",
        "email": "ali@example.com",
        "phone": "03001234567",
        "location": "Lahore",
        "linkedin": "",
        "github": "",
        "portfolio": "",
    },

    "summary": (
        "Software Engineering graduate skilled "
        "in Python and Django."
    ),

    "skills": [
        "Python",
        "Django",
        "PostgreSQL",
        "Git",
    ],

    "education": [
        {
            "institution": "Example University",
            "degree": "BS Software Engineering",
            "field_of_study": "Software Engineering",
            "start_date": "2022-09",
            "end_date": "2026-06",
            "grade": "",
        }
    ],

    "experience": [],

    "projects": [
        {
            "name": "Employee Management System",
            "description": (
                "Developed an employee management "
                "system using Django."
            ),
            "technologies": [
                "Python",
                "Django",
                "PostgreSQL",
            ],
            "url": "",
            "highlights": [
                "Implemented REST APIs."
            ],
        }
    ],

    "certifications": [],
    "achievements": [],
    "languages": [],
}


class M8RenderingTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="m8@example.com",
            password="TestPassword123!",
        )

        self.other_user = User.objects.create_user(
            email="other-m8@example.com",
            password="TestPassword123!",
        )

        self.client = APIClient()

        self.client.force_authenticate(
            user=self.user
        )

        CVTemplate.objects.update_or_create(
            id="modern",
            defaults={
                "name": "Modern",
                "description": "Modern CV template",
                "category": "professional",
                "ats_compatible": True,
                "supported_levels": ["fresher"],
                "supported_roles": [],
                "template_path": "cv_templates/modern.html",
                "is_available": True,
            },
        )

        self.cv = CV.objects.create(
            owner=self.user,
            name="M8 Test CV",
            data=SAMPLE_CV,
        )

    def test_preview_returns_html(self):

        response = self.client.get(
            f"/api/cvs/{self.cv.id}/preview/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            b"Ali Khan",
            response.content,
        )

        self.assertIn(
            b"Python Django Developer",
            response.content,
        )

    def test_pdf_export(self):

        response = self.client.post(
            f"/api/cvs/{self.cv.id}/export/pdf/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response["Content-Type"],
            "application/pdf",
        )

        self.assertTrue(
            response.content.startswith(b"%PDF")
        )

    def test_docx_export(self):

        response = self.client.post(
            f"/api/cvs/{self.cv.id}/export/docx/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        document = Document(
            BytesIO(response.content)
        )

        text = "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
        )

        self.assertIn("Ali Khan", text)

        self.assertIn(
            "Employee Management System",
            text,
        )

    def test_other_user_cannot_access_cv(self):

        self.client.force_authenticate(
            user=self.other_user
        )

        response = self.client.get(
            f"/api/cvs/{self.cv.id}/preview/"
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_unauthenticated_access(self):

        self.client.force_authenticate(
            user=None
        )

        response = self.client.get(
            f"/api/cvs/{self.cv.id}/preview/"
        )

        self.assertIn(
            response.status_code,
            [401, 403],
        )

    def test_export_does_not_modify_cv(self):

        original_version = self.cv.version

        original_data = self.cv.data.copy()

        response = self.client.post(
            f"/api/cvs/{self.cv.id}/export/pdf/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.cv.refresh_from_db()

        self.assertEqual(
            self.cv.version,
            original_version,
        )

        self.assertEqual(
            self.cv.data,
            original_data,
        )