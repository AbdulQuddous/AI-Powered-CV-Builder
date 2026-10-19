"""Opt-in real browser -> HTTP -> Django -> isolated database journeys.

RUN_BROWSER_E2E=1 enables the installed ChromeDriver. E2E_VENDOR_DIR supplies
cached copies of the application's existing frontend libraries. All AI clients
are mocked, even in this opt-in suite. No development records are touched.
"""
import json
import os
import socket
import subprocess
import tempfile
import time
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from docx import Document
from pypdf import PdfReader

from cvs.models import CV
from tests.test_m8 import SAMPLE_CV
from tests.test_system_audit import chat_response


class LocalLibrariesMiddleware:
    """Test-only CDN replacement: the real application scripts stay unchanged."""
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if response.get('Content-Type', '').startswith('text/html'):
            html = response.content.decode().replace(
                'https://cdn.jsdelivr.net/npm/alpinejs@3.17.4/dist/cdn.min.js', '/static/audit-libraries/alpine.js'
            ).replace('https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4', '/static/audit-libraries/tailwind.js')
            response.content = html.encode()
            response['Content-Length'] = len(response.content)
        return response


class Browser:
    def __init__(self, downloads):
        self.profile = tempfile.TemporaryDirectory(prefix='cv-e2e-browser-')
        with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.process = subprocess.Popen(['/snap/chromium/current/usr/lib/chromium-browser/chromedriver', f'--port={port}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while True:
            try: self.command('/status', None, 'GET'); break
            except OSError:
                if time.monotonic() > deadline: raise
                time.sleep(.1)
        result = self.command('/session', {'capabilities': {'alwaysMatch': {'browserName': 'chrome',
            'goog:chromeOptions': {'binary': '/snap/chromium/current/usr/lib/chromium-browser/chrome',
                'args': ['--headless', '--no-sandbox', '--disable-gpu', '--window-size=1600,1050', '--user-data-dir=' + self.profile.name],
                'prefs': {'download.default_directory': str(downloads), 'download.prompt_for_download': False}}}}})
        self.session = result['sessionId']
        self.command(f'/session/{self.session}/goog/cdp/execute', {'cmd': 'Browser.setDownloadBehavior',
            'params': {'behavior': 'allow', 'downloadPath': str(downloads)}})

    def command(self, path, payload, method='POST'):
        req = Request(self.url + path, data=None if payload is None else json.dumps(payload).encode(),
            method=method, headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=20) as response: result = json.load(response)['value']
        except HTTPError as error:
            result = json.load(error)['value']; raise AssertionError(result.get('message', 'WebDriver failure'))
        return result

    def js(self, script, *args):
        return self.command(f'/session/{self.session}/execute/sync', {'script': script, 'args': list(args)})

    def wait(self, expression, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js('return ' + expression): return
            time.sleep(.05)
        raise AssertionError('Browser condition timed out: ' + expression)

    def get(self, url): self.command(f'/session/{self.session}/url', {'url': url})
    def click(self, selector):
        # WebDriver's automatic scroll can race the application's smooth-scroll
        # CSS. Position the element instantly, then perform a native pointer click.
        self.js("document.querySelector(arguments[0]).scrollIntoView({block:'center',behavior:'instant'})", selector)
        element = self.command(f'/session/{self.session}/element', {'using': 'css selector', 'value': selector})
        self.command(f'/session/{self.session}/element/{element["element-6066-11e4-a52e-4f735466cecf"]}/click', {})

    def value(self, selector, value):
        self.js("const node=document.querySelector(arguments[0]);node.value=arguments[1];node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));", selector, value)

    def upload(self, selector, path):
        element = self.command(f'/session/{self.session}/element', {'using': 'css selector', 'value': selector})
        self.command(f'/session/{self.session}/element/{element["element-6066-11e4-a52e-4f735466cecf"]}/value', {'text': str(path), 'value': list(str(path))})

    def close(self):
        try: self.command(f'/session/{self.session}', None, 'DELETE')
        finally: self.process.terminate(); self.process.wait(timeout=10); self.profile.cleanup()


class ChatProvider:
    def generate(self, messages): return chat_response()


class IntelligenceProvider:
    def generate_structured(self, **kwargs):
        properties = kwargs['schema']['properties']
        if 'summary' in properties and 'changes' in properties:
            return {
                'summary': 'Clearer wording for the saved CV and target role.',
                'changes': [
                    {'path': '/summary', 'original': SAMPLE_CV['summary'],
                     'rewritten': 'Software Engineering graduate building applications with Python and Django.',
                     'reason': 'Focus the summary on the supported development skills.'},
                    {'path': '/projects/0/description', 'original': SAMPLE_CV['projects'][0]['description'],
                     'rewritten': 'Built an employee management system with Django.',
                     'reason': 'Use direct wording for the existing project.'},
                ],
                'suggestions': ['Only include skills you can support.'],
            }
        if 'overall_feedback' in properties:
            return {'overall_feedback': 'Clear and relevant.', 'suggestions': ['Keep the CV concise.'],
                'proposed_changes': [{'path': '/summary', 'original': SAMPLE_CV['summary'],
                    'replacement': 'Software Engineering graduate with Python and Django skills.', 'reason': 'Clearer wording.'}],
                'missing_information': [], 'warnings': []}
        if 'rewritten' in properties: return {'rewritten': 'Developed APIs using Django.', 'changes': ['Improved wording.']}
        if 'match_score' in properties: return {'suggestions': [], 'strengths': ['Python'], 'gaps': [], 'match_score': 75}
        return deepcopy(SAMPLE_CV)


@skipUnless(os.environ.get('RUN_BROWSER_E2E') == '1', 'Explicit browser opt-in required')
class BrowserJourneys(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        vendor = Path(os.environ['E2E_VENDOR_DIR'])
        for name in ('alpine.js',):
            if not (vendor / 'audit-libraries' / name).is_file(): raise RuntimeError('Missing cached frontend library: ' + name)
        cls.config = override_settings(STATICFILES_DIRS=[*settings.STATICFILES_DIRS, vendor],
            MIDDLEWARE=[*settings.MIDDLEWARE, 'tests.browser_e2e.LocalLibrariesMiddleware'], GEMINI_API_KEY='')
        cls.config.enable(); super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass(); cls.config.disable()

    def setUp(self):
        # TransactionTestCase flushes data migrations between browser journeys.
        import importlib
        from django.apps import apps
        importlib.import_module('templates_app.migrations.0002_builtin_templates').seed_templates(apps, None)
        self.files = tempfile.TemporaryDirectory(prefix='cv-e2e-files-')
        self.addCleanup(self.files.cleanup)
        self.browser = Browser(Path(self.files.name)); self.addCleanup(self.browser.close)
        self.user = get_user_model().objects.create_user('browser@example.com', 'Browser-Strong-735!')
        self.patchers = [patch('chatbot.services.conversation_service.QwenClient', ChatProvider)] + [
            patch(f'ai.services.{service}.get_llm_provider', return_value=IntelligenceProvider())
            for service in ('extraction', 'analysis', 'writing', 'final_review', 'tailoring')]
        for patcher in self.patchers: patcher.start(); self.addCleanup(patcher.stop)
        self.browser.get(self.live_server_url + '/dashboard/')
        self.browser.wait("document.getElementById('loginModal') && !document.getElementById('loginModal').classList.contains('hidden')")
        self.browser.value('#loginEmail', 'browser@example.com'); self.browser.value('#loginPassword', 'Browser-Strong-735!')
        self.browser.click('#loginSubmit')
        self.browser.wait("document.getElementById('loginModal').classList.contains('hidden') && !state.loading")

    def saved_cv(self, name='Browser CV', summary=None, data=None):
        from cvs.services import create_cv
        data = deepcopy(SAMPLE_CV if data is None else data)
        if summary: data['summary'] = summary
        return create_cv(user=self.user, values={'name': name, 'data': data})

    def reload_dashboard(self):
        self.browser.get(self.live_server_url + '/dashboard/')
        self.browser.wait("typeof state!=='undefined' && !state.loading && !document.getElementById('loginModal').classList.contains('hidden')===false")

    def test_profile_refresh_and_server_logout(self):
        self.browser.click('#profileBtn'); self.browser.wait("!profile.loading && profile.loaded!==null")
        self.browser.value('#profileName', 'Browser Updated'); self.browser.click('#profileSubmit')
        self.browser.wait("profile.saved && !profile.saving")
        self.assertEqual(self.browser.js("return document.getElementById('profileCancel').textContent"), 'Done')
        self.user.refresh_from_db(); self.assertEqual(self.user.full_name, 'Browser Updated')
        self.browser.click('#profileCancel')
        self.browser.js("sessionStorage.setItem('cv_access','expired-test-token')")
        self.browser.click('#refreshBtn'); self.browser.wait("!state.loading && !state.signingIn")
        self.assertNotEqual(self.browser.js("return sessionStorage.getItem('cv_access')"), 'expired-test-token')
        self.browser.click('#logoutBtn')
        self.browser.wait("!state.signingOut && !document.getElementById('loginModal').classList.contains('hidden')")
        self.assertIsNone(self.browser.js("return sessionStorage.getItem('cv_refresh')"))
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        self.assertGreaterEqual(BlacklistedToken.objects.count(), 2)

    def test_manual_editor_pdf_restore_duplicate_and_delete(self):
        self.browser.click('#heroCreate'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Manual browser CV'), ('targetRole', 'Backend Developer'), ('careerLevel', 'fresher'), ('templateId', 'classic')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("location.pathname.includes('/edit/') && typeof Alpine!=='undefined'")
        self.browser.wait("document.querySelector('[x-data]') && Alpine.$data(document.querySelector('[x-data]')).loaded!==null")
        self.browser.js("const input=[...document.querySelectorAll('.m7-edit-form label')].find(label=>label.textContent.includes('full name')).querySelector('input');input.value='Browser Candidate';input.dispatchEvent(new Event('input',{bubbles:true}));")
        self.browser.click('#save-cv-btn'); self.browser.wait("!Alpine.$data(document.querySelector('[x-data]')).dirty")
        cv = CV.objects.get(owner=self.user); self.assertEqual(cv.data['personal']['full_name'], 'Browser Candidate')
        self.browser.click('#export-pdf-btn')
        target = Path(self.files.name) / f'cv-{cv.id}.pdf'
        deadline = time.monotonic() + 15
        while not target.exists() and time.monotonic() < deadline: time.sleep(.1)
        self.assertIn('Browser Candidate', ''.join(page.extract_text() for page in PdfReader(target).pages))
        self.reload_dashboard(); self.browser.click('[data-action="versions"]')
        self.browser.wait("document.getElementById('versionsRows').children.length===2")
        self.browser.click('#versionsRows tr:last-child button'); self.browser.click('#restoreConfirm')
        self.browser.wait("document.getElementById('versionsStatus').textContent==='Saved versions loaded.' && document.getElementById('restorePanel').classList.contains('hidden')")
        cv.refresh_from_db(); self.assertEqual(cv.version, 3); self.assertEqual(cv.data['personal']['full_name'], '')
        self.assertEqual(cv.versions.count(), 3)
        self.browser.click('#versionsCheckpoint')
        self.browser.wait("document.getElementById('toast').textContent==='Checkpoint 4 created.'")
        cv.refresh_from_db(); self.assertEqual(cv.version, 4); self.assertEqual(cv.versions.count(), 4)
        self.browser.click('#versionsClose'); self.browser.click('[data-action="duplicate"]')
        self.browser.wait("state.cvs.length===2 && !state.loading")
        self.browser.click('[data-action="delete"]'); self.browser.click('#deleteConfirm')
        self.browser.wait("state.cvs.length===1")
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 1)

    def test_creation_shows_validation_then_accepts_canonical_career_levels(self):
        from chatbot.models import ChatSession
        self.browser.click('#heroCreate'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        self.assertEqual(self.browser.js("return [...document.getElementById('careerLevel').options].map(option=>option.value)"),
                         ['fresher', 'experienced', 'other'])
        for field, value in [('cvName', 'Experienced manual CV'), ('targetRole', 'Backend Developer'),
                             ('careerLevel', 'experienced')]:
            self.browser.value('#' + field, value)
        self.browser.js("document.getElementById('templateId').add(new Option('Unavailable', 'missing-template'))")
        self.browser.value('#templateId', 'missing-template'); self.browser.click('#createSubmit')
        self.browser.wait("!state.creating && !document.getElementById('createError').classList.contains('hidden')")
        error = self.browser.js("return document.getElementById('createError').textContent")
        self.assertIn('Template:', error); self.assertIn('unavailable', error)
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 0)
        self.browser.value('#templateId', 'classic'); self.browser.click('#createSubmit')
        self.browser.wait("location.pathname.includes('/edit/') && typeof Alpine!=='undefined'")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(cv.data['meta']['career_level'], 'experienced')
        self.reload_dashboard(); self.browser.click('#createAI')
        self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Other career AI CV'), ('targetRole', 'Designer'),
                             ('careerLevel', 'other'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        session = ChatSession.objects.get(pk=self.browser.js("return chat.session.id"))
        self.assertEqual(session.conversation_state['career_level'], 'other')
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 1)

    def test_ai_startup_validation_and_retry_preserve_legacy_form_selections(self):
        from chatbot.models import ChatSession
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        self.browser.js("document.getElementById('careerLevel').add(new Option('Junior', 'junior'));document.getElementById('templateId').add(new Option('Unavailable', 'missing-template'))")
        for field, value in [('cvName', 'Preserved junior AI CV'), ('targetRole', 'Python Developer'),
                             ('careerLevel', 'junior'), ('templateId', 'missing-template')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit')
        self.browser.wait("!state.creating && !chat.busy && !document.getElementById('createError').classList.contains('hidden')")
        self.assertIn('Template:', self.browser.js("return document.getElementById('createError').textContent"))
        self.assertTrue(self.browser.js("return document.getElementById('chatModal').classList.contains('hidden')"))
        self.assertEqual(self.browser.js("return document.getElementById('cvName').value"), 'Preserved junior AI CV')
        self.assertEqual(ChatSession.objects.filter(user=self.user).count(), 0)
        self.browser.value('#templateId', 'classic')
        self.browser.js("""
            const original = window.fetch;
            window.startupRequests = [];
            window.fetch = function(path, options) {
                if (String(path) === '/api/chat/sessions/' && options?.method === 'POST') {
                    window.startupRequests.push(JSON.parse(options.body));
                    if (window.startupRequests.length === 1) return Promise.resolve(new Response(
                        JSON.stringify({detail: 'Temporary service failure'}),
                        {status: 503, headers: {'Content-Type': 'application/json'}}));
                }
                return original.call(this, path, options);
            };
        """)
        self.browser.click('#createSubmit')
        self.browser.wait("!state.creating && !chat.busy && !document.getElementById('chatRetry').classList.contains('hidden')")
        self.assertEqual(ChatSession.objects.filter(user=self.user).count(), 0)
        self.browser.click('#chatRetry'); self.browser.wait("chat.session!==null && !chat.busy")
        attempts = self.browser.js("return window.startupRequests")
        self.assertEqual(len(attempts), 2); self.assertEqual(attempts[0], attempts[1])
        session = ChatSession.objects.get(user=self.user)
        for key, value in {'career_level': 'experienced', 'question_profile': 'junior',
                           'cv_name': 'Preserved junior AI CV', 'target_role': 'Python Developer',
                           'template_id': 'classic'}.items():
            self.assertEqual(session.conversation_state[key], value)
        self.assertTrue(self.browser.js("return document.getElementById('createModal').classList.contains('hidden')"))
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 0)

    def test_ai_creation_resume_and_explicit_save(self):
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'AI browser CV'), ('targetRole', 'Backend Developer'), ('careerLevel', 'fresher'), ('templateId', 'classic')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        self.browser.value('#chatInput', 'Ali Khan'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && document.getElementById('chatHistory').textContent.includes('Ali Khan')")
        self.reload_dashboard(); self.browser.click('#resumeChat')
        self.browser.wait("document.getElementById('chatSessionsRows').children.length===1")
        self.browser.click('#chatSessionsRows button'); self.browser.wait("chat.session!==null && !chat.busy")
        self.browser.value('#chatInput', 'No LinkedIn, GitHub or portfolio. These are my supported facts: ' + json.dumps(chat_response()['cv_updates']))
        self.browser.click('#chatSend'); self.browser.wait("chat.session.current_section==='languages' && !chat.busy")
        self.browser.value('#chatInput', 'keep these unspecified'); self.browser.click('#chatSend')
        self.browser.wait("chat.session.current_section==='review' && !chat.busy")
        self.browser.value('#chatInput', 'finish'); self.browser.click('#chatSend')
        self.browser.wait("chat.session.status==='completed' && !chat.busy")
        self.browser.click('#chatDraft'); self.browser.wait("!chat.busy && !document.getElementById('chatDraftPanel').classList.contains('hidden')")
        self.assertIn('Ali Khan', self.browser.js("return document.getElementById('chatDraftDetails').textContent"))
        self.browser.click('#chatReopen'); self.browser.wait("chat.session.status==='active' && !chat.busy")
        self.browser.value('#chatInput', 'Change my email to corrected@example.org'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy")
        self.browser.value('#chatInput', 'finish'); self.browser.click('#chatSend')
        self.browser.wait("chat.session.status==='completed' && !chat.busy")
        self.browser.click('#chatDraft'); self.browser.wait("!chat.busy && chat.draft!==null")
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 0)
        self.browser.click('#chatFinalReview')
        self.assertIn('approve external processing', self.browser.js("return document.getElementById('chatReviewStatus').textContent"))
        self.browser.click('#chatExternalApproval'); self.browser.click('#chatFinalReview')
        self.browser.wait("!chat.busy && chat.review!==null")
        self.browser.click('#chatReviewSuggestions input[data-review-index]')
        self.browser.click('#chatApplyReview')
        self.browser.wait("!chat.busy && document.getElementById('chatReviewStatus').textContent.includes('approved')")
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 0)
        self.browser.click('#chatSave'); self.browser.wait("!chat.busy && document.getElementById('chatSaveStatus').textContent.includes('Details saved')")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(cv.name, 'AI browser CV'); self.assertEqual(cv.data['meta']['template_id'], 'classic')
        self.assertEqual(cv.data['personal']['full_name'], 'Ali Khan')
        self.assertEqual(cv.data['summary'], 'Software Engineering graduate with Python and Django skills.')
        self.assertEqual(cv.data['personal']['email'], 'corrected@example.org')

    def test_docx_import_review_correction_and_save(self):
        file = Path(self.files.name) / 'browser.docx'
        document = Document(); document.add_paragraph(json.dumps(SAMPLE_CV)); document.save(file)
        self.browser.click('#importCV'); self.browser.upload('#importFile', file); self.browser.click('#importUpload')
        self.browser.wait("document.getElementById('importModal').dataset.state==='uploaded'")
        self.browser.click('#importExtract'); self.browser.wait("document.getElementById('importModal').dataset.state==='extracted'")
        self.browser.click('#importParse'); self.browser.wait("document.getElementById('importModal').dataset.state==='review'")
        self.browser.value('#importField-personal_full_name', 'Corrected Candidate')
        self.browser.value('#importTemplate', 'developer'); self.browser.click('#importConfirm')
        self.browser.wait("document.getElementById('importModal').dataset.state==='saved'")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(cv.data['personal']['full_name'], 'Corrected Candidate')
        self.assertEqual(cv.data['meta']['template_id'], 'developer')
        self.browser.click('#importEditor'); self.browser.wait("location.pathname.includes('/edit/')")
        self.browser.wait("typeof Alpine!=='undefined' && Alpine.$data(document.querySelector('[x-data]')).loaded!==null")
        self.assertEqual(self.browser.js("return Alpine.$data(document.querySelector('[x-data]')).cv.personal.full_name"), 'Corrected Candidate')

    def test_ai_rewrite_discard_approve_and_persistence(self):
        cv = self.saved_cv(summary='I made APIs using Django.')
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait("!document.getElementById('aiModePart').disabled")
        self.browser.click('#aiModePart')
        self.browser.wait("!document.getElementById('aiRewrite').disabled")
        self.browser.click('#aiRewrite'); self.browser.wait("!document.getElementById('aiApply').disabled")
        self.assertEqual(self.browser.js("return document.getElementById('aiOriginal').value"), 'I made APIs using Django.')
        self.assertEqual(self.browser.js("return document.getElementById('aiRewritten').value"), 'Developed APIs using Django.')
        self.browser.click('#aiDiscard'); cv.refresh_from_db(); self.assertEqual(cv.data['summary'], 'I made APIs using Django.')
        self.browser.click('#aiRewrite'); self.browser.wait("!document.getElementById('aiApply').disabled")
        self.browser.click('#aiApply'); self.browser.wait("/saved/i.test(document.getElementById('aiStatus').textContent)")
        cv.refresh_from_db(); self.assertEqual(cv.data['summary'], 'Developed APIs using Django.')
        self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    def test_whole_cv_tailoring_reviews_every_change_and_saves_one_version(self):
        cv = self.saved_cv(); original = deepcopy(cv.data)
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait("!document.getElementById('aiTailor').disabled")
        self.assertEqual(self.browser.js("return document.getElementById('aiModeWhole').getAttribute('aria-selected')"), 'true')
        self.browser.value('#aiRole', 'Python Django Developer')
        self.browser.value('#aiJob', 'Build maintainable Django applications with Python and PostgreSQL.')
        self.browser.click('#aiTailor')
        self.browser.wait("document.querySelectorAll('#aiTailorChanges .ai-change-card').length===2 && !document.getElementById('aiApply').disabled")
        cv.refresh_from_db(); self.assertEqual(cv.data, original)
        self.assertEqual(cv.version, 1); self.assertEqual(cv.versions.count(), 1)
        comparison = self.browser.js("return document.getElementById('aiTailorChanges').textContent")
        for text in [original['summary'], original['projects'][0]['description'],
                     'Software Engineering graduate building applications with Python and Django.',
                     'Built an employee management system with Django.']:
            self.assertIn(text, comparison)
        self.assertIn('Only include skills you can support.', self.browser.js("return document.getElementById('aiTailorSuggestions').textContent"))
        self.assertEqual(self.browser.js("return [...document.querySelectorAll('#aiTailorChanges .ai-change-check')].every(input=>input.checked)"), True)
        self.browser.click('#aiApply')
        self.browser.wait("/saved 2 changes/i.test(document.getElementById('aiStatus').textContent)")
        cv.refresh_from_db()
        self.assertEqual(cv.data['summary'], 'Software Engineering graduate building applications with Python and Django.')
        self.assertEqual(cv.data['projects'][0]['description'], 'Built an employee management system with Django.')
        self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)
        for section in ('personal', 'skills', 'education', 'experience', 'certifications', 'achievements', 'languages', 'meta'):
            self.assertEqual(cv.data[section], original[section])
        self.assertEqual(cv.data['projects'][0]['highlights'], original['projects'][0]['highlights'])

    def test_whole_cv_provider_retry_preserves_inputs_and_saves_only_selected_change(self):
        from ai.exceptions import AIProviderError
        cv = self.saved_cv(); original = deepcopy(cv.data)
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait("!document.getElementById('aiTailor').disabled")
        role = 'Django Application Developer'
        job = 'Use Python and Django to maintain employee applications. Retry journey.'
        self.browser.value('#aiRole', role); self.browser.value('#aiJob', job)
        with patch.object(IntelligenceProvider, 'generate_structured', side_effect=AIProviderError('Test provider unavailable.')):
            self.browser.click('#aiTailor')
            self.browser.wait("!document.getElementById('aiError').classList.contains('hidden') && !document.getElementById('aiRetry').disabled")
        error = self.browser.js("return document.getElementById('aiError').textContent")
        self.assertIn('temporarily unavailable', error)
        self.assertNotIn('connection', error.lower())
        self.assertTrue(self.browser.js("return document.getElementById('aiStatus').classList.contains('hidden') || document.getElementById('aiStatus').textContent.trim()===''"))
        self.assertEqual(self.browser.js("return document.getElementById('aiRole').value"), role)
        self.assertEqual(self.browser.js("return document.getElementById('aiJob').value"), job)
        cv.refresh_from_db(); self.assertEqual(cv.data, original); self.assertEqual(cv.version, 1)
        self.browser.click('#aiRetry')
        self.browser.wait("document.querySelectorAll('#aiTailorChanges .ai-change-check').length===2 && !document.getElementById('aiApply').disabled")
        self.assertTrue(self.browser.js("return document.getElementById('aiError').classList.contains('hidden')"))
        self.browser.click('#aiTailorChanges .ai-change-check')
        self.browser.click('#aiApply'); self.browser.wait("/saved 1 change/i.test(document.getElementById('aiStatus').textContent)")
        cv.refresh_from_db()
        self.assertEqual(cv.data['summary'], original['summary'])
        self.assertEqual(cv.data['projects'][0]['description'], 'Built an employee management system with Django.')
        self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    @override_settings(GEMINI_API_KEY='test-only-no-real-provider-access', M6_GEMINI_MODEL='browser-synthetic-gemini')
    def test_gemini_sdk_partial_review_accepts_case_changes_and_omits_unconfirmed_skill(self):
        from google.genai import types
        from ai.llm.gemini_client import GeminiProvider

        source = 'software engineering graduate building python/django applications and rest apis.'
        rewritten = 'Software Engineering graduate building Python/Django applications and REST APIs.'
        data = deepcopy(SAMPLE_CV)
        data['skills'] = [skill.lower() for skill in data['skills']]
        project = data['projects'][0]
        project['description'] = project['description'].lower()
        project['technologies'] = [technology.lower() for technology in project['technologies']]
        project['highlights'] = [highlight.lower() for highlight in project['highlights']]
        cv = self.saved_cv(summary=source, data=data); original = deepcopy(cv.data)
        provider_result = {
            'summary': 'Improve clarity while keeping the confirmed development experience.',
            'changes': [
                {'path': '/summary', 'original': source, 'rewritten': rewritten,
                 'reason': 'Use consistent technology capitalization.'},
                {'path': '/projects/0/description', 'original': project['description'],
                 'rewritten': 'Built an employee management system using Django and AWS.',
                 'reason': 'Mention cloud deployment.'},
            ],
            'suggestions': [],
        }
        response = types.GenerateContentResponse(candidates=[types.Candidate(
            content=types.Content(role='model', parts=[types.Part.from_text(text=json.dumps(provider_result))]),
            finish_reason=types.FinishReason.STOP,
        )])
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait("!document.getElementById('aiTailor').disabled")
        self.browser.value('#aiRole', 'Python Django Developer')
        self.browser.value('#aiJob', 'Build Django applications and REST APIs. AWS is useful.')
        self.browser.js("""
            const originalFetch=window.fetch;
            window.tailoringResponseStatuses=[];
            window.fetch=async (...args)=>{
                const result=await originalFetch(...args);
                if(String(args[0]).includes('/api/ai/tailor/')) window.tailoringResponseStatuses.push(result.status);
                return result;
            };
        """)
        with patch('ai.llm.gemini_client.genai.Client') as client_factory:
            generate = client_factory.return_value.models.generate_content
            generate.return_value = response
            with patch('ai.services.tailoring.get_llm_provider', return_value=GeminiProvider()):
                self.browser.click('#aiTailor')
                self.browser.wait("document.querySelectorAll('#aiTailorChanges .ai-change-card').length===1 && !document.getElementById('aiApply').disabled")
            generate.assert_called_once()
            self.assertEqual(generate.call_args.kwargs['config'].response_mime_type, 'application/json')
        self.assertEqual(self.browser.js('return window.tailoringResponseStatuses'), [200])
        self.assertTrue(self.browser.js("return document.getElementById('aiError').classList.contains('hidden')"))
        comparison = self.browser.js("return document.getElementById('aiTailorChanges').textContent")
        self.assertIn(source, comparison); self.assertIn(rewritten, comparison)
        self.assertNotIn('AWS', comparison)
        warning = self.browser.js("return document.getElementById('aiTailorWarnings').textContent")
        self.assertIn('left out', warning); self.assertIn('could not be verified against your CV', warning)
        cv.refresh_from_db(); self.assertEqual(cv.data, original)
        self.assertEqual(cv.version, 1); self.assertEqual(cv.versions.count(), 1)
        self.browser.click('#aiApply')
        self.browser.wait("/saved 1 change/i.test(document.getElementById('aiStatus').textContent)")
        cv.refresh_from_db(); self.assertEqual(cv.data['summary'], rewritten)
        self.assertEqual(cv.data['projects'], original['projects'])
        self.assertEqual(cv.data['skills'], original['skills'])
        self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    def test_ai_engineer_jd_rewrite_rejects_inflation_then_previews_supported_role_focus(self):
        from tests.test_job_focused_writing import ORIGINAL, REPORTED, FOCUSED, JD
        cv = self.saved_cv(summary=ORIGINAL); original = deepcopy(cv.data)
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait('!document.getElementById("aiModePart").disabled')
        self.browser.click('#aiModePart')
        self.browser.value('#aiRole', 'AI Engineer'); self.browser.value('#aiJob', JD)
        with patch.object(IntelligenceProvider, 'generate_structured', side_effect=[
            {'rewritten': REPORTED, 'changes': ['Reworded the summary.']},
            {'rewritten': FOCUSED, 'changes': ['Led with supported AI application work.', 'Kept the stated intern level and proficiency.']},
        ]) as provider:
            self.browser.click('#aiRewrite')
            self.browser.wait('!document.getElementById("aiError").classList.contains("hidden") && !document.getElementById("aiRetry").disabled')
            self.assertIn('could not be verified', self.browser.js('return document.getElementById("aiError").textContent'))
            self.assertEqual(self.browser.js('return document.getElementById("aiJob").value'), JD)
            cv.refresh_from_db(); self.assertEqual(cv.data, original); self.assertEqual(cv.version, 1)
            self.browser.click('#aiRetry')
            self.browser.wait('!document.getElementById("aiApply").disabled && document.getElementById("aiRewritten").value.includes("Builds and tests")')
            self.assertEqual(provider.call_count, 2)
        self.assertEqual(self.browser.js('return document.getElementById("aiOriginal").value'), ORIGINAL)
        self.assertEqual(self.browser.js('return document.getElementById("aiRewritten").value'), FOCUSED)
        cv.refresh_from_db(); self.assertEqual(cv.data, original)
        output = os.environ.get('M6_SCREENSHOTS')
        if output:
            import base64
            root = Path(output); root.mkdir(parents=True, exist_ok=True)
            (root / 'ai-engineer-focused-rewrite.png').write_bytes(base64.b64decode(self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')))
        self.browser.click('#aiApply')
        self.browser.wait('/saved this change/i.test(document.getElementById("aiStatus").textContent)')
        cv.refresh_from_db(); expected = deepcopy(original); expected['summary'] = FOCUSED
        self.assertEqual(cv.data, expected); self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    def test_advice_only_review_has_no_save_action_and_polishing_is_explicit(self):
        data = deepcopy(SAMPLE_CV)
        data['meta']['target_role'] = 'Graduate / Associate Software Engineer'
        cv = self.saved_cv(data=data); original = deepcopy(cv.data)
        response = {'summary': original['summary'], 'changes': [],
            'suggestions': ['Mention cloud or deployment experience only if you have it.']}
        self.reload_dashboard(); self.browser.click('[data-action="intelligence"]')
        self.browser.wait('!document.getElementById("aiTailor").disabled')
        self.browser.value('#aiRole', 'DevOps Engineer')
        with patch.object(IntelligenceProvider, 'generate_structured', return_value=response) as provider:
            self.browser.click('#aiTailor')
            self.browser.wait('!document.getElementById("aiPolishPart").classList.contains("hidden") && !document.getElementById("aiTailor").disabled')
            self.assertEqual(self.browser.js('return getComputedStyle(document.getElementById("aiApply")).display'), 'none')
            self.assertEqual(self.browser.js('return document.getElementById("aiReviewState").textContent'), 'No changes to save')
            summary = self.browser.js('return document.getElementById("aiTailorSummary").textContent')
            self.assertIn('Your saved CV is unchanged', summary)
            self.assertNotIn(original['summary'], summary)
            focus = self.browser.js('return document.getElementById("aiReviewContext").textContent')
            self.assertIn('Review focus: DevOps Engineer', focus)
            self.assertIn('Saved CV target: Graduate / Associate Software Engineer', focus)
            self.browser.click('#aiTailor')
            self.browser.wait('!document.getElementById("aiReviewCache").classList.contains("hidden") && !document.getElementById("aiTailor").disabled')
            provider.assert_called_once()
            for width in (1600, 390):
                self.browser.command(f'/session/{self.browser.session}/window/rect', {'width': width, 'height': 1000})
                self.assertLessEqual(self.browser.js('return document.documentElement.scrollWidth'), self.browser.js('return innerWidth'))
                self.assertTrue(self.browser.js('const card=document.querySelector(".ai-card");return card.scrollWidth <= card.clientWidth'))
                output = os.environ.get('M6_SCREENSHOTS')
                if output:
                    import base64
                    self.browser.js('document.getElementById("aiComparison").scrollIntoView({block:"start",behavior:"instant"})')
                    root = Path(output); root.mkdir(parents=True, exist_ok=True)
                    (root / f'advice-only-{width}.png').write_bytes(base64.b64decode(self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')))
            self.browser.click('#aiPolishPart')
            self.browser.wait('document.getElementById("aiModePart").getAttribute("aria-selected") === "true"')
            provider.assert_called_once()
        cv.refresh_from_db(); self.assertEqual(cv.data, original); self.assertEqual(cv.version, 1)
        rewritten = 'Software Engineering graduate with Python and Django skills.'
        with patch.object(IntelligenceProvider, 'generate_structured', return_value={'rewritten': rewritten, 'changes': ['More concise wording.']}) as provider:
            self.browser.click('#aiRewrite')
            self.browser.wait('!document.getElementById("aiApply").disabled && getComputedStyle(document.getElementById("aiApply")).display !== "none"')
            provider.assert_called_once()
        cv.refresh_from_db(); self.assertEqual(cv.data, original)
        self.browser.click('#aiApply')
        self.browser.wait('/saved this change/i.test(document.getElementById("aiStatus").textContent)')
        cv.refresh_from_db()
        expected = deepcopy(original); expected['summary'] = rewritten
        self.assertEqual(cv.data, expected); self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    def test_devops_partial_review_explains_omissions_and_preserves_architecture(self):
        from tests.test_tailoring_grounding import SUMMARY, ARCHITECTURE, WORKFLOW
        data = deepcopy(SAMPLE_CV)
        data['meta'].update(target_role='Senior DevOps Engineer', career_level='experienced')
        data['summary'] = SUMMARY
        data['experience'] = [{'company': 'Example Cloud', 'job_title': 'DevOps Engineer',
            'location': '', 'start_date': '', 'end_date': '', 'is_current': True,
            'highlights': [ARCHITECTURE, WORKFLOW]}]
        cv = self.saved_cv(data=data); original = deepcopy(cv.data)
        rewritten = WORKFLOW.replace('workflows that eliminated', 'workflows, eliminating').replace(', saving', ' and saving')
        result = {'summary': 'All proposed changes preserve the original facts.', 'suggestions': [], 'changes': [
            {'path': '/summary', 'original': SUMMARY, 'rewritten': SUMMARY.replace('over 7', 'over 10'), 'reason': 'Match the job.'},
            {'path': '/experience/0/highlights/0', 'original': ARCHITECTURE,
             'rewritten': ARCHITECTURE.replace('Architected', 'Built and maintained'), 'reason': 'Match maintenance duties.'},
            {'path': '/experience/0/highlights/1', 'original': WORKFLOW, 'rewritten': rewritten, 'reason': 'Make the wording concise.'},
        ]}
        self.reload_dashboard()
        self.browser.js(r'''
            const originalFetch = window.fetch;
            window.cvDetailReads = 0;
            window.fetch = async (...args) => {
                if (/^\/api\/cvs\/\d+\/$/.test(String(args[0])) && (!args[1]?.method || args[1].method === 'GET')) window.cvDetailReads++;
                return originalFetch(...args);
            };
        ''')
        self.browser.click('[data-action="intelligence"]')
        self.browser.wait('!document.getElementById("aiTailor").disabled')
        for _ in range(3): self.browser.js('window.dispatchEvent(new Event("focus"))')
        self.assertEqual(self.browser.js('return window.cvDetailReads'), 1)
        with patch.object(IntelligenceProvider, 'generate_structured', return_value=result) as provider:
            self.browser.click('#aiTailor')
            self.browser.wait('document.querySelectorAll("#aiTailorChanges .ai-change-card").length === 1 && !document.getElementById("aiApply").disabled')
            provider.assert_called_once()
        self.assertIn('1 wording change is ready', self.browser.js('return document.getElementById("aiStatus").textContent'))
        self.assertIn('1 wording change passed', self.browser.js('return document.getElementById("aiTailorSummary").textContent'))
        self.browser.click('#aiTailorWarnings summary')
        reasons = self.browser.js('return document.getElementById("aiTailorWarnings").textContent')
        self.assertIn('Professional summary: excluded because a number', reasons)
        self.assertIn('Work experience 1, bullet 1', reasons)
        self.assertIn('unsupported responsibility', reasons)
        self.assertEqual(self.browser.js('return window.cvDetailReads'), 2)
        cv.refresh_from_db(); self.assertEqual(cv.data, original)
        output = os.environ.get('M6_SCREENSHOTS')
        if output:
            import base64
            root = Path(output); root.mkdir(parents=True, exist_ok=True)
            (root / 'partial-devops-review.png').write_bytes(base64.b64decode(self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')))
        self.browser.click('#aiApply')
        self.browser.wait('/saved 1 change/i.test(document.getElementById("aiStatus").textContent)')
        cv.refresh_from_db()
        expected = deepcopy(original); expected['experience'][0]['highlights'][1] = rewritten
        self.assertEqual(cv.data, expected)
        self.assertEqual(cv.version, 2); self.assertEqual(cv.versions.count(), 2)

    def test_grouped_education_and_explicit_dates_preserve_the_university(self):
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Grouped education CV'), ('targetRole', 'Frontend Developer'),
                             ('careerLevel', 'experienced'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['My name is Faizan Zafar', 'faizan@example.com', '03154992049', 'Islamabad',
                        'skip', 'skip', 'skip', 'Frontend Developer at bitech', 'Frontend design',
                        'I like to highlight React, Next, Node, Javascript, HTML, CSS',
                        'I completed Bs Software ENgineering from University of Mianwali']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.assertIn('graduate', self.browser.js("return chat.session.messages.at(-1).content"))
        education = self.browser.js("return chat.session.conversation_state.collected_data.education")
        self.assertEqual(education[0]['institution'], 'University of Mianwali')
        self.browser.value('#chatInput', 'start date September 2022 end June 2026'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='projects'")
        education = self.browser.js("return chat.session.conversation_state.collected_data.education")
        self.assertEqual(education[0]['institution'], 'University of Mianwali')
        self.assertEqual((education[0]['start_date'], education[0]['end_date']), ('2022-09', '2026-06'))
        for message in ['E commerce project', 'It displays an e-commerce storefront.', 'React',
                        'Giki ai advance bootcamp issue date agust2026', 'skip', 'English urdu saraiki hindku',
                        'unspecified', 'Frontend developer creating accessible React applications.', 'nothing else']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.assertEqual(self.browser.js("return chat.session.status"), 'completed')
        self.browser.click('#chatSave'); self.browser.wait("!chat.busy && state.cvs.length===1")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(cv.data['education'][0]['institution'], 'University of Mianwali')
        self.assertEqual(cv.data['education'][0]['end_date'], '2026-06')
        self.assertEqual(cv.data['experience'][0]['company'], 'bitech')
        self.assertIn('Next.js', cv.data['skills']); self.assertIn('Node.js', cv.data['skills'])
        self.assertEqual(len(cv.data['languages']), 4)
        self.assertEqual(cv.data['certifications'][0]['date'], '2026-08')

    def test_saved_cv_certificate_offers_finish_and_accepts_no_other_thing(self):
        cv = self.saved_cv('Certificate edit CV'); original = deepcopy(cv.data)
        self.reload_dashboard(); self.browser.click('[data-action="ai"]')
        self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['i want to add another certificate', 'Google Ai prompting Essential']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.assertIn('finish', self.browser.js("return chat.session.messages.at(-1).content"))
        self.browser.value('#chatInput', 'No other thing'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.status==='completed'")
        self.browser.click('#chatSave')
        self.browser.wait("!chat.busy && document.getElementById('chatSaveStatus').textContent.includes('Details saved')")
        cv.refresh_from_db(); self.assertEqual(cv.version, 2)
        self.assertIn('Google Ai prompting Essential', [entry['name'] for entry in cv.data['certifications']])
        for section in ('personal', 'education', 'experience', 'projects', 'skills', 'meta'):
            self.assertEqual(cv.data[section], original[section])

    def test_talha_contact_education_and_project_flow_keeps_one_real_project(self):
        from tests.test_chat_project_flow import TITLE, SUMMARY, DESCRIPTION
        provider_patch = patch.object(ChatProvider, 'generate', return_value=chat_response())
        provider = provider_patch.start(); self.addCleanup(provider_patch.stop)
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Talha project flow'), ('targetRole', 'Backend Developer'),
                             ('careerLevel', 'experienced'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['My full name is Talha', 'talha', 'Talha@example.com', 'g5rtg', '03036096093',
                        'islamabad', 'talhalinkedin.com', 'skip', 'https://github.com/Github-Talha',
                        'https://talha-portfolio.rf.gd/?i=1', 'Backend Developer at Nayatel',
                        'Building sclabable and maintainable backend system',
                        'i want to highlight Django, Flask, Restapi, Django Restframework, HTML, CSS, NODE, NEXT, C++, PROBLEM SOLVING, JAVASCRIPT, FLASK, DJANGO',
                        'i bs software engineering from university of minawali']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
            self.assertEqual(provider.call_count, 0, 'Unexpected extraction for: ' + message)
        self.assertIn('graduate', self.browser.js("return chat.session.messages.at(-1).content"))
        personal = self.browser.js("return chat.session.conversation_state.collected_data.personal")
        self.assertEqual(personal['portfolio'], 'https://talha-portfolio.rf.gd/?i=1')
        self.browser.value('#chatInput', 'start 2022-09 end 2026-06'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='projects'")
        for message in [TITLE, SUMMARY, DESCRIPTION]:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
            self.assertEqual(provider.call_count, 0, 'Unexpected extraction for: ' + message)
        self.assertEqual(self.browser.js("return chat.session.current_section"), 'certifications')
        self.assertEqual(len(self.browser.js("return chat.session.conversation_state.collected_data.projects")), 1)
        for message in ['skip', 'skip', 'skip', 'finish']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.assertEqual(self.browser.js("return chat.session.status"), 'completed')
        self.browser.click('#chatSave'); self.browser.wait("!chat.busy && state.cvs.length===1")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(len(cv.data['projects']), 1)
        self.assertEqual(cv.data['projects'][0]['name'], 'Ai base interview plateform')
        self.assertEqual(cv.data['projects'][0]['description'], DESCRIPTION)
        self.assertEqual(cv.data['summary'], SUMMARY)
        self.assertEqual(cv.data['education'][0]['institution'], 'university of minawali')

    def test_numbered_project_selection_applies_the_pending_description_to_one_entry(self):
        from chatbot.services.conversation_service import create_chat_session
        from tests.test_chat_project_flow import LATEST_DESCRIPTION
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Backend Developer', 'career_level': 'experienced', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {'personal': deepcopy(SAMPLE_CV['personal']), 'skills': ['Python'],
                                  'projects': [{'name': 'Interview platform'}, {'name': 'CV maker'}]}
        state['completed_sections'] = ['personal', 'education', 'experience', 'skills']
        for group in ('personal_fields', 'education_fields', 'experience_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        state['project_fields']['name'] = 'collected'
        session.conversation_state = state; session.current_section = 'projects'; session.save()
        self.browser.click('#resumeChat'); self.browser.wait("document.getElementById('chatSessionsRows').children.length===1")
        self.browser.click('#chatSessionsRows button'); self.browser.wait("chat.session!==null && !chat.busy")
        self.browser.value('#chatInput', LATEST_DESCRIPTION); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        reply = self.browser.js("return chat.session.messages.at(-1).content")
        self.assertIn('1. Interview platform', reply); self.assertIn('2. CV maker', reply)
        self.browser.value('#chatInput', '2'); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        projects = self.browser.js("return chat.session.conversation_state.collected_data.projects")
        self.assertNotIn('description', projects[0]); self.assertEqual(projects[1]['description'], LATEST_DESCRIPTION)
        self.browser.value('#chatInput', 'Python, Django'); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        projects = self.browser.js("return chat.session.conversation_state.collected_data.projects")
        self.assertEqual(projects[1]['technologies'], ['Python', 'Django'])
        self.assertNotIn('technologies', projects[0])

    def test_saved_cv_add_language_preserves_id_and_versions(self):
        cv = self.saved_cv('Language edit CV')
        original = deepcopy(cv.data)
        self.reload_dashboard()
        self.browser.click('[data-action="ai"]'); self.browser.wait("chat.session!==null && !chat.busy")
        self.assertEqual(self.browser.js("return chat.session.current_section"), 'review')
        for message in ['I want to add languages', 'Urdu native', 'finish']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.browser.click('#chatSave')
        self.browser.wait("!chat.busy && document.getElementById('chatSaveStatus').textContent.includes('Details saved')")
        cv.refresh_from_db()
        self.assertEqual(CV.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(cv.version, 2)
        self.assertIn({'name': 'Urdu', 'proficiency': 'native'}, cv.data['languages'])
        for section in ('personal', 'education', 'experience', 'projects', 'skills', 'meta'):
            self.assertEqual(cv.data[section], original[section])

    def test_sequential_education_answers_and_single_validation_message(self):
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Sequential education CV'), ('targetRole', 'Python Developer'),
                             ('careerLevel', 'fresher'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['My full name is abdul quddous', 'shuja@example.com', '03001234567',
                        'Islamabad', 'skip', 'skip', 'skip', 'BS software engineering',
                        'university of MIanwali', 'graduate']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend')
            self.browser.wait("!chat.busy")
        self.assertTrue(self.browser.js("return document.getElementById('chatError').classList.contains('hidden')"))
        self.assertEqual(self.browser.js("return [...document.querySelectorAll('#chatHistory .chat-message-assistant')].filter(node=>node.textContent.includes('Please enter a date as YYYY-MM')).length"), 1)
        self.browser.value('#chatInput', 'i am graduated in 2026'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='skills'")
        education = self.browser.js("return chat.session.conversation_state.collected_data.education")
        self.assertEqual(education, [{'degree': 'BS software engineering', 'institution': 'university of MIanwali',
                                     'field_of_study': 'software engineering', 'end_date': '2026'}])
        self.assertTrue(self.browser.js("return document.getElementById('chatError').classList.contains('hidden')"))

    def test_direct_abuse_keeps_experience_question_without_storing_job_facts(self):
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Conduct browser CV'), ('targetRole', 'Python Developer'),
                             ('careerLevel', 'fresher'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['Ali Khan', 'ali@example.com', '03001234567', 'Islamabad', 'skip', 'skip', 'skip',
                        'BS Software Engineering', 'Example University', '2026-06',
                        'Python, Django', 'Mock Interview System', 'It helps candidates practice interviews.', 'Django, PostgreSQL']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        self.assertEqual(self.browser.js("return chat.session.current_section"), 'experience')
        for message in ['o shutup', 'what a fuck', 'are you idiot']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
            self.assertEqual(self.browser.js("return chat.session.current_section"), 'experience')
            self.assertEqual(self.browser.js("return chat.session.conversation_state.experience_fields.company"), 'missing')
            self.assertEqual(self.browser.js("return chat.session.conversation_state.collected_data.experience || []"), [])
            self.assertIn('professional', self.browser.js("return chat.session.messages.at(-1).content"))
            self.assertTrue(self.browser.js("return document.getElementById('chatError').classList.contains('hidden')"))
        self.browser.value('#chatInput', 'no experience'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='certifications'")
        self.assertEqual(self.browser.js("return chat.session.conversation_state.collected_data.experience || []"), [])

    def test_language_summary_and_late_certificate_are_saved_separately(self):
        from tests.test_chat_optional_sections import SUMMARY, COMBINED
        self.browser.click('#createAI'); self.browser.wait("document.getElementById('templateId').options.length>=3")
        for field, value in [('cvName', 'Optional sections CV'), ('targetRole', 'Python Developer'),
                             ('careerLevel', 'fresher'), ('templateId', 'modern')]:
            self.browser.value('#' + field, value)
        self.browser.click('#createSubmit'); self.browser.wait("chat.session!==null && !chat.busy")
        for message in ['Ali Khan', 'ali@example.com', '03001234567', 'Islamabad', 'skip', 'skip', 'skip',
                        'BS Software Engineering', 'Example University', '2026-06',
                        'Python, Django', 'Mock Interview System', 'It helps candidates practice interviews.',
                        'Django, PostgreSQL', 'no experience', 'skip', 'skip', 'English urdu Hindi']:
            self.browser.value('#chatInput', message); self.browser.click('#chatSend'); self.browser.wait("!chat.busy")
        prompt = self.browser.js("return chat.session.messages.at(-1).content")
        self.assertEqual(prompt.count('?'), 1)
        self.assertIn('proficiency', prompt); self.assertNotIn('summary', prompt)
        self.browser.value('#chatInput', COMBINED); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='review'")
        self.assertEqual(self.browser.js("return chat.session.conversation_state.collected_data.summary"), SUMMARY)
        self.browser.value('#chatInput', 'i wan to add certificate'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='certifications'")
        self.browser.value('#chatInput', 'Python Certificate'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.current_section==='review'")
        self.browser.value('#chatInput', 'fnish'); self.browser.click('#chatSend')
        self.browser.wait("!chat.busy && chat.session.status==='completed'")
        self.browser.click('#chatDraft'); self.browser.wait("!chat.busy && chat.draft!==null")
        self.assertIn('Python Certificate', self.browser.js("return document.getElementById('chatDraftDetails').textContent"))
        self.browser.click('#chatSave'); self.browser.wait("!chat.busy && state.cvs.length===1")
        cv = CV.objects.get(owner=self.user)
        self.assertEqual(cv.data['summary'], SUMMARY)
        self.assertEqual(cv.data['languages'], [{'name': name, 'proficiency': ''} for name in ['English', 'Urdu', 'Hindi']])
        self.assertEqual(cv.data['certifications'][0]['name'], 'Python Certificate')
