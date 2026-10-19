"""Catalogue, rendering, security, pagination and cross-module template journeys."""
from collections import Counter
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from pypdf import PdfReader
from docx import Document
from PIL import Image
from chatbot.models import ChatSession, ChatMessage
from cvs.models import CV, CVVersion
from cvs.validation import validate_document
from m8_renderer.samples import sample_cv, PROFILES
from m8_renderer.services.renderer import CVRenderer
from m8_renderer.services.pdf_exporter import PDFExporter
from m8_renderer.services.docx_exporter import DOCXExporter
from templates_app.catalogue import catalogue
from templates_app.models import CVTemplate


class CatalogueTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_fifty_unique_renderable_entries_and_exact_categories(self):
        rows = catalogue()
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({r['name'] for r in rows.values()}), 50)
        self.assertEqual(CVTemplate.objects.count(), 50)
        self.assertEqual(Counter(r['category'] for r in rows.values()), {
            'modern': 10, 'professional': 10, 'simple': 8, 'creative': 7,
            'ats': 7, 'minimalist': 5, 'executive': 3})
        self.assertEqual(len({r['layout_family'] for r in rows.values()}), 12)
        self.assertTrue({'modern', 'classic', 'developer'} <= rows.keys())
        for id, row in rows.items():
            with self.subTest(template=id):
                for key in ('name', 'description', 'layout_family', 'design_config', 'preview_image', 'supported_levels'):
                    self.assertTrue(row[key])
                html = CVRenderer.render_html({'template_id': id, 'cv_data': sample_cv()})
                self.assertIn('Alex Morgan', html)
                self.assertIn('Community Resource Hub', html)
                if row['layout_family'] != 'ledger':
                    self.assertIn(f'family-{row["layout_family"]}', html)
                    self.assertIn(row['design_config']['accent'], html)

    def test_variants_change_structure_or_typography_beyond_palette(self):
        signatures = set()
        for row in catalogue().values():
            if row['layout_family'] == 'ledger':
                continue  # Historical IDs intentionally keep their original implementation.
            design = dict(row['design_config'])
            design.pop('accent')
            if design['family'] not in ('split', 'sidebar', 'asymmetry', 'portfolio'):
                design.pop('aside'); design.pop('sidebar_width')
            signature = json.dumps(design, sort_keys=True)
            self.assertNotIn(signature, signatures, row['id'])
            signatures.add(signature)

    def test_cached_previews_are_real_unique_a4_images(self):
        root = settings.BASE_DIR / 'm8_renderer/static/cv_templates/previews'
        manifest = json.loads((root / 'manifest.json').read_text())
        hashes = set()
        for id in catalogue():
            path = root / f'{id}.webp'
            self.assertTrue(path.is_file(), id)
            self.assertIn('source_hash', manifest[id])
            self.assertEqual(manifest[id]['sample'], 'comparison')
            with Image.open(path) as im:
                self.assertAlmostEqual(im.width / im.height, 210 / 297, places=2)
            hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(len(hashes), 50)

    def test_samples_are_canonical_fictional_and_independent(self):
        for profile in ['comparison', *PROFILES]:
            cv = sample_cv(profile); validate_document(cv)
            self.assertIn('example.com', cv['personal']['email'])
        one = sample_cv(); one['personal']['full_name'] = 'Changed'
        self.assertEqual(sample_cv()['personal']['full_name'], 'Alex Morgan')

    def test_public_filters_pagination_and_old_list_contract(self):
        old = self.client.get('/api/templates/').data
        self.assertIsInstance(old, list); self.assertEqual(len(old), 50)
        first = self.client.get('/api/templates/?page=1').data['results']
        self.assertEqual(first[0]['id'], 'modern_horizon')
        self.assertGreaterEqual(len({t['gallery_category'] for t in first}), 7)
        ids = []
        for page in range(1, 6):
            result = self.client.get(f'/api/templates/?page={page}').data
            self.assertEqual(result['count'], 50)
            ids.extend(t['id'] for t in result['results'])
        self.assertEqual(len(set(ids)), 50)
        result = self.client.get('/api/templates/?page=1&category=ats').data
        self.assertEqual(result['count'], 7)
        self.assertTrue(all(t['ats_compatible'] for t in result['results']))
        result = self.client.get('/api/templates/?page=1&career_level=fresher').data
        self.assertEqual(result['count'], 47)
        result = self.client.get('/api/templates/?page=1&search=boardroom').data
        self.assertEqual([t['id'] for t in result['results']], ['executive_boardroom'])
        self.assertEqual(self.client.get('/api/templates/?page=1&search=not-a-real-design').data['count'], 0)
        self.assertEqual(self.client.get('/api/templates/?page=1&category=creative&role=designer').data['count'], 7)

    def test_unrenderable_or_disabled_records_cannot_be_selected(self):
        for path in ('cv_templates/missing.html', '/etc/passwd', 'cv_templates/../../config.html', 'cv_templates/designed.html'):
            CVTemplate.objects.update_or_create(pk='broken', defaults={'name': 'Broken', 'category': 'modern', 'template_path': path})
            self.assertNotIn('broken', [t['id'] for t in self.client.get('/api/templates/').data])
            self.assertEqual(self.client.get('/api/templates/broken/').status_code, 404)
        CVTemplate.objects.filter(pk='modern').update(is_available=False)
        self.assertEqual(self.client.get('/api/templates/modern/').status_code, 404)

    def test_seed_is_idempotent_and_preserves_custom_records(self):
        from importlib import import_module
        from django.apps import apps
        seed = import_module('templates_app.migrations.0003_template_gallery').seed_templates
        CVTemplate.objects.filter(pk='modern').update(name='Custom modern name', description='Administrator description')
        seed(apps, None); seed(apps, None)
        self.assertEqual(CVTemplate.objects.count(), 50)
        self.assertEqual(CVTemplate.objects.get(pk='modern').description, 'Administrator description')


