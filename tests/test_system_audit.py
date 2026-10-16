"""Chatbot integration regressions; providers are always mocked."""
from copy import deepcopy
import json
from io import BytesIO
from unittest.mock import patch, Mock
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from pypdf import PdfReader, PdfWriter
from docx import Document

from cvs.models import CV, CVVersion
from cv_imports.models import CVImport
from chatbot.models import ChatSession, ChatMessage
from chatbot.services.errors import AIServiceError, AIRateLimitError
from chatbot.services.conversation_service import process_user_message, ConversationConflict
from chatbot.services.response_normalizer import QUESTION_MAP
from chatbot.services.response_validator import validate_ai_response
from tests.test_m8 import SAMPLE_CV


def chat_response():
    return {'assistant_message': 'Collected. Ready for review.', 'intent': 'complete', 'section': 'review',
        'state_updates': {'target_role': None, 'career_level': None,
            'skipped_personal_fields': ['linkedin', 'github', 'portfolio']},
        'cv_updates': {'personal': deepcopy(SAMPLE_CV['personal']), 'summary': SAMPLE_CV['summary'],
            'skills': SAMPLE_CV['skills'], 'education': SAMPLE_CV['education'],
            'experience': [{'company': 'Example', 'role': 'Intern', 'location': 'Lahore',
                'start_date': '2025-01', 'end_date': '2025-06', 'responsibilities': ['Built APIs.']}],
            'projects': [{key: value for key, value in SAMPLE_CV['projects'][0].items() if key != 'highlights'}],
            'certifications': ['Python Certificate'], 'achievements': ['Completed capstone project'],
            'languages': ['English']}, 'next_action': 'complete'}


class SystemAuditTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('audit@example.com', 'Audit-Strong-735!')
        self.other = get_user_model().objects.create_user('other-audit@example.com', 'Other-Strong-735!')
        self.client.force_authenticate(self.user)

    def create(self, data=None):
        response = self.client.post('/api/cvs/', {'name': 'Audit CV', 'data': deepcopy(data or SAMPLE_CV)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data



    def test_invalid_or_disabled_template_is_rejected_without_persistence(self):
        data = deepcopy(SAMPLE_CV); data['meta']['template_id'] = 'missing-template'
        response = self.client.post('/api/cvs/', {'name': 'Invalid', 'data': data}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CV.objects.count(), 0)







    def test_gemini_failures_are_safe_and_do_not_persist_messages(self):
        for exception, status in [(AIServiceError('Unavailable'), 502), (AIRateLimitError('Busy'), 429)]:
            created = self.client.post('/api/chat/sessions/', {}, format='json')
            with patch('chatbot.services.conversation_service.QwenClient') as client:
                client.return_value.generate.side_effect = exception
                response = self.client.post(f"/api/chat/sessions/{created.data['id']}/messages/",
                    {'message': 'Please help me choose a relevant career direction'}, format='json')
            self.assertEqual(response.status_code, status, response.data)
            self.assertEqual(ChatMessage.objects.filter(session_id=created.data['id']).count(), 1)

    def test_stale_conversation_cannot_overwrite_newer_state(self):
        created = self.client.post('/api/chat/sessions/', {}, format='json')
        stale = ChatSession.objects.get(pk=created.data['id'])
        latest = ChatSession.objects.get(pk=stale.pk)
        response = chat_response()
        response['intent'] = 'update_cv'; response['next_action'] = 'ask_question'
        response['state_updates']['target_role'] = 'Python Django Backend Developer'
        response['cv_updates'] = {key: None for key in response['cv_updates']}
        with patch('chatbot.services.conversation_service.QwenClient') as client:
            client.return_value.generate.return_value = response
            process_user_message(session=latest, user_message='I want Python Django backend jobs.')
            with self.assertRaises(ConversationConflict):
                process_user_message(session=stale, user_message='I want Python Django backend jobs.')
        self.assertEqual(ChatMessage.objects.filter(session=stale).count(), 3)

    def test_ai_creation_preserves_selections_through_chat_save_preview_and_pdf(self):
        created = self.client.post('/api/chat/sessions/', {'cv_name': 'Selected AI CV',
            'target_role': 'Backend Developer', 'career_level': 'fresher', 'template_id': 'classic'}, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data['assistant_message'], 'What is your full name?')
        response = chat_response(); validate_ai_response(response)
        with patch('chatbot.services.conversation_service.QwenClient') as client:
            client.return_value.generate.return_value = response
            sent = self.client.post(f"/api/chat/sessions/{created.data['id']}/messages/",
                {'message': 'I do not have LinkedIn, GitHub or a portfolio. These are my CV details: ' + json.dumps(response['cv_updates'])}, format='json')
        self.assertEqual(sent.status_code, 200, sent.data)
        self.assertEqual(sent.data['section'], 'languages')
        self.assertEqual(sent.data['next_action'], 'ask_question')
        sent = self.client.post(f"/api/chat/sessions/{created.data['id']}/messages/",
            {'message': 'keep these unspecified'}, format='json')
        self.assertEqual(sent.data['next_action'], 'review')
        # Providers cannot complete an interview; the user explicitly finishes after review.
        sent = self.client.post(f"/api/chat/sessions/{created.data['id']}/messages/",
            {'message': 'finish'}, format='json')
        self.assertEqual(sent.data['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': created.data['id']}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        cv = saved.data['cv']; self.assertEqual(cv['name'], 'Selected AI CV')
        self.assertEqual(cv['data']['meta'], {'target_role': 'Backend Developer', 'career_level': 'fresher', 'template_id': 'classic'})
        self.assertContains(self.client.get(f"/api/cvs/{cv['id']}/preview/"), 'Ali Khan')
        self.assertEqual(self.client.post(f"/api/cvs/{cv['id']}/export/pdf/").status_code, 200)
        again = self.client.post('/api/cvs/from-chat/', {'session_id': created.data['id']}, format='json')
        self.assertEqual(again.data['cv']['id'], cv['id'])
        self.assertEqual(CV.objects.count(), 1)

    def test_conversation_discovery_is_authenticated_owner_scoped(self):
        mine = self.client.post('/api/chat/sessions/', {}, format='json').data
        ChatSession.objects.create(user=self.other)
        sessions = self.client.get('/api/chat/sessions/').data
        self.assertEqual(sessions['count'], 1)
        self.assertEqual(str(sessions['results'][0]['id']), str(mine['id']))
        self.assertNotIn('conversation_state', sessions['results'][0])
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/chat/sessions/').status_code, 401)




    def test_question_map_requests_one_question_at_a_time(self):
        for key, value in QUESTION_MAP.items():
            self.assertEqual(value.count('?'), 1, key)
        self.assertNotIn('phone', QUESTION_MAP['personal', 'email'])
        self.assertNotIn('portfolio', QUESTION_MAP['personal', 'github'])
