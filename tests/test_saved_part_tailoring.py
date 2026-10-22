"""Saved-field rewrites use owner-checked CV evidence without saving a proposal."""
from copy import deepcopy
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from cvs.models import CV, CVVersion
from cvs.services import create_cv


@override_settings(M6_GEMINI_MODEL="test-gemini", M6_CACHE_SECONDS=3600)
class SavedPartTailoringTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = get_user_model().objects.create_user("saved-part@example.test", "Strong-password-123!")
        self.other = get_user_model().objects.create_user("other-part@example.test", "Strong-password-123!")
        self.client.force_authenticate(self.owner)
        self.cv = create_cv(user=self.owner, values={"name": "Synthetic developer CV", "data": {}})
        self.document = deepcopy(self.cv.data)
        self.document["meta"].update({"target_role": "Backend Developer", "career_level": "fresher", "template_id": "modern"})
        self.document["personal"].update({"full_name": "Fictional Candidate", "email": "candidate@example.test",
            "phone": "+923001234567", "location": "Rawalpindi", "linkedin": "https://private-profile.example.test"})
        self.document["summary"] = "Python developer building Django web applications."
        self.document["skills"] = ["Python", "Django", "Docker", "AWS", "Kubernetes"]
        self.document["experience"] = [{"company": "Example Systems", "job_title": "Developer Intern", "location": "",
            "start_date": "2025-01", "end_date": "", "is_current": True,
            "highlights": ["Built Django APIs.", "Tested Django endpoints."]}]
        self.document["projects"] = [
            {"name": "Recruitment Dashboard", "description": "Created a Django application.",
             "technologies": ["Django"], "url": "https://private-project.example.test", "highlights": ["Built REST APIs."]},
            {"name": "Cloud Lab", "description": "Deployed a Python application using Docker and AWS.",
             "technologies": ["Python", "Docker", "AWS"], "url": "", "highlights": []},
        ]
        self.document["achievements"] = ["Completed a Django project."]
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=["data"])
        self.payload = {"text": self.document["summary"], "section": "summary", "target_role": "Full Stack AI Developer",
            "job_description": "Build Django APIs and deploy Python applications using Docker and AWS. Integrate AI features.",
            "cv_id": self.cv.pk, "expected_version": 1, "field_path": "/summary"}
        self.factory_patch = patch("ai.services.writing.get_llm_provider")
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.provider = Mock()
        self.factory.return_value = self.provider
        self.propose("Developed Django web applications using Python.")

    def propose(self, text):
        self.provider.generate_structured.return_value = {"rewritten": text, "changes": ["Focused the wording on supported job requirements."]}

    def post(self, mode="rewrite", **overrides):
        return self.client.post(f"/api/ai/{mode}/", {**self.payload, **overrides}, format="json")

    def provider_payload(self):
        prompt = self.provider.generate_structured.call_args.kwargs["user_prompt"]
        return json.loads(prompt.rsplit("\n\n", 1)[-1])

    def assert_unchanged(self):
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)
        self.assertEqual(self.cv.version, 1)
        self.assertEqual(CVVersion.objects.filter(cv=self.cv).count(), 1)

    def test_summary_can_synthesize_saved_deployment_for_the_jd_without_saving(self):
        self.propose("Python developer building Django web applications and deploying applications using Docker and AWS.")
        for mode in ("rewrite", "improve"):
            with self.subTest(mode=mode):
                response = self.post(mode=mode)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["data"]["original"], self.document["summary"])
                self.assertIn("Docker", response.data["data"]["rewritten"])
                payload = self.provider_payload()
                self.assertIn("Deployed a Python application using Docker and AWS.", json.dumps(payload["source_evidence"]))
                self.assertTrue(payload["tailoring_brief"])
                self.assertEqual(payload["target_role"], self.payload["target_role"])
                self.assertEqual(payload["job_description"], self.payload["job_description"])
                self.assert_unchanged()
        self.assertEqual(self.provider.generate_structured.call_count, 2)

    def test_summary_evidence_omits_metadata_contacts_and_private_urls(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        payload = self.provider_payload()
        evidence = payload["source_evidence"]
        serialized = json.dumps(evidence)
        for value in (*self.document["personal"].values(), "private-project", "template_id", "career_level"):
            if value:
                self.assertNotIn(value, serialized)
        if isinstance(evidence, dict):
            for key in ("personal", "meta", "schema_version"):
                self.assertNotIn(key, evidence)
        self.assert_unchanged()

    def test_summary_cannot_copy_unsupported_qualifications_or_tools_from_the_jd(self):
        for rewritten in ("Senior Python developer building Django web applications.",
                          "Python developer building Django web applications with PyTorch."):
            with self.subTest(rewritten=rewritten):
                self.propose(rewritten)
                response = self.post(job_description="Deploy Kubernetes clusters and develop with PyTorch.")
                self.assertEqual(response.status_code, 502, response.data)
                self.assertEqual(response.data["error"]["reason"], "factual_validation")
                self.assert_unchanged()

    def test_work_and_project_evidence_stays_with_its_selected_entry(self):
        cases = [("experience", "/experience/0/highlights/0", "Built Django APIs.", "Built and tested Django APIs.", "Tested Django endpoints."),
                 ("projects", "/projects/0/description", "Created a Django application.", "Developed a Django application with REST APIs.", "Built REST APIs.")]
        for section, path, text, rewrite, sibling in cases:
            with self.subTest(section=section):
                self.propose(rewrite)
                response = self.post(section=section, field_path=path, text=text)
                self.assertEqual(response.status_code, 200, response.data)
                evidence = json.dumps(self.provider_payload()["source_evidence"])
                self.assertIn(sibling, evidence)
                for unrelated in ("Cloud Lab", "Docker", "AWS", "Kubernetes"):
                    self.assertNotIn(unrelated, evidence)
                self.assert_unchanged()

    def test_rewrites_cannot_transfer_other_project_deployment_to_a_work_or_project_entry(self):
        cases = [("experience", "/experience/0/highlights/0", "Built Django APIs.", "Built Django APIs and deployed them using Docker and AWS."),
                 ("projects", "/projects/0/description", "Created a Django application.", "Created and deployed a Django application using Docker and AWS.")]
        for section, path, text, rewrite in cases:
            with self.subTest(section=section):
                self.propose(rewrite)
                response = self.post(section=section, field_path=path, text=text)
                self.assertEqual(response.status_code, 502, response.data)
                self.assertEqual(response.data["error"]["reason"], "factual_validation")
                self.assert_unchanged()

    def test_achievement_uses_only_its_selected_text(self):
        self.propose("Completed a project using Django.")
        response = self.post(section="achievements", field_path="/achievements/0", text=self.document["achievements"][0])
        self.assertEqual(response.status_code, 200, response.data)
        evidence = json.dumps(self.provider_payload()["source_evidence"])
        self.assertIn(self.document["achievements"][0], evidence)
        for unrelated in ("Docker", "AWS", "Example Systems", "Cloud Lab"):
            self.assertNotIn(unrelated, evidence)
        self.propose("Completed and deployed a project using Django and AWS.")
        response = self.post(section="achievements", field_path="/achievements/0", text=self.document["achievements"][0],
                             job_description="Deploy Django applications using AWS.")
        self.assertEqual(response.status_code, 502, response.data)
        self.assert_unchanged()

    def test_authentication_ownership_and_missing_cv_reject_before_generation(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post().status_code, 401)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post().status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.post(cv_id=self.cv.pk + 10000).status_code, 404)
        self.factory.assert_not_called()
        self.assert_unchanged()

    def test_stale_version_rejects_before_generation_including_a_cached_proposal(self):
        self.assertEqual(self.post(expected_version=2).status_code, 409)
        self.factory.assert_not_called()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        self.provider.generate_structured.assert_called_once()
        CV.objects.filter(pk=self.cv.pk).update(version=2)
        self.assertEqual(self.post().status_code, 409)
        self.provider.generate_structured.assert_called_once()

    def test_edit_during_generation_rejects_the_result_and_preserves_concurrent_data(self):
        changed = deepcopy(self.document)
        changed["summary"] = "Updated elsewhere."
        def concurrent_save(**kwargs):
            CV.objects.filter(pk=self.cv.pk).update(version=2, data=changed)
            return {"rewritten": "Developed Django web applications using Python.", "changes": []}
        self.provider.generate_structured.side_effect = concurrent_save
        response = self.post()
        self.assertEqual(response.status_code, 409, response.data)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, changed)
        self.assertEqual(self.cv.version, 2)
        self.assertEqual(CVVersion.objects.filter(cv=self.cv).count(), 1)

    def test_context_is_an_all_or_nothing_tuple(self):
        for absent in ("cv_id", "expected_version", "field_path"):
            with self.subTest(absent=absent):
                payload = {key: value for key, value in self.payload.items() if key != absent}
                response = self.client.post("/api/ai/rewrite/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        for overrides in ({"cv_id": 0}, {"expected_version": 0}, {"cv_id": None}, {"field_path": ""}, {"field_path": None}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.post(**overrides).status_code, 400)
        self.factory.assert_not_called()

    def test_invalid_paths_sections_and_changed_source_reject_before_generation(self):
        cases = [{"field_path": "/personal/email"}, {"field_path": "/skills/0"},
                 {"field_path": "/meta/target_role"}, {"field_path": "/education/0/degree"},
                 {"field_path": "/projects/99/description", "section": "projects"},
                 {"field_path": "/projects/0/name", "section": "projects"},
                 {"field_path": "/experience/-1/highlights/0", "section": "experience"},
                 {"field_path": "summary"}, {"section": "projects"}, {"text": "Different saved wording."}]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.post(**overrides).status_code, 400)
        self.factory.assert_not_called()
        self.assert_unchanged()

    def test_source_matching_accepts_only_whitespace_normalization(self):
        response = self.post(text="  Python developer\n building Django web applications. ")
        self.assertEqual(response.status_code, 200, response.data)
        for text in (self.document["summary"].lower(), "Python developer building Django web applications!", "Python developer Django web applications."):
            with self.subTest(text=text):
                self.assertEqual(self.post(text=text).status_code, 400)
        self.provider.generate_structured.assert_called_once()
        self.assert_unchanged()

    def test_original_keeps_saved_whitespace_for_exact_review_and_save_matching(self):
        self.document['summary'] = '  Python developer\n building Django web applications.  '
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=['data'])
        first, cached = self.post(text=self.document['summary']), self.post(text=self.document['summary'])
        for response in (first, cached):
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['data']['original'], self.document['summary'])
        self.assertTrue(cached.data['data']['cached'])
        self.provider.generate_structured.assert_called_once()
        self.assert_unchanged()

    def test_legacy_requests_without_cv_context_keep_their_original_fact_boundary(self):
        legacy = {key: value for key, value in self.payload.items() if key not in ("cv_id", "expected_version", "field_path")}
        for mode in ("rewrite", "improve"):
            with self.subTest(mode=mode):
                response = self.client.post(f"/api/ai/{mode}/", legacy, format="json")
                self.assertEqual(response.status_code, 200, response.data)
        self.propose("Python developer building Django web applications and deploying applications using Docker and AWS.")
        response = self.client.post("/api/ai/rewrite/", {**legacy, "job_description": "Deploy Python applications using Docker and AWS."}, format="json")
        self.assertEqual(response.status_code, 502, response.data)
        self.assert_unchanged()

    def test_cache_is_scoped_by_owner_cv_version_path_mode_and_job_description(self):
        first, repeat = self.post(), self.post()
        self.assertEqual([first.status_code, repeat.status_code], [200, 200])
        self.assertFalse(first.data["data"]["cached"])
        self.assertTrue(repeat.data["data"]["cached"])
        twin = create_cv(user=self.owner, values={"name": "Other synthetic CV", "data": deepcopy(self.document)})
        self.assertFalse(self.post(cv_id=twin.pk).data["data"]["cached"])
        CV.objects.filter(pk=self.cv.pk).update(version=2)
        self.assertFalse(self.post(expected_version=2).data["data"]["cached"])
        self.assertFalse(self.post(expected_version=2, mode="improve").data["data"]["cached"])
        self.assertFalse(self.post(expected_version=2, job_description="Develop Python APIs.").data["data"]["cached"])
        CV.objects.filter(pk=self.cv.pk).update(owner=self.other)
        self.client.force_authenticate(self.other)
        self.assertFalse(self.post(expected_version=2).data["data"]["cached"])
        self.assertEqual(self.provider.generate_structured.call_count, 6)

    def test_saved_summary_cache_cannot_supply_extra_facts_to_a_standalone_rewrite(self):
        self.propose("Python developer building Django web applications and deploying applications using Docker and AWS.")
        grounded = self.post()
        self.assertEqual(grounded.status_code, 200, grounded.data)
        legacy = {key: value for key, value in self.payload.items() if key not in ("cv_id", "expected_version", "field_path")}
        ungrounded = self.client.post("/api/ai/rewrite/", legacy, format="json")
        self.assertEqual(ungrounded.status_code, 502, ungrounded.data)
        self.assertEqual(self.provider.generate_structured.call_count, 2)
        self.assert_unchanged()

    def test_identical_entry_text_in_distinct_paths_does_not_share_a_cached_response(self):
        changed = deepcopy(self.document)
        changed["projects"][1]["description"] = changed["projects"][0]["description"]
        self.cv.data = changed
        self.cv.save(update_fields=["data"])
        self.propose("Developed a Django application.")
        first = self.post(section="projects", field_path="/projects/0/description", text=changed["projects"][0]["description"])
        second = self.post(section="projects", field_path="/projects/1/description", text=changed["projects"][1]["description"])
        self.assertEqual([first.status_code, second.status_code], [200, 200])
        self.assertFalse(first.data["data"]["cached"])
        self.assertFalse(second.data["data"]["cached"])
        self.assertEqual(self.provider.generate_structured.call_count, 2)

    def test_only_explicit_m2_approval_saves_the_selected_summary(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_unchanged()
        approved = deepcopy(self.document)
        approved["summary"] = response.data["data"]["rewritten"]
        saved = self.client.patch(f"/api/cvs/{self.cv.pk}/", {"data": approved, "expected_version": 1}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, approved)
        self.assertEqual(self.cv.version, 2)
        self.assertEqual(CVVersion.objects.filter(cv=self.cv).count(), 2)
