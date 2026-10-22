"""Skip commands with a small typo must never become personal facts."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.field_validation import validated_updates
from chatbot.services.local_extractor import is_skip_command
from chatbot.services.question_engine import next_step


class SkipCommandTests(SimpleTestCase):
    def test_exact_and_one_typo_commands_are_recognized(self):
        for text in ['skip', 'skip it', 'skip ot', 'ski[ it', 'skpi it', 'skp it',
                     'skip iy', 'SKIP OT!', 'skip it.', 'none', 'no']:
            with self.subTest(text=text):
                self.assertTrue(is_skip_command(text))

    def test_names_urls_and_longer_answers_are_not_fuzzy_matched(self):
        for text in ['Skip Smith', 'Skip Li', 'Ski Patel', 'Skipper', 'Ski',
                     'My full name is Skip Ot', 'skip.it@example.com',
                     'https://example.com/skip-it', 'I use Skip for scheduling',
                     'I have LinkedIn but no GitHub', 'skip this project and add Python']:
            with self.subTest(text=text):
                self.assertFalse(is_skip_command(text))

    def test_extracted_skip_labels_cannot_become_names_without_explicit_naming_intent(self):
        for name in ['skip', 'skip ot', 'ski[ it', 'none']:
            response = empty_ai_response()
            response['cv_updates']['personal'] = {'full_name': name}
            clean, errors, statuses = validated_updates(response, {}, user_message='Please skip this question')
            self.assertFalse(clean['cv_updates']['personal'])
            self.assertTrue(errors)
            self.assertEqual(statuses['personal.full_name'], 'invalid')

    def test_explicit_real_names_remain_usable(self):
        for name, message in [('Skip', 'My full name is Skip'),
                              ('Skip Ot', 'My name is Skip Ot'),
                              ('No', 'Change my full name to No'),
                              ('Skip', '{"personal":{"full_name":"Skip"}}')]:
            response = empty_ai_response()
            response['cv_updates']['personal'] = {'full_name': name}
            clean, errors, _ = validated_updates(response, {}, user_message=message)
            self.assertFalse(errors, (name, errors))
            self.assertEqual(clean['cv_updates']['personal'], {'full_name': name})


class SkipTypoConversationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('skip-typos@example.test')

    def setUp(self):
        self.client.force_authenticate(self.user)
        provider = patch('chatbot.services.conversation_service.QwenClient.generate',
                         side_effect=AssertionError('Skip commands and personal answers must remain local'))
        self.qwen = provider.start(); self.addCleanup(provider.stop)

    def start(self):
        return create_chat_session(user=self.user, initial_values={
            'target_role': 'Backend Developer', 'career_level': 'fresher', 'template_id': 'modern'})

    def send(self, session, message):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': message}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        return response.data

    def test_reported_transcript_keeps_name_required_until_an_actual_name_is_supplied(self):
        session = self.start()
        for text in ['skip', 'skip ot', 'skip it', 'ski[ it']:
            result = self.send(session, text)
            self.assertEqual(next_step(session.conversation_state), {'section': 'personal', 'field': 'full_name'})
            self.assertEqual(result['intent'], 'clarify_information')
            self.assertIn('full name', result['assistant_message'])
            self.assertIn('cannot be skipped', result['assistant_message'])
            self.assertFalse(session.conversation_state['collected_data']['personal'].get('full_name'))
            self.assertFalse(any(result['cv_updates'].values()))
        self.send(session, 'Ali Khan')
        self.assertEqual(next_step(session.conversation_state)['field'], 'email')
        self.assertEqual(session.conversation_state['collected_data']['personal']['full_name'], 'Ali Khan')
        self.qwen.assert_not_called()

    def test_email_uses_the_same_skip_policy_without_losing_valid_name(self):
        session = self.start()
        self.send(session, 'Ali Khan')
        for text in ['skip', 'skip it', 'skip ot', 'ski[ it', 'skpi it']:
            result = self.send(session, text)
            self.assertEqual(next_step(session.conversation_state)['field'], 'email')
            self.assertIn('email address', result['assistant_message'])
            self.assertIn('cannot be skipped', result['assistant_message'])
            self.assertNotIn("doesn't look like a valid email", result['assistant_message'])
            self.assertEqual(session.conversation_state['collected_data']['personal'], {'full_name': 'Ali Khan'})
        self.send(session, 'ali@example.com')
        self.assertEqual(next_step(session.conversation_state)['field'], 'phone')
        self.qwen.assert_not_called()

    def test_optional_fields_can_still_be_skipped_with_a_small_typo(self):
        session = self.start()
        state = session.conversation_state
        state['pending_field'] = {'section': 'personal', 'field': 'linkedin'}
        session.save(update_fields=['conversation_state'])
        self.send(session, 'ski[ it')
        self.assertEqual(session.conversation_state['personal_fields']['linkedin'], 'skipped')
        self.assertFalse(session.conversation_state['collected_data']['personal'].get('linkedin'))
        self.qwen.assert_not_called()

    def test_legitimate_names_with_skip_or_ski_are_preserved(self):
        for name in ['Skip Smith', 'Skip Li', 'Ski Patel', 'Skipper', 'علی خان']:
            with self.subTest(name=name):
                session = self.start()
                self.send(session, name)
                self.assertEqual(session.conversation_state['collected_data']['personal']['full_name'], name)
                self.assertEqual(next_step(session.conversation_state)['field'], 'email')
        session = self.start()
        self.send(session, 'My full name is Skip')
        self.assertEqual(session.conversation_state['collected_data']['personal']['full_name'], 'Skip')

    def test_skip_typos_cannot_finish_an_incomplete_cv(self):
        session = self.start()
        for text in ['skip ot', 'ski[ it', 'finish']:
            self.assertNotEqual(self.send(session, text)['next_action'], 'complete')
            self.assertEqual(session.status, 'active')
        self.assertEqual(next_step(session.conversation_state)['field'], 'full_name')
