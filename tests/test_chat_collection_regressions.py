"""Regressions for sequential interview answers and already-split education state."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.state_manager import get_required_conversation_step
from cvs.chat_import import build_chat_document


class SequentialCollectionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('sequential@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.provider_patch = patch('chatbot.services.conversation_service.QwenClient.generate',
                                    side_effect=AssertionError('Straightforward followups must stay local'))
        self.provider = self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)

    def start(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Developer', 'career_level': 'fresher'})
        for text in ['My full name is abdul quddous', 'ssss.com', 'shuja@example.com',
                     'frasrf', '03001234567', 'Islamabad', 'skip', 'abdul.github.com', 'skip', 'skip']:
            self.send(session, text)
        self.assertEqual(get_required_conversation_step(session.conversation_state),
                         {'section': 'education', 'field': 'degree'})
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db()
        return result.data

    def test_separate_degree_and_institution_complete_one_entry(self):
        session = self.start()
        for text in ['BS software engineering', 'university of MIanwali']:
            result = self.send(session, text)
            self.assertNotEqual(result['intent'], 'clarify_information', result)
        self.assertEqual(session.conversation_state['collected_data']['education'], [{
            'degree': 'BS software engineering', 'institution': 'university of MIanwali',
            'field_of_study': 'software engineering'}])
        invalid = self.send(session, 'graduate')
        self.assertEqual(invalid['intent'], 'clarify_information')
        self.assertEqual(get_required_conversation_step(session.conversation_state)['field'], 'end_date')
        result = self.send(session, '2022-06')
        self.assertEqual(result['section'], 'skills')
        document, _ = build_chat_document(session)
        self.assertEqual(len(document['education']), 1)
        self.assertEqual(document['education'][0]['end_date'], '2022-06')
        self.assertEqual(document['education'][0]['institution'], 'university of MIanwali')
        self.provider.assert_not_called()

    def test_graduation_year_and_simple_sentences_stay_local(self):
        for answer, expected in [('2026', '2026'), ('i am graduated in 2026', '2026'),
                                 ('i graduate in 2026-06', '2026-06'), ('I graduated in 2026.', '2026')]:
            with self.subTest(answer=answer):
                session = self.start()
                for text in ['BS software engineering', 'university of MIanwali']:
                    self.send(session, text)
                result = self.send(session, answer)
                self.assertEqual(result['section'], 'skills')
                self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], expected)
        self.provider.assert_not_called()

    def test_company_and_job_title_followups_complete_one_experience(self):
        session = self.start()
        state = session.conversation_state
        state['pending_field'] = {'section': 'experience', 'field': 'company'}
        session.conversation_state = state
        session.save()
        self.send(session, 'Example Company')
        session.conversation_state['pending_field'] = {'section': 'experience', 'field': 'role'}
        session.save()
        self.send(session, 'Backend Developer')
        session.conversation_state['pending_field'] = {'section': 'experience', 'field': 'responsibilities'}
        session.save()
        self.send(session, 'Maintained APIs')
        self.assertEqual(session.conversation_state['collected_data']['experience'], [{
            'company': 'Example Company', 'role': 'Backend Developer', 'responsibilities': ['Maintained APIs']}])

    def broken_session(self, *, explicit_second=False, grouped=False):
        session = self.start()
        fragments = [{'degree': 'BS software engineering'}, {'institution': 'university of MIanwali'}]
        state = session.conversation_state
        state['collected_data']['education'] = deepcopy(fragments)
        state['education_fields'].update(degree='collected', institution='collected',
                                         field_of_study='collected', end_date='missing')
        state['pending_field'] = {'section': 'education', 'field': 'end_date'}
        session.conversation_state = state
        session.save()
        if grouped:
            ChatMessage.objects.create(session=session, role='assistant', content='Collected',
                                       cv_updates={'education': fragments})
        else:
            for index, fragment in enumerate(fragments):
                if explicit_second and index:
                    ChatMessage.objects.create(session=session, role='user', content='Add another degree')
                ChatMessage.objects.create(session=session, role='assistant', content='Collected',
                                           cv_updates={'education': [fragment]})
        return session

    def test_existing_split_session_recovers_without_restarting(self):
        session = self.broken_session()
        result = self.send(session, '2026-06')
        self.assertNotEqual(result['intent'], 'clarify_information', result)
        self.assertEqual(session.conversation_state['collected_data']['education'], [{
            'degree': 'BS software engineering', 'institution': 'university of MIanwali', 'end_date': '2026-06'}])
        # The old failed merge falsely marked this field collected; ask for it once.
        self.assertEqual(get_required_conversation_step(session.conversation_state)['field'], 'field_of_study')
        self.assertEqual(self.send(session, 'SOftware engineerig')['section'], 'skills')
        self.assertEqual(session.conversation_state['collected_data']['personal']['full_name'], 'abdul quddous')
        self.provider.assert_not_called()

    def test_repair_does_not_merge_explicitly_separate_or_grouped_entries(self):
        for options in [{'explicit_second': True}, {'grouped': True}]:
            with self.subTest(options=options):
                session = self.broken_session(**options)
                before = deepcopy(session.conversation_state['collected_data']['education'])
                result = self.send(session, '2026-06')
                self.assertEqual(result['intent'], 'clarify_information')
                self.assertEqual(session.conversation_state['collected_data']['education'], before)
                self.assertEqual(get_required_conversation_step(session.conversation_state)['field'], 'end_date')
                self.assertIn('education', session.conversation_state['missing_sections'])

    def test_ambiguous_merge_does_not_advance_progress(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['education'] = [{'degree': 'BS'}, {'degree': 'MS'}]
        state['education_fields']['degree'] = 'collected'
        session.conversation_state = state
        session.save()
        before = deepcopy(state['education_fields'])
        result = self.send(session, 'Example University')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(session.conversation_state['education_fields'], before)
        self.assertEqual(session.conversation_state['collected_data']['education'], [{'degree': 'BS'}, {'degree': 'MS'}])
