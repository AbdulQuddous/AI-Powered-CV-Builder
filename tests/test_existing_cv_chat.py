from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage, ChatSession
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.existing_cv_conversation import INTRO
from chatbot.services.prompt_builder import build_messages
from chatbot.services.state_manager import get_initial_state
from cvs.models import CVVersion
from cvs.services import create_cv, update_cv
from cvs.validation import build_document


class ExistingCVChatTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('editchat@example.com', 'Strong-password-123!')
        self.other = get_user_model().objects.create_user('foreignchat@example.com', 'Strong-password-123!')
        self.client.force_authenticate(self.user)
        self.document = build_document({'target_role': 'Backend Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        self.document['personal'].update(full_name='Ali Khan', email='ali@example.com', location='Lahore')
        self.document['skills'] = ['Python']
        self.document['projects'] = [{'name': 'Saved Project', 'description': 'An existing project.', 'technologies': ['Python'], 'url': '', 'highlights': []}]
        self.cv = create_cv(user=self.user, values={'name': 'Ali CV', 'data': self.document})

    def start(self, cv_id=None):
        response = self.client.post('/api/chat/sessions/', {'cv_id': self.cv.id if cv_id is None else cv_id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ChatSession.objects.get(pk=response.data['id']), response.data

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def extracted(self, section, value):
        response = empty_ai_response()
        response['section'] = section
        response['cv_updates'][section] = value
        return response

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_populated_cv_starts_with_edit_request_and_known_context(self, gemini):
        session, data = self.start()
        self.assertEqual(data['assistant_message'], INTRO)
        self.assertEqual(session.conversation_state['mode'], 'edit_existing')
        self.assertEqual(session.conversation_state['existing_cv'], self.document)
        self.assertEqual(session.current_section, 'review')
        self.assertEqual(set(data), {'id','cv_id','status','current_section','assistant_message','created_at'})
        messages = build_messages(session, 'I want to enter another project')
        self.assertTrue(any('EXISTING CV EDITING MODE' in message['content'] for message in messages))
        gemini.assert_not_called()
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.version, 1)

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_add_project_collects_only_requested_details_and_preserves_saved_cv(self, gemini):
        session, _ = self.start()
        requested = self.send(session, 'I want to enter another project')
        self.assertEqual(requested['section'], 'projects')
        self.assertIn('project', requested['assistant_message'])
        self.assertNotIn('role are you targeting', requested['assistant_message'])
        gemini.assert_not_called()
        gemini.side_effect = [
            self.extracted('projects', [{'name':'New Project','description':None,'technologies':None,'url':None}]),
            self.extracted('projects', [{'name':None,'description':'Builds CVs.','technologies':None,'url':None}]),
            self.extracted('projects', [{'name':None,'description':None,'technologies':['Django'],'url':None}]),
        ]
        name = self.send(session, 'New Project')
        self.assertIn('describe', name['assistant_message'])
        description = self.send(session, 'It builds CVs')
        self.assertIn('technologies', description['assistant_message'])
        technologies = self.send(session, 'Django')
        self.assertEqual(technologies['section'], 'review')
        self.assertIn('What else', technologies['assistant_message'])
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data, self.document)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id), 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        document = saved.data['cv']['data']
        self.assertEqual(document['projects'][0], self.document['projects'][0])
        self.assertEqual(document['projects'][1]['name'], 'New Project')
        self.assertEqual(document['projects'][1]['technologies'], ['Django'])
        self.assertEqual(document['personal'], self.document['personal'])
        self.assertEqual(document['meta'], self.document['meta'])
        gemini.assert_not_called()  # Simple project fields now use deterministic extraction.
        again = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id), 'expected_version': 2}, format='json')
        self.assertEqual(again.data['cv']['version'], 2)
        self.assertEqual(len(again.data['cv']['data']['projects']), 2)

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_correction_updates_requested_field_without_collecting_whole_profile(self, gemini):
        session, _ = self.start()
        gemini.return_value = self.extracted('personal', {'full_name':None,'email':None,'phone':None,'location':'Islamabad','linkedin':None,'github':None,'portfolio':None})
        response = self.send(session, 'Change my location to Islamabad')
        self.assertEqual(response['section'], 'review')
        self.assertIn('What else', response['assistant_message'])
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['personal']['location'], 'Islamabad')
        self.assertEqual(saved.data['cv']['data']['projects'], self.document['projects'])

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_edit_saved_project_does_not_require_its_unchanged_fields(self, gemini):
        session, _ = self.start()
        self.send(session, 'edit a project')
        gemini.side_effect = [
            self.extracted('projects',[{'name':'Saved Project','description':None,'technologies':None,'url':None}]),
            self.extracted('projects',[{'name':None,'description':'Updated project description.','technologies':None,'url':None}]),
        ]
        choice = self.send(session, 'Saved Project')
        self.assertIn('change', choice['assistant_message'])
        corrected = self.send(session, 'Change its description to Updated project description.')
        self.assertEqual(corrected['section'], 'review')
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(len(saved.data['cv']['data']['projects']), 1)
        self.assertEqual(saved.data['cv']['data']['projects'][0]['technologies'], ['Python'])
        self.assertEqual(saved.data['cv']['data']['projects'][0]['description'], 'Updated project description.')

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_irrelevant_input_cannot_change_edit_proposals_or_advance_project(self, gemini):
        session, _ = self.start()
        self.send(session, 'add another project')
        response = self.extracted('projects',[{'name':'Mango','description':'Unsupported','technologies':['Python'],'url':None}])
        response['intent'] = 'irrelevant'
        gemini.return_value = response
        result = self.send(session, 'I like mango')
        self.assertEqual(result['intent'], 'irrelevant')
        self.assertEqual(result['section'], 'projects')
        self.assertTrue(all(value is None for value in result['cv_updates'].values()))
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['edit_updates'], {'personal':{}})
        self.assertEqual(self.send(session, 'finish')['next_action'], 'ask_question')

    def test_missing_or_empty_cv_keeps_original_interview(self):
        blank = create_cv(user=self.user, values={'name':'Empty CV','data':{}})
        session, response = self.start(blank.id)
        self.assertIn('What role are you targeting?', response['assistant_message'])
        self.assertNotIn('mode', session.conversation_state)
        response = self.client.post('/api/chat/sessions/', {}, format='json')
        self.assertIn('What role are you targeting?', response.data['assistant_message'])

    def test_foreign_cv_cannot_seed_an_editing_session(self):
        private = create_cv(user=self.other, values={'name':'Private','data':self.document})
        before = ChatSession.objects.count()
        response = self.client.post('/api/chat/sessions/', {'cv_id':private.id}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ChatSession.objects.count(), before)

    def test_untouched_legacy_session_upgrades_on_resume_without_erasing_history(self):
        session = ChatSession.objects.create(user=self.user, cv_id=self.cv.id, conversation_state=get_initial_state())
        original = ChatMessage.objects.create(session=session, role='assistant', content='What role are you targeting?')
        response = self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['messages'][-1]['content'], INTRO)
        self.assertTrue(session.messages.filter(pk=original.id).exists())
        self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(session.messages.count(), 2)

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_second_project_request_starts_a_new_draft(self, gemini):
        session, _ = self.start()
        gemini.side_effect = [self.extracted('projects',[{'name':name,'description':'A project.','technologies':['Django'],'url':None}]) for name in ('First New','Second New')]
        self.send(session, 'add another project')
        self.send(session, 'First New uses Django')
        second = self.send(session, 'add another project')
        self.assertEqual(second['section'], 'projects')
        self.send(session, 'Second New uses Django')
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual([item['name'] for item in saved.data['cv']['data']['projects']], ['Saved Project','First New','Second New'])

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_adding_project_preserves_metadata_changed_later_in_editor(self, gemini):
        session, _ = self.start()
        gemini.return_value = self.extracted('projects',[{'name':'New Project','description':'Builds CVs.','technologies':['Django'],'url':None}])
        self.send(session, 'New Project builds CVs using Django')
        self.send(session, 'finish')
        update_cv(user=self.user,cv_id=self.cv.id,values={'target_role':'AI Engineer','expected_version':1})
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':2}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['meta']['target_role'], 'AI Engineer')

    def test_legacy_resume_preserves_unsaved_correction_and_saved_context(self):
        session = ChatSession.objects.create(user=self.user, cv_id=self.cv.id, conversation_state=get_initial_state())
        ChatMessage.objects.create(session=session, role='user', content='Change my location to Islamabad')
        original = ChatMessage.objects.create(session=session, role='assistant', content='What role are you targeting?', section='target', cv_updates={'personal':{'location':'Islamabad'}})
        response = self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['messages'][-1]['content'], INTRO)
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['edit_updates']['personal']['location'], 'Islamabad')
        self.assertTrue(session.messages.filter(pk=original.id).exists())
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['personal']['location'], 'Islamabad')
        self.assertEqual(saved.data['cv']['data']['projects'], self.document['projects'])

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_grouped_skills_and_partial_project_stay_on_project_followup(self, gemini):
        session, _ = self.start()
        response = self.extracted('projects',[{'name':'New Project','description':None,'technologies':None,'url':None}])
        response['cv_updates']['skills'] = ['Django']
        gemini.return_value = response
        reply = self.send(session, 'Add Django to my skills and a project called New Project')
        self.assertEqual(reply['section'], 'projects')
        self.assertIn('describe', reply['assistant_message'])
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['edit_updates']['skills'], ['Django'])
        self.assertNotIn('technologies', session.conversation_state['edit_draft'][0])

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_explicit_new_project_does_not_replace_existing_project_with_same_name(self, gemini):
        session, _ = self.start()
        self.send(session, 'I want to enter another project')
        gemini.return_value = self.extracted('projects',[{'name':'Saved Project','description':'A distinct new project.','technologies':['Django'],'url':None}])
        self.assertEqual(self.send(session, 'Another Saved Project uses Django')['section'], 'review')
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['projects'][0], self.document['projects'][0])
        self.assertEqual(saved.data['cv']['data']['projects'][1]['description'], 'A distinct new project.')
        again = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':2}, format='json')
        self.assertEqual(again.data['cv']['version'], 2)
        self.assertEqual(len(again.data['cv']['data']['projects']), 2)

    @patch('chatbot.services.conversation_service.QwenClient.generate')
    def test_separate_add_requests_keep_projects_separate_even_with_same_name(self, gemini):
        session, _ = self.start()
        gemini.side_effect = [self.extracted('projects',[{'name':'Saved Project','description':description,'technologies':['Django'],'url':None}]) for description in ('First new project.','Second new project.')]
        for text in ('Saved Project: First new project uses Django', 'Saved Project: Second new project uses Django'):
            self.send(session, 'add another project')
            self.send(session, text)
        self.send(session, 'finish')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id':str(session.id),'expected_version':1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual([item['description'] for item in saved.data['cv']['data']['projects']], ['An existing project.','First new project.','Second new project.'])

    def test_known_target_role_is_not_requested_again_even_with_empty_sections(self):
        cv = create_cv(user=self.user, values={'name':'Targeted CV','target_role':'AI Engineer','data':{}})
        session, response = self.start(cv.id)
        self.assertEqual(response['assistant_message'], INTRO)
        self.assertEqual(session.conversation_state['target_role'], 'AI Engineer')
