"""JD relevance may change emphasis, while facts keep their source and scope."""
from copy import deepcopy

from django.test import SimpleTestCase

from ai.exceptions import AIStructuredOutputError
from ai.services.tailoring import validate_response, wording_rejection, writable_text


SUMMARY = 'Python Developer Intern (2026), comfortable with Django and Git.'
DEPLOYMENT = 'Deployed Django APIs and reduced response time by 25%.'
JD = ('Build Django APIs, deploy AI features, implement RAG and vector search, '
      'train models, and lead software teams.')


class JDEvidenceScopeTests(SimpleTestCase):
    def setUp(self):
        self.context = {
            'meta': {'target_role': 'Senior AI Engineer'},
            'summary': SUMMARY,
            'skills': ['Django', 'Git'],
            'experience': [{
                'company': 'Example Systems', 'job_title': 'Python Developer Intern',
                'start_date': '2026-06', 'end_date': '2026-08',
                'highlights': ['Built Django APIs.', DEPLOYMENT],
            }],
            'projects': [{
                'name': 'Research project', 'description': 'Built a PyTorch application.',
                'technologies': ['PyTorch'], 'highlights': [],
            }],
            'achievements': [],
        }

    def proposal(self, path, rewritten):
        return {
            'summary': 'Emphasized confirmed API delivery for the job requirements.',
            'changes': [{
                'path': path, 'original': writable_text(self.context)[path],
                'rewritten': rewritten, 'reason': 'Emphasizes confirmed delivery work requested by the job.',
            }],
            'suggestions': [],
        }

    def review(self, path, rewritten):
        return validate_response(self.proposal(path, rewritten), writable_text(self.context),
                                 self.context, [], job_description=JD)

    def test_whole_cv_summary_can_synthesize_saved_deployment_and_metric(self):
        original = deepcopy(self.context)
        rewritten = SUMMARY + ' ' + DEPLOYMENT
        result = self.review('/summary', rewritten)
        self.assertEqual(result['changes'][0]['rewritten'], rewritten)
        self.assertEqual(self.context, original)

    def test_direct_synthesis_is_explicit_and_default_selected_text_remains_bounded(self):
        rewritten = SUMMARY + ' ' + DEPLOYMENT
        self.assertIsNone(wording_rejection(SUMMARY, rewritten, self.context, allow_synthesis=True))
        self.assertIsNotNone(wording_rejection(SUMMARY, rewritten, self.context))

    def test_same_employer_facts_can_strengthen_a_related_bullet(self):
        rewritten = 'Built and deployed Django APIs, reducing response time by 25%.'
        result = self.review('/experience/0/highlights/0', rewritten)
        self.assertEqual(result['changes'][0]['rewritten'], rewritten)

    def test_same_employer_technology_is_available_without_using_global_skills(self):
        self.context['experience'][0]['highlights'].append('Built Django APIs using PostgreSQL.')
        rewritten = 'Built Django APIs using PostgreSQL.'
        self.assertEqual(self.review('/experience/0/highlights/0', rewritten)['changes'][0]['rewritten'], rewritten)

    def test_other_project_technology_cannot_move_to_an_employer(self):
        with self.assertRaises(AIStructuredOutputError) as raised:
            self.review('/experience/0/highlights/0', 'Built Django APIs using PyTorch.')
        self.assertEqual(raised.exception.reason, 'factual_validation')

    def test_other_employer_metric_cannot_move_to_a_project(self):
        with self.assertRaises(AIStructuredOutputError):
            self.review('/projects/0/description', 'Built a PyTorch application, reducing response time by 25%.')

    def test_summary_can_prioritize_confirmed_project_technology_without_employer_attribution(self):
        rewritten = SUMMARY + ' Built a PyTorch application.'
        self.assertEqual(self.review('/summary', rewritten)['changes'][0]['rewritten'], rewritten)

    def test_job_description_is_never_evidence_for_missing_ai_work(self):
        for addition in (
            ' Built rag workflows.',
            ' Implemented retrieval augmented generation.',
            ' Implemented vector search.',
            ' Trained models.',
            ' Deployed production-grade AI systems.',
        ):
            with self.subTest(addition=addition), self.assertRaises(AIStructuredOutputError):
                self.review('/summary', SUMMARY + addition)

    def test_explicit_model_training_can_be_synthesized_without_new_tool_claims(self):
        self.context['projects'][0]['description'] = 'Trained PyTorch models.'
        rewritten = SUMMARY + ' Trained PyTorch models.'
        self.assertEqual(self.review('/summary', rewritten)['changes'][0]['rewritten'], rewritten)

    def test_metadata_target_is_not_confirmation_of_seniority(self):
        with self.assertRaises(AIStructuredOutputError):
            self.review('/summary', SUMMARY.replace('Python Developer Intern', 'Senior Python Developer'))

    def test_existing_intern_identity_cannot_disappear(self):
        with self.assertRaises(AIStructuredOutputError):
            self.review('/summary', SUMMARY.replace('Developer Intern', 'Developer'))

    def test_proficiency_does_not_inherit_from_another_entry(self):
        self.context['experience'][0]['highlights'].append('Proficient with Git.')
        with self.assertRaises(AIStructuredOutputError):
            self.review('/summary', SUMMARY.replace('comfortable', 'proficient'))

    def test_original_metrics_remain_even_when_synthesis_is_allowed(self):
        rewritten = SUMMARY.replace('(2026)', '') + ' ' + DEPLOYMENT
        self.assertEqual(wording_rejection(SUMMARY, rewritten, self.context, allow_synthesis=True),
                         'numerical_claims')

    def test_existing_date_precision_and_metric_qualifiers_cannot_change(self):
        original = 'Built Django APIs since 2026-06, reducing response time by over 25%.'
        for rewritten in (
            original.replace('2026-06', '2026'),
            original.replace('2026-06', '2026-07'),
            original.replace('over 25%', '25%'),
            original.replace('over 25%', 'over 30%'),
        ):
            with self.subTest(rewritten=rewritten):
                self.assertEqual(wording_rejection(original, rewritten, original, allow_synthesis=True),
                                 'numerical_claims')

    def test_standard_framework_and_ai_fundamentals_aliases_are_equivalent(self):
        pairs = (
            ('Django REST Framework', 'DRF'),
            ('natural language processing', 'NLP'),
            ('large language models', 'LLMs'),
            ('object-oriented programming', 'OOP'),
            ('data structures and algorithms', 'DSA'),
        )
        for expanded, abbreviation in pairs:
            for source, target in ((expanded, abbreviation), (abbreviation, expanded)):
                original, rewritten = f'Used {source}.', f'Used {target}.'
                with self.subTest(original=original):
                    self.assertIsNone(wording_rejection(original, rewritten, original))

    def test_ordinary_sentence_start_does_not_hide_unconfirmed_vendors(self):
        original = 'Built Django APIs and tested them.'
        self.assertIsNone(wording_rejection(original, 'Combined Django API development with testing.', original))
        for vendor in ('AcmeCloud', 'Pinecone', 'OpenAI'):
            with self.subTest(vendor=vendor):
                self.assertIsNotNone(wording_rejection(
                    original, f'Combined Django API development with testing using {vendor}.', original))

    def test_summary_new_metrics_must_exist_in_saved_evidence(self):
        with self.assertRaises(AIStructuredOutputError):
            self.review('/summary', SUMMARY + ' Reduced response time by 99%.')
