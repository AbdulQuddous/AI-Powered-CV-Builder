"""Synthesis must preserve who did what and what an existing metric measures."""
from django.test import SimpleTestCase

from ai.exceptions import AIStructuredOutputError
from ai.services.tailoring import validate_response, wording_rejection, writable_text


class TailoringClaimAssociationTests(SimpleTestCase):
    def check_whole_review(self, context, path, rewritten):
        fields = writable_text(context)
        return validate_response({
            "summary": "Focused the wording on supported work.", "suggestions": [],
            "changes": [{"path": path, "original": fields[path], "rewritten": rewritten,
                         "reason": "Focus on relevant confirmed contributions."}],
        }, fields, context, [])

    def test_an_education_year_cannot_become_an_application_count(self):
        original = "Python developer."
        rewritten = "Python developer who built 2026 applications."
        context = {"summary": original, "education": [{"end_date": "2026-06"}],
                   "projects": [{"description": "Built a Python application."}]}
        self.assertIsNotNone(wording_rejection(original, rewritten, context, allow_synthesis=True))
        with self.assertRaises(AIStructuredOutputError):
            self.check_whole_review(context, "/summary", rewritten)

    def test_another_person_leading_the_team_cannot_establish_candidate_leadership(self):
        original = "Built Django APIs."
        rewritten = "Built Django APIs and led the development team."
        entry = {"company": "Example Systems", "job_title": "Developer Intern", "highlights": [
            original, "Worked with a team led by the engineering manager."]}
        self.assertIsNotNone(wording_rejection(original, rewritten, entry, allow_synthesis=True))
        with self.assertRaises(AIStructuredOutputError):
            self.check_whole_review({"experience": [entry]}, "/experience/0/highlights/0", rewritten)

    def test_a_listed_tool_cannot_be_attached_to_an_unrelated_deployment(self):
        original = "Python developer."
        rewritten = "Python developer deploying Kubernetes applications."
        context = {"summary": original, "skills": ["Python", "Kubernetes"], "projects": [
            {"description": "Deployed a Python application using Docker."}]}
        self.assertIsNotNone(wording_rejection(original, rewritten, context, allow_synthesis=True))
        with self.assertRaises(AIStructuredOutputError):
            self.check_whole_review(context, "/summary", rewritten)

    def test_an_entrys_review_count_cannot_become_its_api_count(self):
        original = "Built Django APIs."
        rewritten = "Built 5 Django APIs."
        entry = {"company": "Example Systems", "highlights": [original, "Reviewed 5 pull requests."]}
        self.assertIsNotNone(wording_rejection(original, rewritten, entry, allow_synthesis=True))
        with self.assertRaises(AIStructuredOutputError):
            self.check_whole_review({"experience": [entry]}, "/experience/0/highlights/0", rewritten)

    def test_summary_can_synthesize_an_explicit_source_action_and_tool_pair(self):
        original = "Python developer."
        rewritten = "Python developer who deployed an application using Docker and AWS."
        context = {"summary": original, "projects": [
            {"description": "Deployed a Python application using Docker and AWS."}]}
        self.assertIsNone(wording_rejection(original, rewritten, context, allow_synthesis=True))
        checked = self.check_whole_review(context, "/summary", rewritten)
        self.assertEqual(checked["changes"][0]["rewritten"], rewritten)

    def test_work_can_include_an_explicit_action_and_tool_from_its_own_entry(self):
        original = "Built Django APIs."
        rewritten = "Built Django APIs and deployed a Django application using Docker."
        entry = {"company": "Example Systems", "highlights": [
            original, "Deployed a Django application using Docker."]}
        self.assertIsNone(wording_rejection(original, rewritten, entry, allow_synthesis=True))
        checked = self.check_whole_review({"experience": [entry]}, "/experience/0/highlights/0", rewritten)
        self.assertEqual(checked["changes"][0]["rewritten"], rewritten)

    def test_metric_retention_and_equivalent_number_spelling_remain_supported(self):
        original = "Built 2 applications using Django."
        entry = {"highlights": [original, "Reviewed 5 pull requests."]}
        for rewritten in ("Developed 2 applications using Django.", "Developed two applications using Django."):
            with self.subTest(rewritten=rewritten):
                self.assertIsNone(wording_rejection(original, rewritten, entry, allow_synthesis=True))
        for rewritten in ("Developed applications using Django.", "Built 5 applications using Django."):
            with self.subTest(rewritten=rewritten):
                self.assertIsNotNone(wording_rejection(original, rewritten, entry, allow_synthesis=True))
