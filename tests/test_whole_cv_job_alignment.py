"""Whole-CV JD tailoring keeps requirement/evidence matching separate from facts."""
from copy import deepcopy
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from ai.exceptions import AIStructuredOutputError
from ai.services.job_alignment import evidence_sources, validate_alignment
from ai.services.job_alignment import ALIGNMENT_WARNING, job_requirements, reference_alignment_schema, resolve_alignment
from ai.services.job_alignment import select_verified_notes
from pathlib import Path
from ai.services.tailoring import SYSTEM
from ai.schemas.contracts import gemini_compatible_schema
from ai.services.tailoring import response_schema, validate_response, writable_text
from cvs.services import create_cv
from tests.test_job_focused_writing import ORIGINAL, FOCUSED, JD
from tests.test_m8 import SAMPLE_CV


class AlignmentEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.context = {'meta': {'target_role': 'AI Engineer'}, 'personal': {'email': 'private@example.com'},
                        'summary': ORIGINAL, 'skills': ['Python'],
                        'projects': [{'description': 'Built Django APIs.'}]}
        self.sources = evidence_sources(self.context)
        self.job = 'Build Django APIs and deploy with Kubernetes.'
        self.alignment = [
            {'requirement': 'Build Django APIs', 'status': 'supported',
             'evidence': [{'path': '/projects/0/description', 'quote': 'Built Django APIs.'}]},
            {'requirement': 'deploy with Kubernetes', 'status': 'missing', 'evidence': []}]

    def test_metadata_and_contacts_are_not_evidence_paths(self):
        self.assertEqual(set(self.sources), {'/summary', '/skills/0', '/projects/0/description'})
        self.assertEqual(validate_alignment(self.alignment, self.job, self.sources), self.alignment)

    def test_related_evidence_is_allowed_with_an_explicit_partial_status(self):
        self.alignment[0]['status'] = 'partial'
        self.assertEqual(validate_alignment(self.alignment, self.job, self.sources), self.alignment)

    def test_fabricated_job_requirements_or_cv_excerpts_cannot_be_displayed_as_matches(self):
        for mutation in ('requirement', 'quote', 'path', 'blank_quote', 'blank_requirement'):
            alignment = deepcopy(self.alignment)
            if mutation == 'requirement': alignment[0]['requirement'] = 'Train large language models'
            if mutation == 'quote': alignment[0]['evidence'][0]['quote'] = 'Deployed production AI systems.'
            if mutation == 'path': alignment[0]['evidence'][0]['path'] = '/meta/target_role'
            if mutation == 'blank_quote': alignment[0]['evidence'][0]['quote'] = '  '
            if mutation == 'blank_requirement': alignment[0]['requirement'] = '  '
            with self.subTest(mutation=mutation), self.assertRaises(AIStructuredOutputError):
                validate_alignment(alignment, self.job, self.sources)

    def test_empty_supported_claims_missing_claims_with_evidence_duplicates_and_invalid_shapes_fail(self):
        cases = [[], None, [*self.alignment, self.alignment[0]],
                 [{**self.alignment[0], 'evidence': []}],
                 [{**self.alignment[0], 'status': 'missing'}],
                 [{**self.alignment[0], 'score': 100}]]
        for alignment in cases:
            with self.subTest(alignment=alignment), self.assertRaises(AIStructuredOutputError):
                validate_alignment(alignment, self.job, self.sources)

    def test_compact_provider_schema_keeps_structure_paths_and_limit_guidance_without_nested_bounds(self):
        schema = response_schema({'/summary': ORIGINAL}, alignment_paths=self.sources, include_alignment=True)
        original = deepcopy(schema)
        compact = gemini_compatible_schema(schema, compact=True)
        def check(node):
            if isinstance(node, dict):
                for bound in ('minLength', 'maxLength', 'minItems', 'maxItems'):
                    self.assertNotIn(bound, node)
                for child in node.values(): check(child)
            elif isinstance(node, list):
                for child in node: check(child)
        check(compact)
        self.assertEqual(schema, original)
        self.assertEqual(compact['required'], schema['required'])
        self.assertFalse(compact['additionalProperties'])
        self.assertIn('Maximum items: 6.', compact['properties']['job_alignment']['description'])
        self.assertEqual(compact['properties']['changes']['items']['properties']['path']['enum'], ['/summary'])
        self.assertEqual(compact['properties']['job_alignment']['items']['properties']['evidence']['items']['properties']['path']['enum'], list(self.sources))
        # Existing extraction callers retain their existing compatibility mode.
        self.assertEqual(gemini_compatible_schema(schema)['properties']['job_alignment']['maxItems'], 6)

    def test_original_server_limits_still_reject_excessive_requirements_evidence_and_text(self):
        for alignment in ([*self.alignment] * 4,
                          [{**self.alignment[0], 'evidence': self.alignment[0]['evidence'] * 4}],
                          [{**self.alignment[0], 'requirement': 'a' * 501}]):
            with self.subTest(alignment=alignment), self.assertRaises(AIStructuredOutputError):
                validate_alignment(alignment, self.job, self.sources)
        proposal = {'summary': 'Checked', 'changes': [{'path': '/summary', 'original': ORIGINAL,
                     'rewritten': 'a' * 5001, 'reason': 'Clearer wording.'}], 'suggestions': []}
        with self.assertRaises(AIStructuredOutputError):
            validate_response(proposal, writable_text(self.context), self.context, [])

    def test_reported_long_jd_uses_known_ids_and_server_supplied_text(self):
        job = (Path(__file__).parent / 'fixtures/full_stack_ai_job.txt').read_text()
        requirements = job_requirements(job)
        self.assertGreater(len(requirements), 10)
        self.assertLessEqual(len(requirements), 32)
        for text in requirements.values():
            self.assertIn(text, job)
            self.assertLessEqual(len(text), 500)
        reference = next(key for key, text in requirements.items() if 'Full-Stack Development:' in text)
        wire = [{'requirement_id': reference, 'status': 'partial', 'evidence_paths': ['/projects/0/description']}]
        resolved = resolve_alignment(wire, requirements, self.sources)
        self.assertEqual(resolved[0]['requirement'], requirements[reference])
        self.assertEqual(resolved[0]['evidence'], [{'path': '/projects/0/description', 'quote': 'Built Django APIs.'}])
        self.assertEqual(validate_alignment(resolved, job, self.sources), resolved)
        schema = reference_alignment_schema(requirements, self.sources)
        self.assertEqual(schema['items']['properties']['requirement_id']['enum'], list(requirements))
        self.assertNotIn('quote', schema['items']['properties'])

    def test_unknown_reference_ids_or_source_paths_never_become_displayed_evidence(self):
        for wire in ([{'requirement_id': 'unknown', 'status': 'supported', 'evidence_paths': ['/summary']}],
                     [{'requirement_id': 'jd-1', 'status': 'supported', 'evidence_paths': ['/meta/target_role']}],
                     [{'requirement_id': 'jd-1', 'status': 'supported', 'evidence_paths': None}]):
            resolved = resolve_alignment(wire, {'jd-1': 'Build Django APIs'}, self.sources)
            with self.subTest(wire=wire), self.assertRaises(AIStructuredOutputError):
                validate_alignment(resolved, self.job, self.sources)

    def test_one_invalid_note_does_not_discard_an_independently_verified_note(self):
        notes = [*self.alignment, {}]
        checked, errors = select_verified_notes(notes, self.job, self.sources)
        self.assertEqual(checked, self.alignment)
        self.assertEqual(errors, {'schema_invalid': 1})

    def test_extra_and_duplicate_notes_and_citations_are_bounded_without_losing_valid_notes(self):
        sources = {f'/skills/{i}': f'Tool {i}' for i in range(4)}
        job = '; '.join(f'Requirement {i}' for i in range(8))
        notes = [{'requirement': f'Requirement {i}', 'status': 'partial',
                  'evidence': [{'path': path, 'quote': quote} for path, quote in sources.items()]}
                 for i in range(8)]
        before = deepcopy(notes)
        checked, errors = select_verified_notes([notes[0], *notes], job, sources)
        self.assertEqual(len(checked), 6)
        self.assertTrue(all(len(note['evidence']) == 3 for note in checked))
        self.assertEqual(len({note['requirement'] for note in checked}), 6)
        self.assertFalse(errors)
        self.assertEqual(notes, before)
        validate_alignment(checked, job, sources)


