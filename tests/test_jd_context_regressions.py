"""Protect factual dates and career identity while adding saved-CV evidence."""
from django.test import SimpleTestCase

from ai.services.tailoring import numerical_claims, redact, wording_rejection


class JDContextRegressions(SimpleTestCase):
    def test_counts_keep_their_unit_with_technical_descriptors_and_app_abbreviation(self):
        self.assertEqual(numerical_claims('Built 5 Django REST APIs.'), numerical_claims('Built five APIs.'))
        self.assertEqual(numerical_claims('Built 2 web apps.'), numerical_claims('Built two applications.'))
        self.assertEqual(numerical_claims('Built 2 Django\nweb applications.\n'), numerical_claims('Built 2 Django web applications.'))
        self.assertNotEqual(numerical_claims('Reviewed 5 pull requests.'), numerical_claims('Built 5 Django APIs.'))

    def test_redaction_preserves_cv_dates_but_removes_real_contact_forms(self):
        for date in ('2026-06', '2020-01 - 2022-06', '2026-06-15'):
            with self.subTest(date=date):
                self.assertEqual(redact(date, []), date)
        for contact in ('+92 (300) 123-4567', '03001234567', 'someone@example.test',
                        'https://example.test/profile'):
            with self.subTest(contact=contact):
                self.assertNotIn(contact, redact(contact, []))

    def test_saved_fact_synthesis_cannot_replace_an_intern_with_a_junior_or_student(self):
        original = 'Python Developer Intern building Django applications.'
        for identity in ('Junior', 'Student'):
            rewritten = original.replace('Intern', identity)
            with self.subTest(identity=identity):
                self.assertEqual(wording_rejection(original, rewritten,
                    [original, f'{identity} developer.'], allow_synthesis=True), 'responsibility_changed')
