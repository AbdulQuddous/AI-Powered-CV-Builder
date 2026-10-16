"""Regressions from the language/summary/certificate interview transcript."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.question_engine import next_step
from chatbot.services.section_answers import parse_languages
from chatbot.services.state_manager import CV_SECTIONS
from tests.test_m8 import SAMPLE_CV

SUMMARY = ('Software Engineering graduate and Python Developer Intern with hands-on experience '
           'developing Python and Django web applications, REST APIs, and AI-integrated features. '
           'Strong foundation in Object-Oriented Programming (OOP), Data Structures and Algorithms '
           '(DSA), relational databases, SQL, and HTTP APIs. Experienced in debugging, API testing, '
           'Git-based version control, and collaborating on software projects.')
COMBINED = 'keep these  unspecified and summary is ' + SUMMARY


class LanguageParsingTests(SimpleTestCase):
    def test_space_separated_and_compound_names(self):
        for text, names in [
            ('English urdu Hindi', ['English', 'Urdu', 'Hindi']),
            ('english, urdu and Hindi', ['English', 'Urdu', 'Hindi']),
            ('American Sign Language English', ['American Sign Language', 'English']),
            ('Brazilian Portuguese; Mandarin Chinese', ['Brazilian Portuguese', 'Mandarin Chinese']),
            ('New Zealand Sign Language', ['New Zealand Sign Language']),
        ]:
            with self.subTest(text=text):
                self.assertEqual(parse_languages(text), [{'name': name} for name in names])


class OptionalSectionConversationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('optional@example.com')
        cls.other = get_user_model().objects.create_user('other-optional@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        for target in ['chatbot.services.conversation_service.QwenClient.generate',
                       'ai.llm.gemini_client.GeminiProvider.generate_structured']:
            mocked = patch(target, side_effect=AssertionError('Explicit interview answers must stay local'))
            mocked.start(); self.addCleanup(mocked.stop)

    def start(self, *, review=False):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        for key in ('certifications', 'languages', 'achievements'):
            state['collected_data'][key] = []
        state['completed_sections'] = ['personal', 'education', 'skills', 'projects', 'experience']
        state['skipped_sections'] = ['certifications']
        if review:
            state['completed_sections'].append('summary')
            state['skipped_sections'] += ['achievements', 'languages']
        else:
            state['collected_data']['summary'] = ''
        state['missing_sections'] = []
        for group in ('personal_fields', 'education_fields', 'project_fields', 'experience_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        session.conversation_state = state
        session.current_section = next_step(state)['section']; session.save()
        return session

    def send(self, session, message):
        response = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': message}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        return response.data

    def language_step(self):
        session = self.start()
        self.assertEqual(self.send(session, 'skip')['section'], 'languages')
        return session

    def test_exact_transcript_collects_clean_summary_and_certificate_then_saves(self):
        session = self.language_step()
        result = self.send(session, 'English urdu Hindi')
        self.assertEqual(next_step(session.conversation_state), {'section': 'languages', 'field': 'proficiency'})
        self.assertEqual(result['assistant_message'].count('?'), 1)
        self.assertNotIn('summary', result['assistant_message'])
        self.assertEqual(self.send(session, COMBINED)['section'], 'review')
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)
        self.assertEqual(self.send(session, 'i wan to add certificate')['section'], 'certifications')
        self.assertEqual(self.send(session, 'Python Certificate')['section'], 'review')
        self.assertEqual(self.send(session, 'fnish')['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        data = saved.data['cv']['data']
        self.assertEqual(data['summary'], SUMMARY)
        self.assertEqual(data['languages'], [{'name': name, 'proficiency': ''} for name in ['English', 'Urdu', 'Hindi']])
        self.assertEqual(data['certifications'][0]['name'], 'Python Certificate')

    def test_proficiency_reply_gets_its_own_turn_before_summary(self):
        session = self.language_step()
        self.send(session, 'English urdu')
        result = self.send(session, 'English professional, Urdu native')
        self.assertEqual(result['section'], 'summary')
        self.assertNotIn('proficiency', result['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['languages'], [
            {'name': 'English', 'proficiency': 'professional'}, {'name': 'Urdu', 'proficiency': 'native'}])
        self.send(session, SUMMARY)
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)

    def test_skipping_proficiency_keeps_names_and_does_not_skip_summary(self):
        for answer in ['skip', 'keep these unspecified', 'unspecified', 'no']:
            with self.subTest(answer=answer):
                session = self.language_step(); self.send(session, 'English Urdu')
                self.assertEqual(self.send(session, answer)['section'], 'summary')
                self.assertEqual(len(session.conversation_state['collected_data']['languages']), 2)
                self.assertNotIn('languages', session.conversation_state['skipped_sections'])

    def test_labelled_summary_is_clean_even_at_summary_step(self):
        session = self.language_step(); self.send(session, 'skip')
        self.send(session, COMBINED)
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)

    def test_partial_proficiency_keeps_remaining_language_pending(self):
        session = self.language_step(); self.send(session, 'English Urdu')
        self.send(session, 'English professional')
        self.assertEqual(session.conversation_state['language_proficiency_pending'], ['Urdu'])
        self.assertEqual(self.send(session, 'keep it unspecified')['section'], 'summary')

    def test_certificate_requests_reopen_skipped_section_without_becoming_facts(self):
        for message in ['i want to add certificate', 'i wan to add certificate', 'add a certification',
                        'Can I add a certificate?', 'please add another certificate', 'add cetificate to my cv']:
            with self.subTest(message=message):
                session = self.start(review=True)
                before = deepcopy(session.conversation_state['collected_data'])
                self.assertEqual(self.send(session, message)['section'], 'certifications')
                self.assertEqual(session.conversation_state['collected_data'], before)
                self.send(session, 'Python Certificate')
                self.assertNotIn('certifications', session.conversation_state['skipped_sections'])
                self.assertEqual(self.send(session, 'add another certificate')['section'], 'certifications')
                self.assertEqual(self.send(session, 'Django Certificate')['section'], 'review')
                self.assertEqual(len(session.conversation_state['collected_data']['certifications']), 2)

    def test_finish_typo_cannot_bypass_required_fields(self):
        session = create_chat_session(user=self.user)
        self.assertEqual(self.send(session, 'fnish')['next_action'], 'ask_question')
        self.assertEqual(session.status, 'active')

    def test_finish_can_leave_only_optional_proficiency_unspecified(self):
        session = self.start(review=True)
        self.send(session, 'add languages'); self.send(session, 'English Urdu')
        self.assertEqual(self.send(session, 'finsh!')['next_action'], 'complete')

    def test_existing_cv_edit_accepts_certificate_and_language_requests(self):
        from cvs.services import create_cv
        cv = create_cv(user=self.user, values={'name': 'Saved', 'data': SAMPLE_CV})
        session = create_chat_session(user=self.user, cv_id=cv.id)
        self.assertEqual(self.send(session, 'i want to add certificate')['section'], 'certifications')
        self.send(session, 'Python Certificate')
        self.send(session, 'add languages'); self.send(session, 'English Urdu')
        self.assertEqual(next_step(session.conversation_state)['field'], 'proficiency')
        self.assertEqual(self.send(session, 'keep these unspecified')['section'], 'review')
        self.assertEqual(self.send(session, 'fnish')['next_action'], 'complete')
        cv.refresh_from_db(); self.assertEqual(cv.version, 1)

    def contaminated(self, *, history=True):
        session = self.start(review=True)
        state = session.conversation_state
        state['collected_data']['languages'] = [{'name': 'English urdu Hindi'}]
        state['collected_data']['summary'] = COMBINED
        state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.status = 'completed'; session.save()
        if history:
            for text in ['English urdu Hindi', COMBINED]:
                ChatMessage.objects.create(session=session, role='user', content=text)
        return session

    def test_resume_repairs_evidenced_unsaved_completed_draft_and_allows_certificate(self):
        session = self.contaminated()
        self.client.get(f'/api/chat/sessions/{session.id}/')
        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)
        self.assertEqual(len(session.conversation_state['undo_state']['collected_data']['languages']), 3)
        self.assertEqual(self.client.post(f'/api/chat/sessions/{session.id}/reopen/').status_code, 200)
        self.send(session, 'i want to add certificate')
        self.assertEqual(self.send(session, 'Python Certificate')['section'], 'review')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_repair_requires_history_and_ownership_and_leaves_saved_sessions_unchanged(self):
        session = self.contaminated(history=False)
        before = deepcopy(session.conversation_state)
        self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
        self.assertEqual(session.conversation_state, before)
        session = self.contaminated(); before = deepcopy(session.conversation_state)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.id}/').status_code, 404)
        self.client.force_authenticate(self.user)
        session.conversation_state['chat_saved_cv_id'] = 'saved'; session.save()
        self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
        self.assertEqual(session.conversation_state['collected_data'], before['collected_data'])

    def test_draft_endpoint_also_recovers_before_preview(self):
        session = self.contaminated()
        response = self.client.get(f'/api/chat/sessions/{session.id}/draft/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['draft']['summary'], SUMMARY)
        self.assertEqual(len(response.data['draft']['languages']), 3)
