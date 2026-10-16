"""Cross-module regressions found by the final audit; providers are always mocked."""
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

    def test_restoration_appends_a_snapshot_and_preserves_all_later_history(self):
        cv = self.create(); url = f"/api/cvs/{cv['id']}/"
        original = deepcopy(cv['data'])
        second = deepcopy(original); second['summary'] = 'Second version'
        self.client.patch(url, {'data': second, 'name': 'Second title', 'expected_version': 1}, format='json')
        self.client.patch(url, {'name': 'Third title', 'expected_version': 2}, format='json')
        restored = self.client.post(url + 'restore/', {'version': 1, 'expected_version': 3}, format='json')
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data['version'], 4)
        self.assertEqual(restored.data['data'], original)
        self.assertEqual(restored.data['name'], 'Audit CV')
        self.assertEqual(list(CVVersion.objects.filter(cv_id=cv['id']).values_list('version', flat=True)), [4, 3, 2, 1])
        self.assertEqual(CVVersion.objects.get(cv_id=cv['id'], version=2).data, second)

    def test_restoration_requires_current_version_and_owner_and_preserves_failed_writes(self):
        cv = self.create(); url = f"/api/cvs/{cv['id']}/restore/"
        for payload, status in [({'version': 1}, 400), ({'version': 1, 'expected_version': 99}, 409),
                                ({'version': 99, 'expected_version': 1}, 404)]:
            self.assertEqual(self.client.post(url, payload, format='json').status_code, status)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url, {'version': 1, 'expected_version': 1}, format='json').status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(url, {'version': 1, 'expected_version': 1}, format='json').status_code, 401)
        self.assertEqual(CV.objects.get(pk=cv['id']).version, 1)
        self.assertEqual(CVVersion.objects.filter(cv_id=cv['id']).count(), 1)

    def test_invalid_or_disabled_template_is_rejected_without_persistence(self):
        data = deepcopy(SAMPLE_CV); data['meta']['template_id'] = 'missing-template'
        response = self.client.post('/api/cvs/', {'name': 'Invalid', 'data': data}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CV.objects.count(), 0)

    def test_all_builtin_templates_render_and_pdf_contains_saved_content_and_a4_pages(self):
        cv = self.create()
        for theme in ('modern', 'classic', 'developer'):
            data = deepcopy(cv['data']); data['meta']['template_id'] = theme
            saved = self.client.patch(f"/api/cvs/{cv['id']}/", {'data': data}, format='json')
            self.assertEqual(saved.status_code, 200)
            preview = self.client.get(f"/api/cvs/{cv['id']}/preview/")
            self.assertContains(preview, f'theme-{theme}')
            pdf = self.client.post(f"/api/cvs/{cv['id']}/export/pdf/")
            self.assertEqual(pdf.status_code, 200)
            reader = PdfReader(BytesIO(pdf.content))
            text = '\n'.join(page.extract_text() for page in reader.pages)
            for fact in ('Ali Khan', 'ali@example.com', 'Python Django Developer', 'Example University',
                         'Employee Management System', 'PostgreSQL', '2022-09'):
                self.assertIn(fact, text)
            self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 595.28, delta=1)
            self.assertAlmostEqual(float(reader.pages[0].mediabox.height), 841.89, delta=1)
        self.client.force_authenticate(self.other)
        for suffix in ('export/pdf/', 'export/docx/'):
            self.assertEqual(self.client.post(f"/api/cvs/{cv['id']}/{suffix}").status_code, 404)

    def test_missing_template_file_is_a_safe_validation_error(self):
        from templates_app.models import CVTemplate
        cv = self.create()
        CVTemplate.objects.filter(pk='modern').update(template_path='cv_templates/missing_file.html')
        response = self.client.get(f"/api/cvs/{cv['id']}/preview/")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b'Traceback', response.content)

    def test_upload_type_mismatch_empty_size_and_zip_expansion_are_rejected(self):
        files = [SimpleUploadedFile('fake.pdf', b'not a PDF'), SimpleUploadedFile('fake.docx', b'%PDF-1.7'),
                 SimpleUploadedFile('empty.pdf', b''), SimpleUploadedFile('big.pdf', b'x' * (5 * 1024 * 1024 + 1))]
        for file in files:
            self.assertEqual(self.client.post('/api/cv-import/upload/', {'file': file}, format='multipart').status_code, 400)
        output = BytesIO()
        with ZipFile(output, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>'); archive.writestr('word/document.xml', '<document/>')
        with patch('cv_imports.services.validators.MAX_UNCOMPRESSED_SIZE', 5):
            self.assertEqual(self.client.post('/api/cv-import/upload/',
                {'file': SimpleUploadedFile('expanded.docx', output.getvalue())}, format='multipart').status_code, 400)
        self.assertEqual(CVImport.objects.count(), 0)

    def test_extraction_is_idempotent_and_media_is_not_public(self):
        output = BytesIO(); document = Document(); document.add_paragraph('Audit user builds Django APIs.'); document.save(output)
        upload = self.client.post('/api/cv-import/upload/', {'file': SimpleUploadedFile('audit.docx', output.getvalue())}, format='multipart')
        record = CVImport.objects.get(pk=upload.data['import_id'])
        self.assertEqual(self.client.get('/media/' + record.file.name).status_code, 404)
        url = f'/api/cv-import/{record.id}/extract/'
        first = self.client.post(url)
        with patch('cv_imports.services.import_service.extract_text', side_effect=AssertionError('Must not parse twice')):
            second = self.client.post(url)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data, second.data)
        record.status = CVImport.Status.EXTRACTING; record.save(update_fields=['status'])
        self.assertEqual(self.client.post(url).status_code, 409)

    def test_real_exported_pdf_can_be_uploaded_and_extracted_without_ai(self):
        cv = self.create()
        pdf = self.client.post(f"/api/cvs/{cv['id']}/export/pdf/")
        upload = self.client.post('/api/cv-import/upload/',
            {'file': SimpleUploadedFile('saved.pdf', pdf.content)}, format='multipart')
        self.assertEqual(upload.status_code, 201)
        extracted = self.client.post(f"/api/cv-import/{upload.data['import_id']}/extract/")
        self.assertEqual(extracted.status_code, 200)
        self.assertIn('Ali Khan', extracted.data['text'])
        self.assertIn('PostgreSQL', extracted.data['text'])

    def test_corrupt_and_image_only_pdfs_fail_without_creating_a_cv(self):
        output = BytesIO(); writer = PdfWriter(); writer.add_blank_page(width=595, height=842); writer.write(output)
        for content in (b'%PDF-1.7\ncorrupt', output.getvalue()):
            upload = self.client.post('/api/cv-import/upload/',
                {'file': SimpleUploadedFile('unreadable.pdf', content)}, format='multipart')
            self.assertEqual(upload.status_code, 201)
            failed = self.client.post(f"/api/cv-import/{upload.data['import_id']}/extract/")
            self.assertEqual(failed.status_code, 422)
            self.assertEqual(CVImport.objects.get(pk=upload.data['import_id']).status, 'failed')
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

    def test_docx_import_to_m6_review_m2_editor_preview_pdf_and_reopen(self):
        output = BytesIO(); document = Document(); document.add_paragraph(json.dumps(SAMPLE_CV)); document.save(output)
        uploaded = self.client.post('/api/cv-import/upload/', {'file': SimpleUploadedFile('journey.docx', output.getvalue())}, format='multipart')
        text = self.client.post(f"/api/cv-import/{uploaded.data['import_id']}/extract/").data['text']
        provider = Mock(); provider.generate_structured.return_value = deepcopy(SAMPLE_CV)
        with patch('ai.services.extraction.get_llm_provider', return_value=provider):
            extracted = self.client.post('/api/ai/extract/', {'raw_text': text}, format='json')
        self.assertEqual(extracted.status_code, 200, extracted.data)
        reviewed = deepcopy(extracted.data['data']['cv'])
        reviewed['personal']['full_name'] = 'Reviewed Candidate'
        reviewed['meta']['template_id'] = 'developer'
        saved = self.create(reviewed)
        self.assertEqual(self.client.get(f"/api/cvs/{saved['id']}/").data['data'], reviewed)
        self.assertEqual(self.client.get(f"/cvs/{saved['id']}/edit/").status_code, 200)
        self.assertContains(self.client.get(f"/api/cvs/{saved['id']}/preview/"), 'Reviewed Candidate')
        pdf = self.client.post(f"/api/cvs/{saved['id']}/export/pdf/")
        self.assertIn('Reviewed Candidate', ''.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages))
        self.assertEqual(provider.generate_structured.call_count, 1)

    def test_rewrite_cannot_take_new_metrics_from_the_target_role(self):
        provider = Mock(); provider.generate_structured.return_value = {
            'rewritten': 'Improved performance by 99%.', 'changes': ['Improved wording.']}
        with patch('ai.services.writing.get_llm_provider', return_value=provider):
            response = self.client.post('/api/ai/rewrite/', {'text': 'I made APIs using Django.',
                'section': 'summary', 'target_role': 'Backend 99% performance engineer'}, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(CV.objects.count(), 0)

    def test_sensitive_api_responses_disable_http_caching(self):
        cv = self.create()
        for url in ['/api/auth/me/', '/api/cvs/', f"/api/cvs/{cv['id']}/", '/api/chat/sessions/']:
            response = self.client.get(url)
            self.assertIn('no-store', response['Cache-Control'])
            self.assertIn('Authorization', response['Vary'])

    def test_question_map_requests_one_question_at_a_time(self):
        for key, value in QUESTION_MAP.items():
            self.assertEqual(value.count('?'), 1, key)
        self.assertNotIn('phone', QUESTION_MAP['personal', 'email'])
        self.assertNotIn('portfolio', QUESTION_MAP['personal', 'github'])
