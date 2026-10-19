"""Job relevance must come from the candidate's evidence, without stronger claims."""
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from ai.exceptions import AIStructuredOutputError
from ai.prompts.cv_tasks import JOB_FOCUS_RULES, WRITING_SYSTEM
from ai.services.tailoring import SYSTEM, validate_response, writable_text
from ai.services.writing import improve_text
from cvs.services import create_cv

JD = ('AI Engineer to design, build, and deploy production-grade artificial intelligence and machine learning systems. '
      'You will bridge the gap between experimental data science and scalable software applications, '
      'turning complex business problems into reliable AI-powered features.')
ORIGINAL = ('Software Engineering graduate (2026) and Python Developer Intern experienced in building and testing web '
    'applications with Python, Django, REST APIs, PostgreSQL, and JavaScript. Contributed to recruitment, ATS scoring, '
    'and AI-powered CV workflows; used AI coding assistance while reviewing and testing generated code. Comfortable '
    'with Git, debugging, software development lifecycle (SDLC), and translating feature requirements into working solutions.')
REPORTED = ('Software Engineering graduate (2026) and Python Developer Intern experienced in developing and testing web '
    'applications using Python, Django, REST APIs, PostgreSQL, and JavaScript. Contributed to recruitment systems, ATS '
    'scoring, and AI-supported CV workflows, utilizing AI coding assistance while reviewing and testing generated code. '
    'Proficient in Git, debugging, the software development lifecycle (SDLC), and translating feature requirements into working solutions.')
FOCUSED = ('Software Engineering graduate (2026) and Python Developer Intern with contributions to AI-powered CV '
    'workflows, ATS scoring and recruitment features. Builds and tests web applications with Python, Django, REST APIs, '
    'PostgreSQL and JavaScript, translating feature requirements into working solutions. Reviews and tests AI-assisted '
    'code and is comfortable with Git, debugging and the software development lifecycle (SDLC).')


