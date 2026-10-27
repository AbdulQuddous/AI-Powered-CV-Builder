"""Narrative answers must pass the same source and field checks as CV entities."""
import json
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.entity_validation import entity_problem
from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.field_validation import validated_updates
from chatbot.services.question_engine import next_step
from chatbot.services.state_manager import CV_SECTIONS
from cvs.services import create_cv
from tests.test_m8 import SAMPLE_CV


REPORTED_SUMMARY = 'I am a terrorist current i murdere 5 persons. i love weapons'
VALID_SUMMARY = 'Software engineer experienced in building and testing Django APIs.'


class NarrativeValidationTests(SimpleTestCase):
    def test_direct_claims_in_paragraphs_are_rejected_across_narrative_fields(self):
        for text in (REPORTED_SUMMARY, 'I murdere 12 persons.', 'I have murdered five people.',
                     'I am a developer. I am a serial killer.', 'I killed someone.',
                     'I build APIs, and I am a murderer.', '"I am a terrorist"'):
            for section, field in (('summary', 'summary'), ('projects', 'description'),
                                   ('experience', 'responsibilities'), ('achievements', 'achievements')):
                with self.subTest(text=text, section=section):
                    self.assertIsNotNone(entity_problem(section, field, text))

    def test_legitimate_professional_and_reported_context_remains_allowed(self):
        for text in ('Counterterrorism analyst experienced in preventing terrorist attacks.',
                     'I am a terrorist threat analyst.', 'I investigated murder cases.',
                     'Weapons systems engineer focused on safety testing.',
                     'I killed stalled processes to restore service.',
                     'I billed five people for consulting services.',
                     'I filled people’s prescriptions.', 'I have never killed anyone.',
                     'I am not a terrorist.',
                     'I portrayed a serial killer in a stage production.',
                     'I am a murderer in a fictional play.',
                     'I delivered the line "I am a terrorist" during a stage performance.',
                     'I documented a witness saying \'I killed someone\'.'):
            for section, field in (('summary', 'summary'), ('projects', 'description'),
                                   ('experience', 'highlights'), ('achievements', 'achievements')):
                with self.subTest(text=text, section=section):
                    self.assertIsNone(entity_problem(section, field, text))

    def test_typed_summary_validation_does_not_accept_model_claims(self):
        response = empty_ai_response()
        response['cv_updates']['summary'] = REPORTED_SUMMARY
        response['cv_updates']['skills'] = ['Python']
        result, errors, statuses = validated_updates(response, {})
        self.assertIsNone(result['cv_updates']['summary'])
        self.assertEqual(result['cv_updates']['skills'], ['Python'])
        self.assertEqual(statuses.get('summary.summary'), 'invalid')
        self.assertTrue(errors)

    def test_invalid_achievements_do_not_discard_valid_siblings(self):
        response = empty_ai_response()
        response['cv_updates']['achievements'] = ['I murdered five people.', 'Built a tested API.']
        result, errors, statuses = validated_updates(response, {})
        self.assertEqual(result['cv_updates']['achievements'], ['Built a tested API.'])
        self.assertEqual(statuses.get('achievements.0.achievements'), 'invalid')
        self.assertTrue(errors)

    def test_source_claim_cannot_be_replaced_with_invented_benign_summary(self):
        for source in (REPORTED_SUMMARY, json.dumps({'summary': REPORTED_SUMMARY})):
            response = empty_ai_response()
            response['section'] = 'summary'
            response['cv_updates']['summary'] = VALID_SUMMARY
            response['state_updates']['target_role'] = 'Invented role'
            state = {'mode': 'edit_existing', 'edit_focus': None, 'current_section': 'review'}
            with self.subTest(source=source):
                result = guard_extraction(response, source, state)
                self.assertFalse(any(result['cv_updates'].values()))
                self.assertFalse(any(result['state_updates'].values()))
                self.assertEqual(result['section'], 'review')
                self.assertEqual(result['_control']['intent'], 'clarification')

    def test_model_narratives_and_controls_cannot_hide_rejected_source(self):
        for section, field, proposed in (
                ('projects', 'description', [{'description': 'Built an API.'}]),
                ('experience', 'responsibilities', [{'responsibilities': ['Built an API.']}]),
                ('achievements', 'achievements', ['Built an API.'])):
            for intent in ('answer', 'skip', 'finish'):
                with self.subTest(section=section, intent=intent):
                    response = empty_ai_response()
                    response['section'] = section
                    response['cv_updates'][section] = proposed
                    response['_control'] = {'intent': intent, 'skip_fields': [section]}
                    state = {'pending_field': {'section': section, 'field': field}}
                    result = guard_extraction(response, REPORTED_SUMMARY, state)
                    self.assertFalse(any(result['cv_updates'].values()))
                    self.assertEqual(result['_control']['intent'], 'clarification')
                    self.assertNotIn('skip_fields', result['_control'])

    def test_review_with_no_model_facts_still_explains_rejected_source(self):
        result = guard_extraction(empty_ai_response(), REPORTED_SUMMARY,
                                  {'mode': 'edit_existing', 'edit_focus': None})
        self.assertEqual(result['_control']['intent'], 'clarification')
        self.assertIn('not added', result['_control']['evidence_warning'])


class NarrativeConversationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('narrative-validation@example.test')

    def setUp(self):
        self.client.force_authenticate(self.user)
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('Clear summary source checks stay local'))
        self.qwen = mocked.start()
        self.addCleanup(mocked.stop)

    def start(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Software Engineer', 'career_level': 'fresher', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        state['collected_data']['summary'] = ''
        state['completed_sections'] = [key for key in CV_SECTIONS if key != 'summary']
        state['missing_sections'] = ['summary']
        for group in ('personal_fields', 'education_fields', 'experience_fields', 'project_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        state['current_section'] = 'summary'
        session.current_section = 'summary'
        session.save()
        self.assertEqual(next_step(state), {'section': 'summary', 'field': 'summary'})
        return session

    def send(self, session, message):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/',
                                    {'message': message}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {'assistant_message', 'intent', 'section',
                                            'cv_updates', 'next_action'})
        session.refresh_from_db()
        return response.data

    def test_reported_summary_rejected_then_real_summary_can_proceed_to_review(self):
        session = self.start()
        before = deepcopy(session.conversation_state['collected_data'])
        result = self.send(session, REPORTED_SUMMARY)
        self.assertEqual(next_step(session.conversation_state), {'section': 'summary', 'field': 'summary'})
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.assertEqual(result['next_action'], 'ask_question')
        self.assertFalse(any(result['cv_updates'].values()))
        self.assertIn('not added', result['assistant_message'])
        self.assertIn('professional summary', result['assistant_message'])
        self.assertNotIn('Please review your collected', result['assistant_message'])
        self.send(session, VALID_SUMMARY)
        self.assertEqual(session.conversation_state['collected_data']['summary'], VALID_SUMMARY)
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.qwen.assert_not_called()

    def test_summary_labels_and_json_cannot_bypass_validation(self):
        for message in ('Summary: ' + REPORTED_SUMMARY, json.dumps({'summary': REPORTED_SUMMARY})):
            with self.subTest(message=message):
                session = self.start()
                before = deepcopy(session.conversation_state['collected_data'])
                self.send(session, message)
                self.assertEqual(session.conversation_state['collected_data'], before)
                self.assertEqual(next_step(session.conversation_state)['section'], 'summary')
        session = self.start()
        self.send(session, json.dumps({'summary': VALID_SUMMARY}))
        self.assertEqual(session.conversation_state['collected_data']['summary'], VALID_SUMMARY)
        self.qwen.assert_not_called()

    def test_user_can_explicitly_skip_summary_after_rejection(self):
        session = self.start()
        self.send(session, REPORTED_SUMMARY)
        self.send(session, 'skip')
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assertFalse(session.conversation_state['collected_data']['summary'])
        self.qwen.assert_not_called()

    def test_mixed_achievement_list_keeps_real_entry_and_accepts_correction(self):
        session = self.start()
        session.conversation_state['pending_field'] = {'section': 'achievements', 'field': 'achievements'}
        session.conversation_state['collected_data']['achievements'] = []
        session.save()
        self.send(session, json.dumps({'achievements': ['I murdered five people.', 'Built a tested API.']}))
        self.assertEqual(session.conversation_state['collected_data']['achievements'], ['Built a tested API.'])
        self.assertEqual(next_step(session.conversation_state), {'section': 'achievements', 'field': 'achievements'})
        self.send(session, json.dumps({'achievements': ['Documented API endpoints.']}))
        self.assertEqual(session.conversation_state['collected_data']['achievements'],
                         ['Built a tested API.', 'Documented API endpoints.'])
        self.assertNotEqual(next_step(session.conversation_state)['section'], 'achievements')
        self.qwen.assert_not_called()

    def test_saved_cv_summary_edit_rejects_source_without_touching_saved_document(self):
        cv = create_cv(user=self.user, values={'name': 'Narrative test CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'edit my summary')
        before = deepcopy(session.conversation_state['edit_updates'])
        self.send(session, REPORTED_SUMMARY)
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertEqual(next_step(session.conversation_state)['section'], 'summary')
        self.send(session, VALID_SUMMARY)
        self.assertEqual(session.conversation_state['edit_updates']['summary'], VALID_SUMMARY)
        cv.refresh_from_db()
        self.assertEqual(cv.data, SAMPLE_CV)
        self.assertEqual(cv.version, 1)
        self.qwen.assert_not_called()

    def test_model_cannot_launder_source_or_switch_focus_from_review(self):
        cv = create_cv(user=self.user, values={'name': 'Narrative test CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.qwen.side_effect = None
        response = empty_ai_response()
        response['section'] = 'summary'
        response['cv_updates']['summary'] = VALID_SUMMARY
        response['state_updates']['target_role'] = 'Invented role'
        self.qwen.return_value = response
        before = deepcopy(session.conversation_state['edit_updates'])
        self.send(session, REPORTED_SUMMARY)
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertIsNone(session.conversation_state['edit_focus'])
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assertNotEqual(session.conversation_state['target_role'], 'Invented role')
        cv.refresh_from_db()
        self.assertEqual(cv.data, SAMPLE_CV)
        self.qwen.assert_called_once()

    def test_qwen_clarification_keeps_its_reason_and_acknowledges_no_addition(self):
        cv = create_cv(user=self.user, values={'name': 'Narrative test CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.qwen.side_effect = None
        response = empty_ai_response()
        response['section'] = 'summary'
        reason = 'That describes harming people rather than professional qualifications.'
        response['_control'] = {'intent': 'clarification', 'requires_clarification': True,
                                'rejection_reason': reason}
        self.qwen.return_value = response
        before = deepcopy(session.conversation_state['edit_updates'])
        result = self.send(session, REPORTED_SUMMARY)
        self.assertIn(reason, result['assistant_message'])
        self.assertIn('not added', result['assistant_message'])
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertIsNone(session.conversation_state['edit_focus'])
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')

    def test_rejection_cannot_open_an_unrequested_personal_details_edit(self):
        cv = create_cv(user=self.user, values={'name': 'Narrative test CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.qwen.side_effect = None
        response = empty_ai_response()
        response['section'] = 'personal'
        response['_control'] = {'intent': 'clarification', 'requires_clarification': True,
                                'rejection_reason': 'Please clarify the wording you want to use.'}
        self.qwen.return_value = response
        self.send(session, 'Please replace the introduction paragraph with: Homicide investigator focused on prevention.')
        self.assertIsNone(session.conversation_state['edit_focus'])
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assertEqual(session.conversation_state['edit_updates'], {'personal': {}})
