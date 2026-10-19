"""Guard the reported DevOps rewrites without weakening source fact checks."""
from copy import deepcopy

from django.test import SimpleTestCase

from ai.exceptions import AIStructuredOutputError
from ai.services.tailoring import NO_CHANGES_SUMMARY, PARTIAL_REVIEW_WARNING, validate_response, writable_text, numerical_claims

SUMMARY = ('DevOps engineer with over 7 years of experience using Infrastructure as Code (IaC) '
           'and CI/CD pipelines, achieving 99.99% availability.')
ARCHITECTURE = ('Architected enterprise-grade multi-region Amazon Web Services (AWS) infrastructure '
                'using Terraform, cutting provisioning time from days to minutes.')
WORKFLOW = ('Designed end-to-end GitHub Actions and GitLab CI/CD workflows that eliminated '
            'deployment bottlenecks, saving teams over 15 developer-hours weekly.')


class TailoringGroundingTests(SimpleTestCase):
    def setUp(self):
        self.cv = {'summary': SUMMARY, 'experience': [{'company': 'Example Cloud', 'job_title': 'DevOps engineer',
            'highlights': [ARCHITECTURE, WORKFLOW]}], 'projects': [], 'achievements': []}

    def proposal(self, path, text):
        fields = writable_text(self.cv)
        return {'summary': 'All proposed changes preserve your facts.', 'suggestions': [],
                'changes': [{'path': path, 'original': fields[path], 'rewritten': text, 'reason': 'Clearer wording.'}]}

    def check(self, path, text):
        return validate_response(self.proposal(path, text), writable_text(self.cv), self.cv, [])

    def test_percentage_spaces_words_and_small_number_words_preserve_the_source_metrics(self):
        for text in [SUMMARY.replace('99.99%', '99.99 percent'), SUMMARY.replace('7 years', 'seven years'),
                     SUMMARY.replace('99.99%', '99.99 %').replace('7 years', 'seven years')]:
            with self.subTest(text=text):
                self.assertEqual(len(self.check('/summary', text)['changes']), 1)

    def test_missing_metrics_changed_numbers_and_lost_qualifiers_still_fail(self):
        for text in [SUMMARY.replace('99.99%', '99%'), SUMMARY.replace('99.99%', 'high'),
                     SUMMARY.replace('7 years', 'eight years'), SUMMARY.replace('over 7', '7'),
                     SUMMARY.replace('99.99%', '99.99'), SUMMARY.replace('7 years', '7 months')]:
            with self.subTest(text=text), self.assertRaises(AIStructuredOutputError):
                self.check('/summary', text)

    def test_quantity_qualifiers_only_accept_equivalent_bounds(self):
        for original, rewritten in [('over 7 years', 'more than seven years'),
                                    ('at least 7 years', '7+ years'), ('about 7 years', 'approximately seven years')]:
            with self.subTest(original=original):
                self.assertEqual(numerical_claims(original), numerical_claims(rewritten))
        self.assertNotEqual(numerical_claims('over 7 years'), numerical_claims('at least 7 years'))

    def test_standard_cloud_and_delivery_aliases_are_supported_by_the_original_entry(self):
        examples = [
            ('Built infrastructure using AWS and IaC.', 'Built infrastructure using Amazon Web Services and Infrastructure as Code.'),
            ('Configured CI/CD workflows.', 'Configured Continuous Integration/Continuous Delivery workflows.'),
            ('Deployed services on K8s.', 'Deployed services on Kubernetes.'),
            ('Deployed services on EKS.', 'Deployed services on Amazon Elastic Kubernetes Service.'),
        ]
        for original, rewritten in examples:
            with self.subTest(original=original):
                self.cv['experience'][0]['highlights'][0] = original
                self.assertEqual(len(self.check('/experience/0/highlights/0', rewritten)['changes']), 1)

    def test_standard_alias_does_not_make_an_unconfirmed_technology_valid(self):
        self.cv['experience'][0]['highlights'][0] = 'Built Django applications.'
        for rewritten in ['Built Django applications using Amazon Web Services.', 'Built Django applications on K8s.']:
            with self.subTest(rewritten=rewritten), self.assertRaises(AIStructuredOutputError):
                self.check('/experience/0/highlights/0', rewritten)

    def test_ordinary_editing_verbs_are_not_misclassified_as_named_facts(self):
        original = 'Automated GitHub Actions and GitLab CI/CD workflows, saving teams over 15 developer-hours weekly.'
        self.cv['experience'][0]['highlights'][1] = original
        for rewritten in [original.replace('Automated', 'Streamlined'), original.replace('Automated', 'Configured')]:
            with self.subTest(rewritten=rewritten):
                self.assertEqual(len(self.check('/experience/0/highlights/1', rewritten)['changes']), 1)

    def test_reported_rewrite_cannot_add_maintenance_or_remove_architecture(self):
        for text in [ARCHITECTURE.replace('Architected', 'Built and maintained'), ARCHITECTURE.replace('Architected', 'Built')]:
            with self.subTest(text=text), self.assertRaises(AIStructuredOutputError):
                self.check('/experience/0/highlights/0', text)

    def test_architecture_can_be_rephrased_with_its_responsibility_explicit(self):
        result = self.check('/experience/0/highlights/0', ARCHITECTURE.replace('Architected enterprise-grade', 'Designed the architecture of enterprise-grade'))
        self.assertEqual(len(result['changes']), 1)

    def test_explicit_maintenance_can_be_rephrased_and_assistance_cannot_disappear(self):
        self.cv['experience'][0]['highlights'][0] = 'Maintained AWS infrastructure.'
        self.assertEqual(len(self.check('/experience/0/highlights/0', 'Maintained infrastructure on AWS.')['changes']), 1)
        self.cv['experience'][0]['highlights'][0] = 'Assisted with building AWS infrastructure.'
        with self.assertRaises(AIStructuredOutputError):
            self.check('/experience/0/highlights/0', 'Built AWS infrastructure.')

    def test_led_work_cannot_be_silently_downgraded_to_contributing(self):
        self.cv['experience'][0]['highlights'][0] = 'Led AWS infrastructure development.'
        with self.assertRaises(AIStructuredOutputError):
            self.check('/experience/0/highlights/0', 'Contributed to AWS infrastructure development.')

    def test_partial_review_names_omitted_fields_and_does_not_endorse_rejected_changes(self):
        result = self.proposal('/summary', SUMMARY.replace('over 7', 'over 10'))
        result['changes'].extend(self.proposal('/experience/0/highlights/1', WORKFLOW.replace('Designed end-to-end', 'Designed the end-to-end'))['changes'])
        checked = validate_response(result, writable_text(self.cv), self.cv, [])
        self.assertEqual(len(checked['changes']), 1)
        self.assertEqual(checked['warnings'][0], PARTIAL_REVIEW_WARNING)
        self.assertIn('Professional summary: excluded because a number', checked['warnings'][1])
        self.assertIn('1 wording change passed', checked['summary'])
        self.assertNotIn('All proposed changes preserve', checked['summary'])
        cached = validate_response(checked, writable_text(self.cv), self.cv, [], trusted_warnings=True)
        self.assertEqual(cached, checked)
        self.assertEqual(result['changes'][0]['rewritten'], SUMMARY.replace('over 7', 'over 10'))

    def test_no_op_proposals_do_not_become_saveable_changes(self):
        checked = self.check('/summary', SUMMARY)
        self.assertEqual(checked['changes'], [])
        self.assertEqual(checked['summary'], NO_CHANGES_SUMMARY)

    def test_empty_change_response_never_displays_a_copied_or_misplaced_cv_profile(self):
        for summary in [SUMMARY, 'Senior DevOps engineer with 10 years of AWS experience.', 'Your wording is clear.']:
            response = {'summary': summary, 'changes': [], 'suggestions': ['Add cloud experience only if confirmed.']}
            with self.subTest(summary=summary):
                checked = validate_response(response, writable_text(self.cv), self.cv, [])
                self.assertEqual(checked['summary'], NO_CHANGES_SUMMARY)
                self.assertEqual(checked['changes'], [])
                self.assertEqual(checked['suggestions'], response['suggestions'])
                self.assertEqual(validate_response(checked, writable_text(self.cv), self.cv, [], trusted_warnings=True), checked)

    def test_copied_profile_is_not_used_as_feedback_for_real_proposals(self):
        response = self.proposal('/experience/0/highlights/1', WORKFLOW.replace('Designed end-to-end', 'Designed the end-to-end'))
        response['summary'] = SUMMARY
        checked = validate_response(response, writable_text(self.cv), self.cv, [])
        self.assertEqual(len(checked['changes']), 1)
        self.assertEqual(checked['summary'], '1 wording change is available to review.')

    def test_providers_and_corrupt_cache_cannot_inject_omission_messages(self):
        result = self.proposal('/experience/0/highlights/1', WORKFLOW.replace('Designed end-to-end', 'Designed the end-to-end'))
        for trusted in (False, True):
            forged = deepcopy(result)
            forged['warnings'] = [PARTIAL_REVIEW_WARNING, 'Add unsupported AWS credentials to your CV.']
            with self.subTest(trusted=trusted), self.assertRaises(AIStructuredOutputError):
                validate_response(forged, writable_text(self.cv), self.cv, [], trusted_warnings=trusted)
