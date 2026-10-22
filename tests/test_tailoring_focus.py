"""Editing hints follow the supplied JD and bounded literal CV evidence."""
from copy import deepcopy

from django.test import SimpleTestCase

from ai.services.job_alignment import job_requirements
from ai.services.tailoring_focus import tailoring_brief


class TailoringFocusTests(SimpleTestCase):
    def setUp(self):
        self.sources = {
            '/projects/0/description': 'Integrated Gemini AI chatbot workflows with LLM prompts and response guardrails.',
            '/experience/0/highlights/0': 'Built Django REST APIs with PostgreSQL.',
            '/experience/0/highlights/1': 'Tested REST APIs with Postman and debugged Django endpoints.',
            '/projects/1/description': 'Created responsive React interfaces using JavaScript.',
        }

    def brief(self, jd='', role='', section='summary', sources=None):
        return tailoring_brief(section, role, job_requirements(jd), self.sources if sources is None else sources)

    def test_ai_and_backend_testing_jobs_prioritize_different_confirmed_contributions(self):
        ai = self.brief('Integrate AI chatbot workflows with LLM prompts and output guardrails.', 'AI Developer')
        backend = self.brief('Build Django REST APIs with PostgreSQL and test endpoints using Postman.', 'Backend Developer')
        self.assertEqual(ai['job_priorities'][0]['evidence_paths'][0], '/projects/0/description')
        self.assertEqual(backend['job_priorities'][0]['evidence_paths'][0], '/experience/0/highlights/1')
        self.assertNotEqual(ai['job_priorities'], backend['job_priorities'])

    def test_jd_guides_a_review_even_without_a_target_role(self):
        result = self.brief('Create responsive React interfaces with JavaScript.')
        self.assertEqual(result['job_priorities'][0]['evidence_paths'][0], '/projects/1/description')
        self.assertEqual(result['role_evidence_paths'], [])

    def test_entry_scoped_sources_cannot_produce_other_entries_as_evidence(self):
        bounded = {path: text for path, text in self.sources.items() if path.startswith('/experience/0/')}
        result = self.brief(
            'Integrate AI chatbot workflows and implement Django REST APIs with PostgreSQL.',
            'Gemini AI Developer', section='experience', sources=bounded,
        )
        referenced = [path for item in result['job_priorities'] for path in item['evidence_paths']]
        referenced.extend(result['role_evidence_paths'])
        self.assertTrue(referenced)
        self.assertLessEqual(set(referenced), set(bounded))
        self.assertNotIn('/projects/0/description', referenced)

    def test_missing_requirement_does_not_become_candidate_evidence(self):
        result = self.brief('Manage offshore seismic hydrographic surveys.', 'Marine Surveyor')
        self.assertEqual(result['job_priorities'], [])
        self.assertEqual(result['role_evidence_paths'], [])
        self.assertIn('missing requirements are gaps', result['evidence_note'])

    def test_shared_terms_are_relevance_hints_without_automatic_qualification(self):
        sources = {'/skills/0': 'Django', '/skills/1': 'Python'}
        result = self.brief('Lead production Django services and train Python AI models.', sources=sources)
        self.assertTrue(result['job_priorities'])
        self.assertIn('not proof of qualification', result['evidence_note'])
        for item in result['job_priorities']:
            self.assertNotIn('status', item)
            self.assertNotIn('qualified', item)
            self.assertNotIn('score', item)
            self.assertLessEqual(set(item['evidence_paths']), set(sources))
            self.assertNotIn('production', item['shared_terms'])
            self.assertNotIn('train', item['shared_terms'])
            self.assertNotIn('lead', item['shared_terms'])

    def test_priorities_keep_literal_requirement_identifiers_and_source_paths(self):
        jd = 'Use Django REST APIs.\nCreate React interfaces with JavaScript.\nIntegrate Gemini AI workflows.'
        requirements = job_requirements(jd)
        before_requirements, before_sources = deepcopy(requirements), deepcopy(self.sources)
        result = tailoring_brief('summary', 'AI Developer', requirements, self.sources)
        self.assertTrue(result['job_priorities'])
        for item in result['job_priorities']:
            self.assertIn(item['requirement_id'], requirements)
            self.assertLessEqual(set(item['evidence_paths']), set(self.sources))
            self.assertNotIn('requirement', item)
            self.assertNotIn('rewritten', item)
        self.assertEqual(requirements, before_requirements)
        self.assertEqual(self.sources, before_sources)

    def test_role_only_review_uses_matching_saved_evidence_without_fabricating_requirements(self):
        result = self.brief(role='React JavaScript Developer', section='projects')
        self.assertEqual(result['job_priorities'], [])
        self.assertEqual(result['role_evidence_paths'][0], '/projects/1/description')
        self.assertIn('Project experience remains project experience', result['section_purpose'])

    def test_empty_context_still_requests_useful_factual_editing(self):
        result = self.brief(sources={})
        self.assertEqual(result['job_priorities'], [])
        self.assertEqual(result['role_evidence_paths'], [])
        self.assertIn('career identity and proficiency', result['section_purpose'])
        self.assertIn('synonym substitutions', result['editing_goal'])
        self.assertIn('not proof of qualification', result['evidence_note'])

    def test_contribution_hints_prefer_actual_work_over_skills_and_job_titles(self):
        sources = {
            '/skills/0': 'Django REST APIs Postman PostgreSQL',
            '/experience/0/job_title': 'Django REST API Developer',
            '/experience/0/highlights/0': 'Built Django REST APIs with PostgreSQL.',
            '/projects/0/description': 'Tested Django REST APIs using Postman.',
            '/projects/1/description': 'Created responsive React interfaces.',
        }
        result = self.brief('Build and test Django REST APIs with PostgreSQL and Postman.', sources=sources)
        self.assertEqual(set(result['contribution_evidence_paths']), {
            '/experience/0/highlights/0', '/projects/0/description',
        })
        self.assertNotIn('/skills/0', result['contribution_evidence_paths'])
        self.assertNotIn('/experience/0/job_title', result['contribution_evidence_paths'])

    def test_summary_additional_hints_find_new_confirmed_contributions(self):
        sources = {
            '/summary': 'Django developer with REST APIs.',
            '/experience/0/highlights/0': 'Django developer with REST APIs.',
            '/projects/0/description': 'Integrated Gemini AI chatbot workflows.',
            '/skills/0': 'Gemini AI chatbot workflows',
        }
        requirements = job_requirements('Build Django REST APIs and integrate Gemini AI chatbot workflows.')
        result = tailoring_brief('summary', 'AI Developer', requirements, sources, selected_path='/summary')
        self.assertEqual(result['additional_evidence_to_consider'], ['/projects/0/description'])
        self.assertNotIn('/summary', result['additional_evidence_to_consider'])
        self.assertNotIn('/experience/0/highlights/0', result['additional_evidence_to_consider'])
        self.assertIn('not proof of qualification', result['evidence_note'])

    def test_entry_additional_hints_exclude_selected_bullet_and_other_entries(self):
        sources = {
            '/experience/0/job_title': 'Django Developer',
            '/experience/0/highlights/0': 'Built Django REST APIs.',
            '/experience/0/highlights/1': 'Tested Django REST APIs with Postman.',
        }
        result = tailoring_brief(
            'experience', 'Django API Developer',
            job_requirements('Build and test Django REST APIs using Postman and Gemini AI.'),
            sources, selected_path='/experience/0/highlights/0',
        )
        self.assertEqual(result['additional_evidence_to_consider'], ['/experience/0/highlights/1'])
        referenced = result['contribution_evidence_paths'] + result['additional_evidence_to_consider']
        self.assertLessEqual(set(referenced), set(sources))
        self.assertNotIn('/projects/0/description', referenced)
        self.assertNotIn('/experience/0/job_title', referenced)