class RenderingQualityTests(TestCase):
    def test_every_design_pdf_has_a4_pages_and_complete_comparison_content(self):
        cv = sample_cv()
        for id in catalogue():
            with self.subTest(template=id):
                pdf = PDFExporter.generate({'template_id': id, 'cv_data': cv})
                self.assertTrue(pdf.startswith(b'%PDF'))
                reader = PdfReader(BytesIO(pdf))
                text = '\n'.join(p.extract_text() for p in reader.pages)
                for fact in ('Alex Morgan', 'alex.morgan@example.com', 'Community Resource Hub', 'Northstar Labs',
                             'First class honours', 'Cloud Foundations', 'French', 'credentials.example.com/alex'):
                    self.assertIn(''.join(fact.split()), ''.join(text.split()), (id, fact))
                for page in reader.pages:
                    self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=1)
                    self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=1)
                    self.assertTrue(page.extract_text().strip(), 'Unexpected blank page')

    def test_long_content_and_missing_sections_in_every_layout_family(self):
        long = sample_cv(); long['summary'] = ('Reliable delivery and thoughtful engineering. ' * 65) + 'SUMMARY-END'
        long['skills'] = [f'Skill {i}' for i in range(100)]
        long['experience'] = [deepcopy(long['experience'][0]) for _ in range(5)]
        for i, entry in enumerate(long['experience']):
            entry['company'] = 'Long organisation name ' * 8 + str(i)
            entry['highlights'] = [('Delivered maintainable software with a collaborative team. ' * 14) + f'WORK-END-{i}']
        long['projects'] = [deepcopy(long['projects'][0]) for _ in range(8)]
        for i, project in enumerate(long['projects']):
            project['description'] = ('Designed accessible services and documented decisions. ' * 15) + f'PROJECT-END-{i}'
        long['languages'][-1]['name'] = 'FINAL-LANGUAGE-MARKER'
        validate_document(long)
        families = {}
        for id, row in catalogue().items(): families.setdefault(row['layout_family'], id)
        for id in families.values():
            with self.subTest(template=id):
                reader = PdfReader(BytesIO(PDFExporter.generate({'template_id': id, 'cv_data': long})))
                self.assertGreater(len(reader.pages), 1)
                text = '\n'.join(p.extract_text() for p in reader.pages)
                for fact in ['SUMMARY-END', 'Skill 99', 'FINAL-LANGUAGE-MARKER', *[f'WORK-END-{i}' for i in range(5)], *[f'PROJECT-END-{i}' for i in range(8)]]:
                    self.assertIn(''.join(fact.split()), ''.join(text.split()))
                self.assertTrue(all(p.extract_text().strip() for p in reader.pages))
                empty = sample_cv()
                for key in ('experience','education','skills','projects','certifications','achievements','languages'): empty[key] = []
                empty['summary'] = ''
                html = CVRenderer.render_html({'template_id': id, 'cv_data': empty})
                self.assertIn('Alex Morgan', html)
                self.assertNotIn('Professional Summary</h2>', html)

    def test_special_characters_escape_and_docx_content_for_new_designs(self):
        cv = sample_cv(); cv['personal']['full_name'] = 'Zoë O’Neill & García <script>alert(1)</script>'
        html = CVRenderer.render_html({'template_id': 'creative_studio', 'cv_data': cv})
        self.assertIn('&lt;script&gt;', html); self.assertNotIn('<script>', html)
        doc = Document(BytesIO(DOCXExporter.generate({'template_id': 'creative_studio', 'cv_data': cv})))
        text = '\n'.join(p.text for p in doc.paragraphs)
        self.assertIn('García', text); self.assertIn('credentials.example.com/alex', text)


class TemplateJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('gallery-owner@example.com')
        cls.other = get_user_model().objects.create_user('gallery-other@example.com')

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def create(self, template='modern'):
        response = self.client.post('/api/cvs/', {'name': 'My CV', 'template_id': template,
            'target_role': 'Data Analyst', 'career_level': 'experienced', 'data': {}}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_manual_creation_and_switch_preserve_id_content_and_version(self):
        cv = self.create('creative_studio'); id = cv['id']
        before = deepcopy(cv['data']); expected = deepcopy(before); expected['meta']['template_id'] = 'professional_blue'
        with patch('httpx.Client.send', side_effect=AssertionError('No AI or network during switching')):
            response = self.client.patch(f'/api/cvs/{id}/', {'template_id': 'professional_blue', 'expected_version': 1}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data'], expected)
        self.assertEqual(response.data['version'], 2); self.assertEqual(response.data['id'], id)
        self.assertEqual(CV.objects.count(), 1); self.assertEqual(CVVersion.objects.count(), 2)
        self.assertEqual(self.client.patch(f'/api/cvs/{id}/', {'template_id': 'ats_plain', 'expected_version': 1}, format='json').status_code, 409)
        self.assertContains(self.client.get(f'/api/cvs/{id}/preview/'), 'family-split')
        self.assertContains(self.client.get(f'/cvs/{id}/edit/'), 'Change template')

    def test_preview_is_public_with_samples_and_owner_scoped_with_personal_data(self):
        cv = self.create(); data = sample_cv(); data['personal']['full_name'] = 'PRIVATE OWNER NAME'
        saved = self.client.patch(f'/api/cvs/{cv["id"]}/', {'data': data, 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200)
        path = '/api/cvs/templates/creative_studio/preview/'
        response = self.client.get(path + f'?cv_id={cv["id"]}')
        self.assertContains(response, 'PRIVATE OWNER NAME'); self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(self.client.get(path, {'cv_id': '²'}).status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(path + f'?cv_id={cv["id"]}').status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(path + f'?cv_id={cv["id"]}').status_code, 401)
        response = self.client.get(path); self.assertContains(response, 'Alex Morgan')
        self.assertNotContains(response, 'PRIVATE OWNER NAME')
        self.assertEqual(self.client.get(path + '?sample=unknown').status_code, 400)
        self.assertContains(self.client.get(path + '?sample=designer'), 'Graphic Designer')
        self.assertEqual(CV.objects.get(pk=cv['id']).version, 2)

    def test_switch_rejects_unavailable_and_other_owners(self):
        cv = self.create(); url = f'/api/cvs/{cv["id"]}/'
        self.assertEqual(self.client.patch(url, {'template_id': 'missing', 'expected_version': 1}, format='json').status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(url, {'template_id': 'ats_plain', 'expected_version': 1}, format='json').status_code, 404)
        self.assertEqual(CV.objects.get(pk=cv['id']).version, 1)

    def test_ai_session_selection_survives_messages_and_m2_save(self):
        result = self.client.post('/api/chat/sessions/', {'cv_name': 'AI Gallery CV', 'target_role': 'Data Analyst',
            'career_level': 'experienced', 'template_id': 'modern_vector'}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        session = ChatSession.objects.get(pk=result.data['id'])
        from django.urls import reverse
        with patch('chatbot.services.conversation_service.QwenClient.generate', return_value={
            'assistant_message': 'Thanks. Let us continue.', 'intent': 'collect_information',
            'section': 'personal', 'cv_updates': {}, 'next_action': 'ask_question'}):
            reply = self.client.post(reverse('chat-message-create', kwargs={'session_id': session.pk}),
                {'message': 'I am Fictional AI Example.'}, format='json')
        self.assertEqual(reply.status_code, 200, reply.data)
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['template_id'], 'modern_vector')
        session.status = 'completed'; session.save(update_fields=['status'])
        ChatMessage.objects.create(session=session, role='assistant', content='Collected', cv_updates={
            'personal': {'full_name': 'Fictional AI Example'}, 'summary': 'Builds useful services.', 'skills': ['Python']})
        response = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        saved = response.data['cv']
        self.assertEqual(saved['template_id'], 'modern_vector')
        self.assertEqual(saved['target_role'], 'Data Analyst')
        self.assertEqual(saved['career_level'], 'experienced')

    def test_import_review_document_accepts_selected_template_without_content_loss(self):
        # The existing M4 review submits its canonical approved document through M2.
        data = sample_cv(); data['meta']['template_id'] = 'creative_prism'
        response = self.client.post('/api/cvs/', {'name': 'Approved import', 'data': data}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['data'], data)
        self.assertContains(self.client.get(f'/api/cvs/{response.data["id"]}/preview/'), 'family-sidebar')

    def test_gallery_shell_uses_static_images_and_no_private_content(self):
        response = self.client.get('/templates/')
        self.assertContains(response, 'Choose Your Perfect')
        self.assertContains(response, 'template_gallery.js')
        self.assertContains(response, 'loadMoreTemplates')
        self.assertContains(response, 'ATS-Friendly')
