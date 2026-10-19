"""Reported graduation precision loop, paired corrections and safe recovery."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.date_recovery import repair_date_state
from chatbot.services.education_answers import parse_education, reversed_date_range
from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.message_routing import empty_ai_response
from tests.test_m8 import SAMPLE_CV

ANSWER = 'I sompleted bs software engineering from university of mianwali in 2026'
PAIR = 'starting date 2022-09 ending date 2026-06'
ENTRY = {'degree': 'bs software engineering', 'institution': 'university of mianwali',
         'field_of_study': 'software engineering'}


def evidence(text, values):
    return [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': 'Accepted',
            'intent': 'collect_information', 'cv_updates': {'education': [values] if values else []}}]


def old_state(start='2022-09', end='2026'):
    return {'collected_data': {'education': [{**ENTRY, 'start_date': start, 'end_date': end}]},
            'date_confirmation_pending': {'section': 'education', 'index': 0, 'field': 'end_date', 'year': '2026'}}


class DateEvidenceTests(SimpleTestCase):
    def test_unknown_month_cannot_create_a_false_inversion(self):
        for start, end, invalid in [('2026-04', '2026', False), ('2026', '2026-04', False),
                                    ('2026', '2026', False), ('2022-09', '2026-06', False),
                                    ('2026-09', '2026-06', True), ('2027', '2026', True),
                                    ('2027-01', '2026', True), ('2026', '2025-12', True)]:
            with self.subTest(start=start, end=end):
                self.assertEqual(reversed_date_range(start, end), invalid)

    def test_reported_typo_keeps_grouped_facts_and_only_the_stated_year(self):
        self.assertEqual(parse_education(ANSWER), {**ENTRY, 'end_date': '2026'})

    def test_qwen_cannot_duplicate_a_completion_year_into_the_start(self):
        response = empty_ai_response()
        response['cv_updates']['education'] = [{**ENTRY, 'start_date': '2026', 'end_date': '2026'}]
        guarded = guard_extraction(response, ANSWER, {})
        self.assertNotIn('start_date', guarded['cv_updates']['education'][0])
        self.assertEqual(guarded['cv_updates']['education'][0]['end_date'], '2026')

    def test_history_restores_a_discarded_endpoint_once(self):
        state = old_state()
        history = evidence(PAIR, {**ENTRY, 'start_date': '2022-09'})
        self.assertTrue(repair_date_state(state, history))
        self.assertEqual(state['collected_data']['education'][0]['end_date'], '2026-06')
        self.assertNotIn('date_confirmation_pending', state)
        self.assertFalse(repair_date_state(state, history))

    def test_history_removes_a_proven_fabricated_start_year(self):
        state = old_state('2026')
        self.assertTrue(repair_date_state(state, evidence(ANSWER, {**ENTRY, 'start_date': '2026', 'end_date': '2026'})))
        self.assertNotIn('start_date', state['collected_data']['education'][0])
        self.assertEqual(state['collected_data']['education'][0]['end_date'], '2026')

    def test_later_user_intent_and_multiple_qualifications_block_recovery(self):
        for later in ['omit', 'skip this date', 'change the graduation date', 'end date 2026-08',
                      'add another degree']:
            state = old_state(); before = deepcopy(state)
            history = evidence(PAIR, {**ENTRY, 'start_date': '2022-09'}) + evidence(later, {})
            with self.subTest(later=later):
                self.assertFalse(repair_date_state(state, history))
                self.assertEqual(state, before)
        state = old_state(); state['collected_data']['education'].append({'degree': 'MS'})
        self.assertFalse(repair_date_state(state, evidence(PAIR, {'start_date': '2022-09'})))

    def test_no_proof_or_current_full_date_is_never_overwritten(self):
        state = old_state()
        self.assertFalse(repair_date_state(state, evidence(PAIR, {})))
        state = old_state(end='2026-12')
        self.assertFalse(repair_date_state(state, evidence(PAIR, {'start_date': '2022-09'})))
        self.assertEqual(state['collected_data']['education'][0]['end_date'], '2026-12')


class DateFollowupJourneyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('date-followup@example.com')
        cls.other = get_user_model().objects.create_user('date-followup-other@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('Explicit date answers need no provider'))
        mocked.start(); self.addCleanup(mocked.stop)

    def start(self, start='2026', end='2026'):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Frontend Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = deepcopy(SAMPLE_CV)
        state['collected_data']['education'] = [{**ENTRY, 'start_date': start, 'end_date': end}]
        state['completed_sections'] = ['personal', 'experience', 'skills', 'education', 'projects',
                                       'certifications', 'achievements', 'languages', 'summary']
        for key in ('personal_fields', 'experience_fields', 'education_fields', 'project_fields'):
            state[key] = dict.fromkeys(state[key], 'collected')
        session.conversation_state = state; session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db()
        return result.data

    def test_raw_start_month_does_not_conflict_with_an_unknown_end_month(self):
        session = self.start(); self.send(session, 'finish')
        self.assertNotEqual(self.send(session, '2026-04')['intent'], 'clarify_information')
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['start_date'], '2026-04')
        self.send(session, 'finish'); self.send(session, '2026-06')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_paired_correction_saves_both_endpoints_and_finishes(self):
        session = self.start(); self.send(session, 'finish'); self.send(session, PAIR)
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual((entry['start_date'], entry['end_date']), ('2022-09', '2026-06'))
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['education'][0]['end_date'], '2026-06')

    def test_partial_pair_retains_the_complete_sibling_and_new_year(self):
        session = self.start(); self.send(session, 'finish')
        self.send(session, 'start date 2022 end date 2026-06')
        state = session.conversation_state
        self.assertEqual(state['collected_data']['education'][0]['end_date'], '2026-06')
        self.assertEqual(state['date_confirmation_pending']['year'], '2022')
        self.send(session, '2022-09')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_real_inversion_is_rejected_then_paired_retry_works(self):
        session = self.start(); self.send(session, 'finish')
        self.assertEqual(self.send(session, 'start date 2027-09 end date 2026-06')['intent'], 'clarify_information')
        self.send(session, PAIR)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_short_omission_skips_only_the_date_and_preserves_education(self):
        for answer in ('omit', 'skip', 'leave it blank'):
            session = self.start(start='2022-09'); self.send(session, 'finish')
            self.send(session, answer)
            with self.subTest(answer=answer):
                self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
                draft = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
                self.assertEqual(draft.data['draft']['education'][0]['degree'], ENTRY['degree'])
                self.assertEqual(draft.data['draft']['education'][0]['end_date'], '')

    def test_resume_repairs_the_draft_and_undo_and_explains_it_only_once(self):
        session = self.start(start='2022-09'); self.send(session, 'finish')
        state = session.conversation_state; state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.save()
        for message in evidence(PAIR, {**ENTRY, 'start_date': '2022-09'}):
            ChatMessage.objects.create(session=session, **message)
        for _ in range(2):
            reply = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
            self.assertEqual(reply.status_code, 200, reply.data)
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], '2026-06')
        self.assertEqual(session.conversation_state['undo_state']['collected_data']['education'][0]['end_date'], '2026-06')
        self.assertEqual(session.messages.filter(content__startswith='I recovered the dates').count(), 1)

    def test_recovery_is_owner_scoped_and_does_not_rewrite_saved_drafts(self):
        session = self.start(start='2022-09'); self.send(session, 'finish')
        for message in evidence(PAIR, {**ENTRY, 'start_date': '2022-09'}):
            ChatMessage.objects.create(session=session, **message)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.pk}/draft/').status_code, 404)
        self.client.force_authenticate(self.user)
        session.conversation_state['chat_saved_cv_id'] = 'already-saved'; session.save()
        self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], '2026')
