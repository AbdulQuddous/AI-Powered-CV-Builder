"""Explicit saved-CV corrections replace old prompts before using their context."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.edit_controls import TRANSIENT
from chatbot.services.question_engine import next_step
from cvs.services import create_cv
from tests.test_m8 import SAMPLE_CV


class EditContextSwitchingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('edit-context@example.test')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.document = deepcopy(SAMPLE_CV)
        self.document['meta']['career_level'] = 'experienced'
        self.document['languages'] = [{'name': 'Urdu', 'proficiency': ''}]
        self.document['experience'] = [{
            'company': 'Example Systems', 'job_title': 'Developer Intern', 'location': '',
            'start_date': '2025-01', 'end_date': '', 'is_current': True,
            'highlights': ['Built confirmed Python features.'],
        }]
        self.cv = create_cv(user=self.user, values={'name': 'Synthetic context CV', 'data': self.document})
        self.qwen = patch('chatbot.services.conversation_service.QwenClient.generate',
                          side_effect=AssertionError('Deterministic corrections need no provider')).start()
        self.addCleanup(patch.stopall)
        patch('ai.llm.gemini_client.GeminiProvider.generate_structured',
              side_effect=AssertionError('Corrections do not call Gemini')).start()

    def start(self, stale=True):
        session = create_chat_session(user=self.user, cv_id=self.cv.pk)
        if stale:
            state = session.conversation_state
            state.update(
                pending_field={'section': 'projects', 'field': 'description', 'index': 99},
                pending_selection={'section': 'education', 'field': 'institution'},
                date_confirmation_pending={'section': 'education', 'field': 'end_date', 'index': 99, 'year': '2028'},
                language_proficiency_pending=['Urdu'],
                optional_entry_confirmation={'section': 'certifications', 'entries': [{'name': 't33ssr'}]},
                edit_focus='languages', edit_operation='add', edit_draft=[{'name': 'Old unconfirmed entry'}],
            )
            state['edit_updates']['skills'] = ['Git']
            session.save(update_fields=['conversation_state'])
        return session

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        self.assertEqual(set(response.data), {'assistant_message', 'intent', 'section', 'cv_updates', 'next_action'})
        return response.data

    def draft(self, session):
        response = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['draft']

    def assert_review(self, session):
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        for key in TRANSIENT:
            self.assertFalse(session.conversation_state.get(key), key)
        self.cv.refresh_from_db()
        self.assertEqual((self.cv.data, self.cv.version), (self.document, 1))
        self.qwen.assert_not_called()

    def test_inline_email_correction_replaces_every_stale_prompt_and_keeps_accepted_edits(self):
        session = self.start()
        result = self.send(session, 'change my email to corrected@example.test')
        self.assertEqual(result['section'], 'review')
        self.assertEqual(self.draft(session)['personal']['email'], 'corrected@example.test')
        self.assertIn('Git', session.conversation_state['edit_updates']['skills'])
        self.assertFalse(session.conversation_state['edit_updates'].get('certifications'))
        self.assert_review(session)

    def test_scalar_request_without_value_asks_only_for_the_requested_value(self):
        session = self.start()
        result = self.send(session, 'change my email')
        self.assertEqual(result['section'], 'personal')
        self.assertEqual(next_step(session.conversation_state), {'section': 'personal', 'field': 'email'})
        self.assertNotIn('language_proficiency_pending', session.conversation_state)
        self.send(session, 'corrected@example.test')
        self.assertEqual(self.draft(session)['personal']['email'], 'corrected@example.test')
        self.assert_review(session)

    def test_invalid_scalar_value_retains_new_field_instead_of_resuming_old_prompt(self):
        session = self.start()
        result = self.send(session, 'change my email to incomplete-address')
        self.assertEqual(result['section'], 'personal')
        self.assertEqual(next_step(session.conversation_state)['field'], 'email')
        self.assertNotIn('specify language proficiency', result['assistant_message'])
        self.assertEqual(self.draft(session)['personal']['email'], self.document['personal']['email'])
        self.send(session, 'corrected@example.test')
        self.assert_review(session)

    def test_summary_correction_does_not_resume_language_proficiency(self):
        session = self.start()
        summary = 'Develops confirmed Python web applications and tests API behavior.'
        self.send(session, 'change my summary to ' + summary)
        self.assertEqual(self.draft(session)['summary'], summary)
        self.assert_review(session)

    def test_entry_patch_uses_new_explicit_index_instead_of_stale_project_index(self):
        session = self.start()
        self.send(session, 'change my project description to Tracks confirmed application details.')
        data = self.draft(session)
        self.assertEqual(data['projects'][0]['description'], 'Tracks confirmed application details.')
        patch = session.conversation_state['entry_patches'][0]
        self.assertEqual((patch['section'], patch['index']), ('projects', 0))
        self.assertEqual(data['experience'], self.document['experience'])
        self.assert_review(session)

    def test_entry_request_and_followup_preserve_the_requested_target(self):
        session = self.start()
        self.send(session, 'change my job title')
        self.assertEqual(next_step(session.conversation_state), {'section': 'experience', 'field': 'role', 'index': 0})
        self.send(session, 'Backend Developer')
        self.assertEqual(self.draft(session)['experience'][0]['job_title'], 'Backend Developer')
        self.assert_review(session)

    def test_multiple_entries_need_a_fresh_selection_in_the_requested_section(self):
        self.document['projects'].append(dict(deepcopy(self.document['projects'][0]), name='Second Project'))
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=['data'])
        session = self.start()
        result = self.send(session, 'change my project description')
        self.assertEqual(result['section'], 'projects')
        self.assertEqual(next_step(session.conversation_state), {'section': 'projects', 'field': 'select_entry'})
        self.send(session, '2')
        self.assertEqual(next_step(session.conversation_state)['index'], 1)
        self.send(session, 'Tracks confirmed interview notes.')
        data = self.draft(session)
        self.assertEqual(data['projects'][0], self.document['projects'][0])
        self.assertEqual(data['projects'][1]['description'], 'Tracks confirmed interview notes.')
        self.assert_review(session)

    def test_missing_entry_does_not_keep_a_stale_target_or_invent_one(self):
        self.document['education'] = []
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=['data'])
        session = self.start()
        result = self.send(session, 'change my university to Another University')
        self.assertIn('no saved entry', result['assistant_message'].lower())
        self.assertEqual(self.draft(session)['education'], [])
        self.assert_review(session)

    def test_inline_skill_add_and_remove_do_not_resurface_an_old_followup(self):
        for command in ('add Django to my skills', 'remove Python from my skills'):
            with self.subTest(command=command):
                session = self.start()
                self.send(session, command)
                data = self.draft(session)
                if command.startswith('add'):
                    self.assertIn('Django', data['skills'])
                else:
                    self.assertNotIn('Python', data['skills'])
                self.assert_review(session)

    def test_career_level_correction_replaces_old_prompt_without_inventing_experience(self):
        session = self.start()
        self.send(session, 'change my career level to senior')
        self.assertEqual(session.conversation_state['question_profile'], 'senior')
        self.assertEqual(self.draft(session)['experience'], self.document['experience'])
        self.assert_review(session)

    def test_model_output_cannot_authorize_the_private_context_switch(self):
        session = self.start(stale=False)
        state = session.conversation_state
        state['language_proficiency_pending'] = ['Urdu']
        session.save(update_fields=['conversation_state'])
        response = empty_ai_response()
        response['_control'] = {'_edit_switch': {'section': 'personal', 'field': 'email'}}
        self.qwen.side_effect = None
        self.qwen.return_value = response
        self.send(session, 'I am thinking about something else')
        self.assertEqual(next_step(session.conversation_state), {'section': 'languages', 'field': 'proficiency'})
        self.assertNotIn('pending_field', session.conversation_state)
        self.qwen.assert_called_once()

    def test_initial_interview_inline_correction_keeps_required_interview_progress(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Backend Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        self.send(session, 'change my email to corrected@example.test')
        self.assertEqual(session.conversation_state['collected_data']['personal']['email'], 'corrected@example.test')
        self.assertEqual(next_step(session.conversation_state), {'section': 'personal', 'field': 'full_name'})
        self.assertEqual(session.status, ChatSession.Status.ACTIVE)

    def test_targeted_entry_advice_is_available_but_normal_edit_and_progress_stay_concise(self):
        session = self.start(stale=False)
        entered = self.send(session, 'add skills')
        self.assertIn('8–15', entered['assistant_message'])
        self.assertIn('Candidate skills', entered['assistant_message'])
        accepted = self.send(session, 'Docker')
        self.assertNotIn('One or two pages', accepted['assistant_message'])
        self.assertNotIn('Candidate skills', accepted['assistant_message'])
        progress = self.send(session, 'show collected information')
        self.assertIn('Docker', progress['assistant_message'])
        self.assertNotIn('Candidate skills', progress['assistant_message'])