@override_settings(M6_GEMINI_MODEL='whole-cv-jd-test', M6_CACHE_SECONDS=3600)
class WholeCVJobAlignmentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('whole-cv-jd@example.com')

    def setUp(self):
        cache.clear(); self.client.force_authenticate(self.user)
        self.data = deepcopy(SAMPLE_CV)
        self.data['meta']['target_role'] = 'Python Developer'
        self.data['summary'] = ORIGINAL
        self.data['experience'] = [{'company': 'Example Systems', 'job_title': 'Developer Intern',
            'location': '', 'start_date': '', 'end_date': '', 'is_current': True,
            'highlights': ['Contributed to AI-powered CV workflows and ATS scoring with Django.']}]
        self.data['projects'][0]['description'] = 'Built an AI-powered CV application using Django.'
        self.data['achievements'] = ['Completed a Django project.']
        self.cv = create_cv(user=self.user, values={'name': 'Job-focused CV', 'data': self.data})
        self.payload = {'cv_id': self.cv.pk, 'expected_version': 1, 'target_role': 'AI Engineer', 'job_description': JD}
        self.result = {
            'job_alignment': [
                {'requirement': 'AI-powered features', 'status': 'partial',
                 'evidence': [{'path': '/experience/0/highlights/0', 'quote': self.data['experience'][0]['highlights'][0]}]},
                {'requirement': 'deploy production-grade', 'status': 'missing', 'evidence': []}],
            'summary': 'Prioritized existing AI application contributions for this job.',
            'changes': [self.change('/summary', FOCUSED)],
            'suggestions': ['If available, add a confirmed example of deploying an AI application.']}
        self.provider = Mock()
        self.provider.generate_structured.return_value = deepcopy(self.result)
        provider_patch = patch('ai.services.tailoring.get_llm_provider', return_value=self.provider)
        provider_patch.start(); self.addCleanup(provider_patch.stop)

    def change(self, path, rewritten):
        original = self.data
        for part in path.strip('/').split('/'):
            original = original[int(part)] if isinstance(original, list) else original[part]
        return {'path': path, 'original': original, 'rewritten': rewritten,
                'reason': 'Prioritizes confirmed AI-powered application work for the job requirements.'}

    def post(self, **overrides):
        return self.client.post('/api/ai/tailor/', {**self.payload, **overrides}, format='json')

    def test_one_gemini_request_reviews_all_sections_with_jd_evidence_and_entry_scope(self):
        self.provider.generate_structured.return_value['changes'] += [
            self.change('/experience/0/highlights/0', 'Contributed to ATS scoring and AI-powered CV workflows with Django.'),
            self.change('/projects/0/description', 'Built an AI-powered CV application with Django.'),
            self.change('/achievements/0', 'Completed a project using Django.')]
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data['data']
        self.assertEqual(result['job_alignment'], self.result['job_alignment'])
        self.assertEqual(len(result['changes']), 4)
        self.provider.generate_structured.assert_called_once()
        request = self.provider.generate_structured.call_args.kwargs
        prompt = json.loads(request['user_prompt'])
        self.assertEqual(prompt['target_role'], 'AI Engineer')
        self.assertEqual(prompt['job_description'], JD)
        self.assertEqual(prompt['cv']['meta']['target_role'], 'Python Developer')
        self.assertEqual(set(prompt['review_sections']), {'summary', 'experience', 'projects', 'achievements'})
        self.assertIn('/education/0/degree', prompt['evidence_sources'])
        self.assertNotIn('/meta/target_role', prompt['evidence_sources'])
        self.assertNotIn('/personal/full_name', prompt['evidence_sources'])
        constraints = prompt['field_constraints']['/experience/0/highlights/0']
        self.assertIn('/experience/0/highlights/0', constraints['allowed_evidence_paths'])
        self.assertNotIn('/projects/0/description', constraints['allowed_evidence_paths'])
        self.assertIn('job_alignment', request['schema']['required'])
        self.assertNotIn('maxItems', request['schema']['properties']['job_alignment'])
        self.assertEqual(list(request['schema']['properties'])[0], 'job_alignment')
        self.assertIn('primary focus', SYSTEM)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.data)
        self.assertEqual(self.cv.version, 1)
        self.assertEqual(self.cv.versions.count(), 1)

    def test_changing_jd_changes_review_context_and_suggestions_instead_of_reusing_old_review(self):
        self.assertEqual(self.post().status_code, 200)
        second_job = 'Build Django web applications and REST APIs.'
        second_wording = ORIGINAL.replace('experienced in building and testing', 'building and testing')
        self.provider.generate_structured.return_value = {
            'job_alignment': [{'requirement': 'Django web applications', 'status': 'supported',
                               'evidence': [{'path': '/summary', 'quote': 'building and testing web applications with Python, Django'}]}],
            'summary': 'Prioritized Django application delivery.',
            'changes': [self.change('/summary', second_wording)], 'suggestions': []}
        second = self.post(job_description=second_job)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['data']['changes'][0]['rewritten'], second_wording)
        self.assertNotEqual(second.data['data']['changes'][0]['rewritten'], FOCUSED)
        self.assertEqual(second.data['data']['job_alignment'][0]['requirement'], 'Django web applications')
        self.assertEqual(self.provider.generate_structured.call_count, 2)
        cached = self.post(job_description=second_job)
        self.assertTrue(cached.data['data']['cached'])
        self.assertEqual(self.provider.generate_structured.call_count, 2)

    def test_unverified_job_fit_notes_do_not_discard_verified_wording_and_are_not_cached_as_evidence(self):
        self.provider.generate_structured.return_value['job_alignment'][0]['evidence'][0]['quote'] = 'Deployed production ML models.'
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['changes'], self.result['changes'])
        self.assertEqual(response.data['data']['job_alignment'], [self.result['job_alignment'][1]])
        self.assertEqual(response.data['data']['job_alignment_warning'], ALIGNMENT_WARNING)
        self.provider.generate_structured.return_value = deepcopy(self.result)
        cached = self.post()
        self.assertEqual(cached.status_code, 200)
        self.assertTrue(cached.data['data']['cached'])
        self.assertEqual(cached.data['data']['job_alignment'], [self.result['job_alignment'][1]])
        self.assertEqual(self.provider.generate_structured.call_count, 1)

    def test_cached_alignment_is_checked_again_against_current_job_and_cv(self):
        corrupt = deepcopy(self.result)
        corrupt['job_alignment'][0]['requirement'] = 'An unrelated job requirement'
        with patch('ai.services.tailoring.cached_ai_result', return_value=(corrupt, True)):
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['data']['job_alignment'], [self.result['job_alignment'][1]])
            self.assertEqual(response.data['data']['job_alignment_warning'], ALIGNMENT_WARNING)
        self.provider.generate_structured.assert_not_called()

    def test_reported_jd_paraphrase_cannot_block_independently_validated_cv_improvements(self):
        job = (Path(__file__).parent / 'fixtures/full_stack_ai_job.txt').read_text()
        self.provider.generate_structured.return_value['job_alignment'] = [{
            'requirement': 'Develop full-stack applications using Django and React', 'status': 'partial',
            'evidence': [{'path': '/summary', 'quote': 'Python, Django'}]}]
        response = self.post(job_description=job, target_role='Full Stack AI Developer')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['changes'], self.result['changes'])
        self.assertNotIn('job_alignment', response.data['data'])
        self.assertIn('job_alignment_warning', response.data['data'])
        self.cv.refresh_from_db(); self.assertEqual(self.cv.data, self.data)

    def test_reference_response_resolves_to_public_evidence_without_schema_contract_changes(self):
        requirements = job_requirements(JD)
        reference = next(key for key, text in requirements.items() if 'AI-powered features' in text)
        self.provider.generate_structured.return_value['job_alignment'] = [{
            'requirement_id': reference, 'status': 'partial', 'evidence_paths': ['/experience/0/highlights/0']}]
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        note = response.data['data']['job_alignment'][0]
        self.assertEqual(note['requirement'], requirements[reference])
        self.assertEqual(note['evidence'][0]['quote'], self.data['experience'][0]['highlights'][0])
        request = self.provider.generate_structured.call_args.kwargs
        self.assertEqual(json.loads(request['user_prompt'])['job_requirements'], requirements)
        self.assertIn('requirement_id', request['schema']['properties']['job_alignment']['items']['required'])

    def test_missing_job_fit_notes_never_make_stale_source_or_unsupported_claims_acceptable(self):
        self.provider.generate_structured.return_value['job_alignment'][0]['requirement'] = 'Paraphrased requirement'
        for change in ({**self.result['changes'][0], 'original': 'Different saved wording'},
                       {**self.result['changes'][0], 'rewritten': FOCUSED + ' Deployed production-grade ML systems.'}):
            self.provider.generate_structured.return_value['changes'] = [change]
            with self.subTest(change=change):
                self.assertEqual(self.post().status_code, 502)

    def test_provider_cannot_forge_job_fit_omission_warning(self):
        self.provider.generate_structured.return_value['job_alignment_warning'] = ALIGNMENT_WARNING
        self.assertEqual(self.post().status_code, 502)

    def test_legacy_role_only_api_is_compatible_and_does_not_request_a_fabricated_jd_review(self):
        self.provider.generate_structured.return_value.pop('job_alignment')
        response = self.post(job_description='')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('job_alignment', self.provider.generate_structured.call_args.kwargs['schema']['properties'])

    def test_alignment_is_advice_only_and_approval_saves_only_selected_wording(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        data = deepcopy(self.data)
        data['summary'] = response.data['data']['changes'][0]['rewritten']
        saved = self.client.patch(f'/api/cvs/{self.cv.pk}/', {'data': data, 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, data)
        self.assertNotIn('job_alignment', self.cv.data)
        self.assertNotIn('production-grade', self.cv.data['summary'])
        self.assertEqual(self.cv.version, 2)
