"""Direct hostility must never become CV facts or advance a pending question."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.message_routing import classify
from chatbot.services.state_manager import get_required_conversation_step, CV_SECTIONS
from tests.test_m8 import SAMPLE_CV

PHRASES = ['o shutup', 'what a fuck', 'are you idiot']


class ConductClassificationTests(SimpleTestCase):
    def test_direct_abuse_variations(self):
        for text in PHRASES + ['OH, SHUT UP!', 'hey shut-up', 'please just shutup', 'are you an idiot?',
                                "you're an idiot", 'you are so stupid', 'r u dumb', 'what the fuck?',
                                'wtf', 'stfu', 'fuck you', 'idiot!', 'I will hurt you.']:
            with self.subTest(text=text): self.assertEqual(classify(text), 'inappropriate')

    def test_quotes_workplace_content_and_criticism_are_not_abuse(self):
        for text in ['I faced harassment at my previous workplace.', 'My manager said "shut up".',
                     'My boss asked "are you idiot"; should I mention that on my CV?',
                     '"Shut Up and Listen" is the title of my project.',
                     'I developed idiot-proof input validation.', 'This form is frustrating.',
                     'You misunderstood my answer.', 'I worked on a Fuck Cancer campaign.']:
            with self.subTest(text=text): self.assertNotEqual(classify(text), 'inappropriate')


class ConductConversationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('conduct@example.com')
        cls.other = get_user_model().objects.create_user('other-conduct@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.qwen_patch = patch('chatbot.services.conversation_service.QwenClient.generate',
                                side_effect=AssertionError('Clear abusive phrases must not call Qwen'))
        self.qwen = self.qwen_patch.start(); self.addCleanup(self.qwen_patch.stop)
        self.gemini_patch = patch('ai.llm.gemini_client.GeminiProvider.generate_structured',
                                  side_effect=AssertionError('No Gemini calls during chat'))
        self.gemini = self.gemini_patch.start(); self.addCleanup(self.gemini_patch.stop)

    def start(self, field='company'):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        state['collected_data']['experience'] = []
        state['completed_sections'] = ['personal', 'education', 'skills', 'projects', 'summary']
        state['missing_sections'] = ['experience']
        for group in ('personal_fields', 'education_fields', 'project_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        if field in ('role', 'responsibilities'):
            state['collected_data']['experience'] = [{'company': 'Example Company'}]
            state['experience_fields']['company'] = 'collected'
        if field == 'responsibilities':
            state['collected_data']['experience'][0]['role'] = 'Developer'
            state['experience_fields']['role'] = 'collected'
        state['current_section'] = 'experience'
        session.conversation_state = state; session.current_section = 'experience'; session.save()
        return session

    def send(self, session, message):
        response = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': message}, format='json')
        self.assertEqual(response.status_code, 200, response.data); session.refresh_from_db()
        return response.data

    def test_reported_messages_keep_same_question_and_data(self):
        session = self.start()
        data, fields = deepcopy(session.conversation_state['collected_data']), deepcopy(session.conversation_state['experience_fields'])
        for message in PHRASES:
            result = self.send(session, message)
            self.assertEqual(result['intent'], 'irrelevant')
            self.assertEqual(result['section'], 'experience')
            self.assertFalse(any(result['cv_updates'].values()))
            self.assertIn('professional', result['assistant_message'])
            self.assertEqual(get_required_conversation_step(session.conversation_state), {'section': 'experience', 'field': 'company'})
            self.assertEqual(session.conversation_state['collected_data'], data)
            self.assertEqual(session.conversation_state['experience_fields'], fields)
        self.qwen.assert_not_called(); self.gemini.assert_not_called()

    def test_abuse_is_blocked_at_company_role_and_responsibilities(self):
        for field in ('company', 'role', 'responsibilities'):
            for message in PHRASES:
                with self.subTest(field=field, message=message):
                    session = self.start(field)
                    before = deepcopy(session.conversation_state['collected_data'])
                    result = self.send(session, message)
                    self.assertEqual(result['intent'], 'irrelevant')
                    self.assertEqual(session.conversation_state['collected_data'], before)
                    self.assertEqual(get_required_conversation_step(session.conversation_state)['field'], field)

    def test_abuse_is_blocked_before_other_field_parsers(self):
        for section, field in [('personal', 'full_name'), ('education', 'degree'), ('projects', 'description'),
                               ('skills', 'skills'), ('certifications', 'certifications'), ('summary', 'summary')]:
            with self.subTest(section=section):
                session = self.start()
                session.conversation_state['pending_field'] = {'section': section, 'field': field}
                session.save()
                before = deepcopy(session.conversation_state['collected_data'])
                self.assertEqual(self.send(session, 'o shutup')['intent'], 'irrelevant')
                self.assertEqual(get_required_conversation_step(session.conversation_state), {'section': section, 'field': field})
                self.assertEqual(session.conversation_state['collected_data'], before)

    def test_legitimate_workplace_quote_can_be_collected(self):
        session = self.start('responsibilities')
        message = 'My manager said "shut up"; I documented workplace incidents.'
        self.qwen.side_effect = None
        self.qwen.return_value = {'assistant_message': '', 'intent': 'update_cv', 'section': 'experience',
            'state_updates': {}, 'cv_updates': {'experience': [{'responsibilities': [message]}]}, 'next_action': 'ask_question'}
        result = self.send(session, message)
        self.assertNotEqual(result['intent'], 'irrelevant')
        self.assertEqual(session.conversation_state['collected_data']['experience'][0]['responsibilities'], [message])

    def test_unrecognised_conversational_question_is_not_a_literal_job_field(self):
        session = self.start()
        self.qwen.side_effect = None
        self.qwen.return_value = {'assistant_message': '', 'intent': 'collect_information', 'section': 'experience',
            'state_updates': {}, 'cv_updates': {}, 'next_action': 'ask_question'}
        for message in ['are you even listening', 'you are a fool', 'your questions are confusing']:
            self.send(session, message)
        self.assertEqual(session.conversation_state['collected_data']['experience'], [])
        self.assertEqual(get_required_conversation_step(session.conversation_state)['field'], 'company')
        self.assertEqual(self.qwen.call_count, 3)

    def test_saved_cv_edit_mode_does_not_accept_hostile_job_details(self):
        from cvs.services import create_cv
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': SAMPLE_CV})
        session = create_chat_session(user=self.user, cv_id=cv.id)
        self.send(session, 'add a job')
        before = deepcopy(session.conversation_state['edit_updates'])
        for message in PHRASES:
            result = self.send(session, message)
            self.assertEqual(result['intent'], 'irrelevant')
            self.assertEqual(session.conversation_state['edit_updates'], before)
            self.assertEqual(get_required_conversation_step(session.conversation_state), {'section': 'experience', 'field': 'company'})
        cv.refresh_from_db(); self.assertEqual(cv.version, 1)
        self.qwen.assert_not_called()

    def test_fresher_can_skip_after_hostility_without_saving_fake_experience(self):
        session = self.start()
        for message in PHRASES + ['no experience', 'skip', 'skip', 'skip', 'finish']:
            result = self.send(session, message)
        self.assertEqual(result['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['experience'], [])
        self.qwen.assert_not_called(); self.gemini.assert_not_called()

    def contaminated(self, *, history=True):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['experience'] = [{'company': PHRASES[0], 'role': PHRASES[1], 'responsibilities': [PHRASES[2]]}]
        state['experience_fields'].update(company='collected', role='collected', responsibilities='collected')
        state['field_status'] = {f'experience.0.{field}': 'answered' for field in ('company', 'role', 'responsibilities')}
        state['completed_sections'].append('experience'); state['missing_sections'] = []
        state['current_section'] = 'certifications'
        state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.current_section = 'certifications'; session.save()
        if history:
            for field, message in zip(('company', 'role', 'responsibilities'), PHRASES):
                ChatMessage.objects.create(session=session, role='user', content=message)
                ChatMessage.objects.create(session=session, role='assistant', content='Next question',
                    intent='update_cv', section='experience', next_action='ask_question',
                    cv_updates={'experience': [{field: [message] if field == 'responsibilities' else message}]})
        return session

    def test_resume_repairs_only_history_confirmed_bad_experience(self):
        session = self.contaminated()
        personal, projects = deepcopy(session.conversation_state['collected_data']['personal']), deepcopy(session.conversation_state['collected_data']['projects'])
        response = self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db(); state = session.conversation_state
        self.assertEqual(state['collected_data']['experience'], [])
        self.assertEqual(state['undo_state']['collected_data']['experience'], [])
        self.assertEqual(state['collected_data']['personal'], personal)
        self.assertEqual(state['collected_data']['projects'], projects)
        self.assertEqual(get_required_conversation_step(state), {'section': 'experience', 'field': 'company'})
        self.assertIn('experience', state['missing_sections'])
        self.assertNotIn('experience', state['completed_sections'])
        self.assertFalse(any(path.startswith('experience.') for path in state['field_status']))
        count = session.messages.count()
        self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(session.messages.count(), count)
        self.assertIn('earlier non-CV messages', response.data['messages'][-1]['content'])

    def test_resume_does_not_repair_without_history_or_for_another_owner(self):
        session = self.contaminated(history=False)
        before = deepcopy(session.conversation_state)
        self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
        self.assertEqual(session.conversation_state, before)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.id}/').status_code, 404)

    def test_stale_timestamp_cannot_overwrite_repaired_state(self):
        session = self.contaminated(); timestamp = session.updated_at.isoformat()
        self.client.get(f'/api/chat/sessions/{session.id}/')
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/',
            {'message': 'o shutup', 'expected_updated_at': timestamp}, format='json')
        self.assertEqual(result.status_code, 409)
        session.refresh_from_db(); self.assertEqual(session.conversation_state['collected_data']['experience'], [])