@override_settings(M6_GEMINI_MODEL='job-focus-test', M6_CACHE_SECONDS=3600)
class JobFocusedWritingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = Mock()
        self.provider.generate_structured.return_value = {
            'rewritten': FOCUSED, 'changes': ['Led with the existing AI workflow and ATS contributions.',
                'Retained the intern identity, technologies and stated proficiency.']}

    def rewrite(self, **kwargs):
        return improve_text(ORIGINAL, user_id=1, section='summary', target_role='AI Engineer',
                            job_description=JD, llm=self.provider, **kwargs)

    def test_reported_source_can_be_reordered_for_ai_role_without_new_claims(self):
        result = self.rewrite()
        self.assertEqual(result['rewritten'], FOCUSED)
        self.assertEqual(result['original'], ORIGINAL)
        self.assertLess(FOCUSED.index('AI-powered'), FOCUSED.index('Python, Django'))
        self.assertIn('Python Developer Intern', result['rewritten'])
        self.assertIn('comfortable with Git', result['rewritten'])
        self.provider.generate_structured.assert_called_once()

    def test_rewrite_and_whole_cv_receive_the_same_role_focus_policy(self):
        self.rewrite()
        request = self.provider.generate_structured.call_args.kwargs
        self.assertIn(JOB_FOCUS_RULES, request['system_prompt'])
        self.assertIn(JOB_FOCUS_RULES, SYSTEM)
        self.assertIn('swapping synonyms alone is not tailoring', WRITING_SYSTEM)
        self.assertIn('AI coding assistance is not evidence of building ML models', WRITING_SYSTEM)
        payload = json.loads(request['user_prompt'].split('\n\n')[-1])
        self.assertEqual(payload['job_description'], JD)
        self.assertEqual(payload['text'], ORIGINAL)
        self.assertEqual(payload['target_role'], 'AI Engineer')

    def test_reported_comfortable_to_proficient_inflation_is_rejected_in_both_modes(self):
        self.provider.generate_structured.return_value['rewritten'] = REPORTED
        for mode in ('rewrite', 'improve'):
            with self.subTest(mode=mode), self.assertRaises(AIStructuredOutputError) as raised:
                self.rewrite(mode=mode)
            self.assertEqual(raised.exception.reason, 'factual_validation')
        self.assertEqual(self.provider.generate_structured.call_count, 2)

    def test_whole_cv_uses_the_same_proficiency_guard(self):
        context = {'summary': ORIGINAL}
        proposal = {'summary': 'Focused wording.', 'suggestions': [], 'changes': [
            {'path': '/summary', 'original': ORIGINAL, 'rewritten': REPORTED, 'reason': 'Focus on AI.'}]}
        with self.assertRaises(AIStructuredOutputError):
            validate_response(proposal, writable_text(context), context, [])
        proposal['changes'][0]['rewritten'] = FOCUSED
        self.assertEqual(validate_response(proposal, writable_text(context), context, [])['changes'][0]['rewritten'], FOCUSED)

    def test_jd_cannot_supply_production_training_deployment_or_new_tools(self):
        for addition in (' Deployed AI applications.', ' Delivered production-grade AI features.',
                         ' Trained AI models.', ' Implemented MLOps.', ' Used AWS and PyTorch.'):
            self.provider.generate_structured.return_value['rewritten'] = FOCUSED + addition
            with self.subTest(addition=addition), self.assertRaises(AIStructuredOutputError):
                self.rewrite()

    def test_confirmed_proficiency_can_be_rephrased(self):
        self.provider.generate_structured.return_value['rewritten'] = 'Proficient with Git and Django.'
        response = improve_text('Skilled with Git and Django.', user_id=1, section='summary', llm=self.provider)
        self.assertEqual(response['rewritten'], 'Proficient with Git and Django.')

    def test_selected_rewrites_preserve_source_year_and_quantities(self):
        self.provider.generate_structured.return_value['rewritten'] = FOCUSED.replace('(2026) ', '')
        with self.assertRaises(AIStructuredOutputError):
            self.rewrite()

    def test_valid_reviews_cache_once_per_context_and_invalid_reviews_do_not_cache(self):
        self.provider.generate_structured.return_value['rewritten'] = REPORTED
        with self.assertRaises(AIStructuredOutputError): self.rewrite()
        self.provider.generate_structured.return_value['rewritten'] = FOCUSED
        self.assertFalse(self.rewrite()['cached'])
        self.assertTrue(self.rewrite()['cached'])
        self.assertEqual(self.provider.generate_structured.call_count, 2)

    def test_cached_selected_rewrites_are_revalidated(self):
        with patch('ai.services.writing.cached_ai_result', return_value=({'rewritten': REPORTED, 'changes': []}, True)):
            with self.assertRaises(AIStructuredOutputError): self.rewrite()
        self.provider.generate_structured.assert_not_called()

    def test_contact_and_large_number_formatting_changes_are_checked_separately(self):
        for original, rewritten in [
            ('Built 1000000 Django records.', 'Built 1,000,000 Django records.'),
            ('Developed Django APIs. Contact candidate@example.com.', 'Developed APIs with Django. Contact candidate@example.com.'),
        ]:
            self.provider.generate_structured.return_value['rewritten'] = rewritten
            with self.subTest(original=original):
                self.assertEqual(improve_text(original, user_id=1, section='summary', llm=self.provider)['rewritten'], rewritten)


class JobFocusedWritingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('job-focus@example.com')

    def setUp(self):
        cache.clear(); self.client.force_authenticate(self.user)

    @patch('ai.services.writing.get_llm_provider')
    def test_selected_review_uses_jd_but_does_not_change_the_saved_cv(self, factory):
        cv = create_cv(user=self.user, values={'name': 'AI applications CV', 'data': {}})
        cv.data['summary'] = ORIGINAL; cv.save(update_fields=['data'])
        factory.return_value.generate_structured.return_value = {'rewritten': FOCUSED, 'changes': ['Moved supported AI contributions first.']}
        payload = {'text': ORIGINAL, 'section': 'summary', 'target_role': 'AI Engineer', 'job_description': JD}
        for route in ('rewrite', 'improve'):
            response = self.client.post(f'/api/ai/{route}/', payload, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['data']['original'], ORIGINAL)
            self.assertEqual(response.data['data']['rewritten'], FOCUSED)
        cv.refresh_from_db(); self.assertEqual(cv.data['summary'], ORIGINAL); self.assertEqual(cv.version, 1)
