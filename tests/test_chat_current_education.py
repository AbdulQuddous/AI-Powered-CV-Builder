"""Ongoing education, grouped answers and expected graduation must not loop."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.collection_memory import repair_study_status, merge_collection_entries
from chatbot.services.education_answers import parse_education
from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.field_validation import validated_updates
from chatbot.services.message_routing import empty_ai_response
from chatbot.services.question_engine import next_step
from tests.test_m8 import SAMPLE_CV


DEGREE = 'i am studying in BS Computer Science at HITEC University'
ENTRY = {'degree': 'BS Computer Science', 'institution': 'HITEC University',
         'field_of_study': 'Computer Science', 'is_current': True}


class CurrentEducationParsingTests(SimpleTestCase):
    def test_status_only_does_not_become_a_degree(self):
        for message in ['I am currently studying', "I'm still studying", 'currently enrolled']:
            with self.subTest(message=message):
                self.assertEqual(parse_education(message), {'is_current': True})

    def test_grouped_ongoing_degree_retains_institution_and_subject(self):
        for message in [DEGREE, 'I am currently studying BS Computer Science at HITEC University',
                        "I'm pursuing BS Computer Science at HITEC University",
                        'I am enrolled in BS Computer Science at HITEC University']:
            with self.subTest(message=message):
                self.assertEqual(parse_education(message), ENTRY)

    def test_expected_graduation_sentences_and_reported_typo(self):
        for message in ['I  excpect to graduate in 2028-06', 'excpect to graduate in 2028-06',
                        'I expect to graduate in June 2028', 'I will graduate in June 2028',
                        'My expected graduation date is June 2028']:
            with self.subTest(message=message):
                self.assertEqual(parse_education(message, 'end_date'), {'end_date': '2028-06'})

    def test_partial_year_stays_partial_and_missing_start_is_not_invented(self):
        self.assertEqual(parse_education(DEGREE + ', expected graduation 2028'), {**ENTRY, 'end_date': '2028'})

    def test_negation_and_multiple_qualifications_are_not_guessed(self):
        for message in ['I am not currently studying', 'I am studying BS at A and MS at B']:
            with self.subTest(message=message):
                self.assertIsNone(parse_education(message))

    def test_current_study_allows_expected_date_but_jobs_remain_strict(self):
        for section, should_reject in [('education', False), ('experience', True)]:
            response = empty_ai_response()
            response['cv_updates'][section] = [{'is_current': True, 'end_date': '2028-06'}]
            clean, errors, statuses = validated_updates(response, {})
            with self.subTest(section=section):
                self.assertEqual(bool(errors), should_reject)
                self.assertEqual('end_date' in clean['cv_updates'][section][0], not should_reject)

    def test_unsupported_education_facts_remain_rejected_with_plain_language(self):
        response = empty_ai_response()
        response['cv_updates']['education'] = [{'degree': 'Bachelor of Computer Science'}]
        guarded = guard_extraction(response, 'I am currently studying', {})
        self.assertEqual(guarded['cv_updates']['education'], [{}])
        warning = guarded['_control']['evidence_warning']
        self.assertNotIn('education.degree', warning)
        self.assertIn('education details', warning)

    def test_naming_a_status_only_row_preserves_its_confirmed_graduation_month(self):
        old = [{'is_current': True, 'end_date': '2028-06'}]
        result = merge_collection_entries(old, [{'degree': 'BS Computer Science', 'end_date': '2028'}],
                                          'education', {'section': 'education', 'field': 'degree'})
        self.assertEqual(result[0]['end_date'], '2028-06')
        self.assertEqual(result[0]['degree'], 'BS Computer Science')
        self.assertEqual(old, [{'is_current': True, 'end_date': '2028-06'}])


class CurrentEducationJourneyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('current-education@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        provider = patch('chatbot.services.conversation_service.QwenClient.generate',
                         side_effect=AssertionError('Explicit study facts must not require a model guess'))
        provider.start(); self.addCleanup(provider.stop)

    def start(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Backend Developer', 'career_level': 'student', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {'personal': deepcopy(SAMPLE_CV['personal'])}
        state['personal_fields'] = dict.fromkeys(state['personal_fields'], 'collected')
        state['completed_sections'] = ['personal']
        session.conversation_state = state; session.current_section = 'education'; session.save()
        return session

    def send(self, session, message):
        result = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': message}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db()
        return result.data

    def test_reported_conversation_asks_only_for_missing_facts(self):
        session = self.start()
        result = self.send(session, 'I am currently studying')
        self.assertIn('Which degree or course are you studying?', result['assistant_message'])
        self.assertNotIn('confirm extracted', result['assistant_message'])
        self.assertNotIn('education.degree', result['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['education'], [{'is_current': True}])
        result = self.send(session, DEGREE)
        self.assertEqual(session.conversation_state['collected_data']['education'], [ENTRY])
        self.assertEqual(next_step(session.conversation_state), {'section': 'education', 'field': 'end_date'})
        self.assertIn('expect to graduate from HITEC University', result['assistant_message'])
        self.assertNotIn('Which institution', result['assistant_message'])
        result = self.send(session, 'I  excpect to graduate in 2028-06')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{**ENTRY, 'end_date': '2028-06'}])
        self.assertEqual(next_step(session.conversation_state)['section'], 'skills')
        self.assertNotEqual(result['intent'], 'clarify_information')

    def test_all_study_details_in_one_answer_skip_education_followups(self):
        session = self.start()
        result = self.send(session, DEGREE + ', expected graduation June 2028')
        self.assertEqual(result['section'], 'skills')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{**ENTRY, 'end_date': '2028-06'}])
        self.assertNotIn('start_date', session.conversation_state['collected_data']['education'][0])

    def test_institution_is_asked_in_present_tense_only_when_missing(self):
        session = self.start()
        result = self.send(session, 'I am studying BS Computer Science')
        self.assertIn('Which university or college are you studying at?', result['assistant_message'])
        self.send(session, 'HITEC University')
        self.assertEqual(len(session.conversation_state['collected_data']['education']), 1)
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')

    def test_invalid_month_preserves_facts_then_expected_date_recovers(self):
        session = self.start(); self.send(session, DEGREE)
        result = self.send(session, 'I excpect to graduate in 2028-13')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(session.conversation_state['collected_data']['education'], [ENTRY])
        result = self.send(session, 'excpect to graduate in 2028-06')
        self.assertEqual(result['section'], 'skills')
        self.assertNotIn('pending_field', session.conversation_state)

    def test_legacy_current_study_rejection_recovers_on_the_next_answer(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['education'] = [deepcopy(ENTRY)]
        state['education_fields'].update(degree='collected', institution='collected', field_of_study='collected')
        state['pending_field'] = {'section': 'education', 'field': 'end_date'}
        state['field_status'] = {'education.0.end_date': 'invalid'}
        session.conversation_state = state; session.save()
        result = self.send(session, 'I excpect to graduate in 2028-06')
        self.assertEqual(result['section'], 'skills')
        self.assertEqual(session.conversation_state['field_status']['education.0.end_date'], 'answered')

    def test_expected_graduation_survives_draft_and_explicit_save(self):
        session = self.start(); self.send(session, DEGREE + ', expected graduation 2028-06')
        for message in ['Python, Django', *['skip'] * 6, 'finish']:
            result = self.send(session, message)
        self.assertEqual(result['intent'], 'complete')
        draft = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        self.assertEqual(draft.status_code, 200, draft.data)
        education = draft.data['draft']['education'][0]
        self.assertEqual(education['end_date'], '2028-06')
        self.assertNotIn('is_current', education)  # Source-only; M10's education contract is unchanged.
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['education'], [education])

    def test_status_and_degree_turns_are_undoable(self):
        session = self.start(); self.send(session, 'I am currently studying')
        self.send(session, DEGREE)
        self.send(session, 'undo')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{'is_current': True}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'degree')

    def legacy_fragmented(self):
        session = self.start()
        named = {key: value for key, value in ENTRY.items() if key != 'is_current'}
        state = session.conversation_state
        state['collected_data']['education'] = [{'is_current': True}, deepcopy(named)]
        state['education_fields'].update(degree='collected', institution='collected', field_of_study='collected')
        state['pending_field'] = {'section': 'education', 'field': 'end_date'}
        session.conversation_state = state; session.save()
        for text, update in [('I am currently studying', {'is_current': True}), (DEGREE, named)]:
            ChatMessage.objects.create(session=session, role='user', content=text, section='education')
            ChatMessage.objects.create(session=session, role='assistant', content='Next question', section='education',
                                       intent='clarify_information', cv_updates={'education': [update]})
        return session

    def test_evidenced_legacy_status_fragment_recovers_on_date_retry(self):
        session = self.legacy_fragmented()
        result = self.send(session, 'I excpect to graduate in 2028-06')
        self.assertEqual(result['section'], 'skills')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{**ENTRY, 'end_date': '2028-06'}])
        self.send(session, 'undo')
        self.assertEqual(session.conversation_state['collected_data']['education'], [ENTRY])

    def test_status_repair_needs_history_and_respects_additional_degrees(self):
        session = self.legacy_fragmented()
        state = deepcopy(session.conversation_state)
        ChatMessage.objects.filter(session=session, role='user', content=DEGREE).delete()
        self.assertEqual(repair_study_status(session, state), state)
        session = self.legacy_fragmented()
        ChatMessage.objects.create(session=session, role='user', content='Add another degree', section='education')
        state = deepcopy(session.conversation_state)
        self.assertEqual(repair_study_status(session, state), state)

    def test_status_repair_preserves_named_rows_conflicts_and_saved_cv_editing(self):
        for change in ('named', 'conflict', 'editing', 'third'):
            session = self.legacy_fragmented()
            state = deepcopy(session.conversation_state)
            if change == 'named':
                state['collected_data']['education'][0]['degree'] = 'Diploma'
            elif change == 'conflict':
                state['collected_data']['education'][1]['is_current'] = False
            elif change == 'editing':
                state['mode'] = 'edit_existing'
            else:
                state['collected_data']['education'].append({'degree': 'MS'})
            with self.subTest(change=change):
                self.assertEqual(repair_study_status(session, state), state)
