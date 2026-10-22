"""Wrong entity types and noise cannot become employer or credential facts."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.entity_validation import entity_problem, obvious_noise
from chatbot.services.education_answers import parse_certificate
from chatbot.services.message_routing import classify
from chatbot.services.question_engine import next_step
from chatbot.services.section_answers import section_request
from cvs.services import create_cv
from tests.test_m8 import SAMPLE_CV


class EntityValidationTests(SimpleTestCase):
    def test_experience_typos_are_commands_without_facts(self):
        for message in ['i want to add xperience', 'add experiance', 'please add experince']:
            with self.subTest(message=message):
                self.assertEqual(section_request(message), ('experience', 'add'))
        self.assertIsNone(section_request('I worked at Xperience Systems'))

    def test_direct_fool_variants_are_abuse_but_workplace_quotes_remain_eligible(self):
        for text in ['are  you fool', 'are you a fool?', 'you are a fool', 'r u a fool']:
            self.assertEqual(classify(text), 'inappropriate', text)
        for text in ['My manager called me a fool.', 'Developed fool-proof validation.',
                     '"The Fool" is the title of my project.']:
            self.assertNotEqual(classify(text), 'inappropriate', text)

    def test_random_labels_are_rejected_without_rejecting_real_codes_or_brands(self):
        for label in ['ter45fase4', 't33ssr', 'asdfghjkl', 'aaaaaa']:
            self.assertTrue(obvious_noise(label), label)
        for label in ['AZ-900', 'AWS SAA-C03', '1Z0-071', 'ISO27001', 'CS50x',
                      'eJPTv2', 'n8n', '37signals', 'a16z', '東京食堂']:
            self.assertFalse(obvious_noise(label), label)

    def test_activity_is_not_an_employer_without_explicit_workplace_context(self):
        self.assertIsNotNone(entity_problem('experience', 'company', 'lamb cooking', 'lamb cooking'))
        self.assertIsNone(entity_problem('experience', 'company', 'Lamb Cooking', 'Company: Lamb Cooking'))
        self.assertIsNone(entity_problem('experience', 'role', 'Chef', 'Chef'))
        self.assertIsNone(entity_problem('certifications', 'name', 'Lamb Cooking Certificate', 'Lamb Cooking Certificate'))

    def test_certificate_title_punctuation_is_not_invented_issuer_metadata(self):
        title = 'AWS Certified Solutions Architect - Associate'
        self.assertIsNone(parse_certificate(title))
        self.assertEqual(parse_certificate('Certification: ' + title), {'name': title})
        self.assertIsNone(parse_certificate('Professional Certificate; Advanced Level'))

    def test_explicit_certificate_issuer_and_date_are_collected_together(self):
        self.assertEqual(parse_certificate('Certification: Google AI Essentials — Google issue date 2026-06'),
                         {'name': 'Google AI Essentials', 'issuer': 'Google', 'date': '2026-06'})
        self.assertEqual(parse_certificate('Regional Professional Practice; issuer: Example Institute'),
                         {'name': 'Regional Professional Practice', 'issuer': 'Example Institute'})


class ChatEntityValidationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('entity-validation@example.test')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.document = deepcopy(SAMPLE_CV)
        self.document['meta']['career_level'] = 'experienced'
        self.cv = create_cv(user=self.user, values={'name': 'Entity validation CV', 'data': self.document})
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('Clear entity checks must stay local'))
        self.qwen = mocked.start(); self.addCleanup(mocked.stop)

    def start(self, *, initial=False, section='experience'):
        if initial:
            session = create_chat_session(user=self.user, initial_values={
                'target_role': 'Backend Developer', 'career_level': 'fresher'})
            state = session.conversation_state
            state['pending_field'] = {'section': section, 'field': 'company' if section == 'experience' else section}
            session.save(update_fields=['conversation_state'])
        else:
            session = create_chat_session(user=self.user, cv_id=self.cv.pk)
            self.send(session, 'add a job' if section == 'experience' else 'add a certification')
        return session

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {'assistant_message', 'intent', 'section', 'cv_updates', 'next_action'})
        session.refresh_from_db()
        return response.data

    def collected(self, session):
        state = session.conversation_state
        return state.get('edit_updates') if state.get('mode') == 'edit_existing' else state['collected_data']

    def assert_saved_unchanged(self):
        self.cv.refresh_from_db()
        self.assertEqual((self.cv.data, self.cv.version), (self.document, 1))

    def test_reported_transcript_never_adds_noise_or_activity_as_employment(self):
        session = self.start(section='certifications')
        for text in ['o shutup', 'ter45fase4', 'yes, add it']:
            self.send(session, text)
            self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'cancel')
        self.assertEqual(self.send(session, 'are  you fool')['intent'], 'irrelevant')
        self.assertEqual(self.send(session, 'i want to add xperience')['section'], 'experience')
        self.assertEqual(self.send(session, 'are  you fool')['intent'], 'irrelevant')
        result = self.send(session, 'lamb cooking')
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.assertIn('activity', result['assistant_message'])
        self.assertFalse(self.collected(session).get('experience'))
        self.send(session, 'Bitech Systems')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'Bitech Systems'}])
        self.qwen.assert_not_called(); self.assert_saved_unchanged()

    def test_wrong_company_entity_stays_at_company_in_both_modes(self):
        for initial in [False, True]:
            for answer in ['lamb cooking', 'playing cricket', 'Python', 'English', '2026-06', 'https://example.com']:
                with self.subTest(initial=initial, answer=answer):
                    session = self.start(initial=initial)
                    self.send(session, answer)
                    self.assertEqual(next_step(session.conversation_state)['field'], 'company')
                    self.assertFalse(self.collected(session).get('experience'))
        self.assert_saved_unchanged()

    def test_company_labels_disambiguate_unusual_names_and_are_not_saved_as_prefixes(self):
        for message, name in [('Company: Lamb Cooking', 'Lamb Cooking'),
                              ('Company: Python', 'Python'), ('n8n', 'n8n'),
                              ('A Cup of Tea', 'A Cup of Tea'), ('東京食堂', '東京食堂')]:
            with self.subTest(message=message):
                session = self.start()
                self.send(session, message)
                self.assertEqual(self.collected(session)['experience'], [{'company': name}])
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')

    def test_culinary_experience_is_valid_for_a_different_target_role(self):
        session = self.start()
        self.send(session, 'Example Restaurant')
        self.send(session, 'lamb cooking')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.send(session, 'Job title: Chef')
        self.send(session, 'Prepared meals.')
        self.assertEqual(self.collected(session)['experience'][0]['role'], 'Chef')
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assert_saved_unchanged()

    def test_random_certificate_is_not_confirmable_in_both_modes(self):
        for initial in [False, True]:
            for title in ['ter45fase4', 't33ssr', 'asdfghjkl', 'ter45fase4 Certificate']:
                with self.subTest(initial=initial, title=title):
                    session = self.start(initial=initial, section='certifications')
                    self.send(session, title)
                    self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
                    self.send(session, 'yes')
                    self.assertFalse(self.collected(session).get('certifications'))
                    self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')

    def test_structured_certificate_metadata_cannot_make_a_random_title_valid(self):
        session = self.start(section='certifications')
        self.send(session, '{"certifications": [{"name": "ter45fase4", "issuer": "Example Training", "date": "2026-06"}]}')
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_clear_certificate_is_kept_when_a_sibling_is_random(self):
        session = self.start(section='certifications')
        self.send(session, 'Python Certificate, ter45fase4')
        self.assertEqual(self.collected(session)['certifications'], [{'name': 'Python Certificate'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.send(session, 'cancel')
        self.assertEqual(self.collected(session)['certifications'], [{'name': 'Python Certificate'}])

    def test_ambiguous_certificate_requires_actual_details_rather_than_yes(self):
        session = self.start(section='certifications')
        self.send(session, 'Regional Professional Practice')
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'yes, add it')
        self.assertFalse(self.collected(session).get('certifications'))
        self.send(session, 'Certification: Regional Professional Practice — Example Institute')
        self.assertEqual(self.collected(session)['certifications'], [
            {'name': 'Regional Professional Practice', 'issuer': 'Example Institute'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_legacy_random_optional_confirmation_cannot_be_accepted(self):
        session = self.start(section='certifications')
        session.conversation_state['optional_entry_confirmation'] = {
            'section': 'certifications', 'entries': [{'name': 'ter45fase4'}]}
        session.save(update_fields=['conversation_state'])
        self.send(session, 'yes')
        self.assertFalse(self.collected(session).get('certifications'))
        self.send(session, 'cancel')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_model_extraction_cannot_store_an_activity_as_company(self):
        session = self.start()
        response = empty_ai_response()
        response['section'] = 'experience'
        response['cv_updates']['experience'] = [{'company': 'lamb cooking'}]
        self.qwen.side_effect = None; self.qwen.return_value = response
        self.send(session, 'I was thinking about lamb cooking')
        self.assertFalse(self.collected(session).get('experience'))
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.qwen.assert_called_once()

    def test_credential_codes_and_culinary_certificates_are_accepted(self):
        for title in ['AZ-900', 'CCNA', 'ISO27001', 'Lamb Cooking Certificate']:
            with self.subTest(title=title):
                session = self.start(section='certifications')
                self.send(session, title)
                self.assertEqual(self.collected(session)['certifications'][0]['name'], title)

    def test_a_skill_or_issuer_alone_is_not_a_certification(self):
        for title in ['Python', 'SQL', 'AWS', 'Google', 'Microsoft']:
            with self.subTest(title=title):
                session = self.start(section='certifications')
                self.send(session, title)
                self.send(session, 'yes')
                self.assertFalse(self.collected(session).get('certifications'))
                self.send(session, 'Certification: Google AI Essentials — Google')
                self.assertEqual(self.collected(session)['certifications'][0]['name'], 'Google AI Essentials')

    def test_skill_and_language_replies_do_not_become_job_titles(self):
        for answer in ['Python', 'English', 'Bitech Company']:
            with self.subTest(answer=answer):
                session = self.start()
                self.send(session, 'Example Restaurant')
                self.send(session, answer)
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')
                self.assertEqual(self.collected(session)['experience'], [{'company': 'Example Restaurant'}])

    def test_unknown_lowercase_employer_uses_qwen_instead_of_blind_scalar_assignment(self):
        session = self.start()
        self.qwen.side_effect = None
        self.qwen.return_value = empty_ai_response()
        self.send(session, 'mango salad')
        self.assertFalse(self.collected(session).get('experience'))
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.qwen.assert_called_once()

    def test_abusive_json_entity_does_not_bypass_conduct_checks(self):
        session = self.start(section='certifications')
        self.send(session, '{"certifications": [{"name": "are you a fool", "issuer": "Example"}]}')
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
