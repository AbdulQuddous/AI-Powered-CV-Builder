from copy import deepcopy
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from cvs.models import CV
from cvs.services import create_cv
from templates_app.models import CVTemplate


class M9AIIntegrationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('review@example.com', 'Strong-password-123!')
        self.other = get_user_model().objects.create_user('private@example.com', 'Strong-password-123!')
        self.client.force_authenticate(self.user)
        self.cv = create_cv(user=self.user, values={'name': 'Backend CV', 'target_role': 'Backend Developer', 'template_id': 'modern', 'data': {}})
        self.document = deepcopy(self.cv.data)
        self.document['personal']['full_name'] = 'Ali Khan'
        self.document['summary'] = 'I developed Django APIs.'
        self.document['projects'] = [{'name': 'CV Maker', 'description': 'Created a CV maker', 'technologies': ['Django'], 'url': '', 'highlights': []}]
        self.cv.data = self.document
        self.cv.save(update_fields=['data'])
        CVTemplate.objects.update_or_create(id='modern', defaults={'name': 'Modern', 'category': 'professional', 'template_path': 'cv_templates/modern.html', 'is_available': True})

    @patch('ai.services.analysis.get_llm_provider')
    def test_selection_and_health_check_do_not_use_gemini(self, provider):
        self.assertEqual(self.client.get('/dashboard/').status_code, 200)
        saved = self.client.get(f'/api/cvs/{self.cv.id}/').data
        response = self.client.post('/api/ai/validate/', {'cv': saved['data'], 'target_role': saved['target_role'], 'use_ai': False}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['data']['valid'])
        self.assertTrue(response.data['data']['warnings'])
        provider.assert_not_called()

    @patch('ai.services.analysis.get_llm_provider')
    def test_combined_analysis_reuses_backend_cache_and_does_not_save(self, provider):
        llm = Mock()
        llm.generate_structured.return_value = {'suggestions': [{'section': 'summary', 'priority': 'medium', 'message': 'Clarify summary', 'recommended_action': 'Describe supported work'}], 'strengths': ['Django'], 'gaps': ['Missing phone'], 'match_score': 65}
        provider.return_value = llm
        payload = {'cv': self.document, 'target_role': 'Backend Developer', 'use_ai': True}
        first = self.client.post('/api/ai/optimize/', payload, format='json')
        second = self.client.post('/api/ai/suggestions/', payload, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertTrue(second.data['data']['cached'])
        self.assertEqual(llm.generate_structured.call_count, 1)
        self.assertEqual(first.data['data']['match_score'], 65)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)
        self.assertEqual(self.cv.version, 1)

    @patch('ai.services.writing.get_llm_provider')
    def test_approved_rewrite_reaches_editor_and_renderer_without_losing_projects(self, provider):
        llm = Mock()
        llm.generate_structured.return_value = {'rewritten': 'Developed Django APIs.', 'changes': ['Improved wording']}
        provider.return_value = llm
        response = self.client.post('/api/ai/rewrite/', {'text': self.document['summary'], 'section': 'summary', 'target_role': 'Backend Developer'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data['summary'], self.document['summary'])
        approved = deepcopy(self.document)
        approved['summary'] = response.data['data']['rewritten']
        saved = self.client.patch(f'/api/cvs/{self.cv.id}/', {'data': approved, 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['data']['projects'], self.document['projects'])
        self.assertEqual(saved.data['version'], 2)
        stale = self.client.patch(f'/api/cvs/{self.cv.id}/', {'data': self.document, 'expected_version': 1}, format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.get(f'/cvs/{self.cv.id}/edit/').status_code, 200)
        preview = self.client.get(f'/api/cvs/{self.cv.id}/preview/')
        self.assertContains(preview, 'Developed Django APIs.')
        self.assertContains(preview, 'CV Maker')
        with patch('m8_renderer.views.PDFExporter.generate', return_value=b'%PDF-test') as pdf:
            export = self.client.post(f'/api/cvs/{self.cv.id}/export/pdf/')
            self.assertEqual(export.status_code, 200)
            self.assertEqual(pdf.call_args.args[0]['cv_data']['summary'], 'Developed Django APIs.')

    @patch('ai.services.extraction.get_llm_provider')
    def test_import_ai_proposal_only_creates_cv_after_m2_confirmation(self, provider):
        llm = Mock()
        llm.generate_structured.return_value = deepcopy(self.document)
        provider.return_value = llm
        before = CV.objects.count()
        extracted = self.client.post('/api/ai/extract/', {'raw_text': 'Ali Khan\nBackend Developer\nDeveloped Django APIs.'}, format='json')
        self.assertEqual(extracted.status_code, 200, extracted.data)
        self.assertEqual(CV.objects.count(), before)
        saved = self.client.post('/api/cvs/', {'name': 'Imported CV', 'data': extracted.data['data']['cv']}, format='json')
        self.assertEqual(saved.status_code, 201, saved.data)
        self.assertEqual(CV.objects.count(), before + 1)
        self.assertNotEqual(saved.data['id'], self.cv.id)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)

    def test_ownership_is_enforced_on_the_source_cv_and_approved_save(self):
        private = create_cv(user=self.other, values={'name': 'Private CV', 'data': {}})
        self.assertEqual(self.client.get(f'/api/cvs/{private.id}/').status_code, 404)
        saved = self.client.patch(f'/api/cvs/{private.id}/', {'data': self.document, 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 404)
        private.refresh_from_db()
        self.assertEqual(private.version, 1)

    @patch('ai.services.tailoring.get_llm_provider')
    def test_whole_cv_proposal_requires_one_approved_versioned_save(self, provider):
        llm = Mock()
        changes = [
            {'path': '/summary', 'original': self.document['summary'], 'rewritten': 'Developed Django APIs.', 'reason': 'Use direct wording.'},
            {'path': '/projects/0/description', 'original': self.document['projects'][0]['description'], 'rewritten': 'Developed a CV maker.', 'reason': 'Use a clear action verb.'},
        ]
        llm.generate_structured.return_value = {
            'summary': 'Clarified the professional summary and project description.',
            'changes': changes,
            'suggestions': ['Only include skills supported by your experience.'],
        }
        provider.return_value = llm
        snapshot_count = self.cv.versions.count()
        response = self.client.post('/api/ai/tailor/', {
            'cv_id': self.cv.id, 'expected_version': 1, 'target_role': 'Backend Developer',
            'job_description': 'Develop and maintain Django APIs.',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['cv_id'], self.cv.id)
        self.assertEqual(response.data['data']['version'], 1)
        self.assertEqual(response.data['data']['changes'], changes)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)
        self.assertEqual(self.cv.version, 1)
        self.assertEqual(self.cv.versions.count(), snapshot_count)

        approved = deepcopy(self.document)
        approved['summary'] = changes[0]['rewritten']
        approved['projects'][0]['description'] = changes[1]['rewritten']
        saved = self.client.patch(f'/api/cvs/{self.cv.id}/', {
            'data': approved, 'expected_version': response.data['data']['version'],
        }, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['data'], approved)
        self.assertEqual(saved.data['version'], 2)
        self.assertEqual(self.cv.versions.count(), snapshot_count + 1)
        self.assertEqual(saved.data['data']['personal'], self.document['personal'])
        self.assertEqual(saved.data['data']['education'], self.document['education'])
        self.assertEqual(saved.data['data']['projects'][0]['technologies'], self.document['projects'][0]['technologies'])
        preview = self.client.get(f'/api/cvs/{self.cv.id}/preview/')
        self.assertContains(preview, changes[0]['rewritten'])
        self.assertContains(preview, changes[1]['rewritten'])
        with patch('m8_renderer.views.PDFExporter.generate', return_value=b'%PDF-test') as pdf:
            export = self.client.post(f'/api/cvs/{self.cv.id}/export/pdf/')
            self.assertEqual(export.status_code, 200)
            self.assertEqual(pdf.call_args.args[0]['cv_data'], approved)

    @patch('ai.services.tailoring.get_llm_provider')
    def test_whole_cv_generation_rejects_foreign_or_stale_sources_before_ai(self, provider):
        private = create_cv(user=self.other, values={'name': 'Private CV', 'data': {}})
        payload = {'cv_id': private.id, 'expected_version': 1, 'job_description': 'Maintain Django APIs.'}
        response = self.client.post('/api/ai/tailor/', payload, format='json')
        self.assertEqual(response.status_code, 404, response.data)
        payload['cv_id'] = self.cv.id
        payload['expected_version'] = 99
        response = self.client.post('/api/ai/tailor/', payload, format='json')
        self.assertEqual(response.status_code, 409, response.data)
        provider.assert_not_called()
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)
        self.assertEqual(self.cv.version, 1)
