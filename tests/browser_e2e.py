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
        for name in ('alpine.js', 'tailwind.js'):
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
            for service in ('extraction', 'analysis', 'writing', 'final_review')]
        for patcher in self.patchers: patcher.start(); self.addCleanup(patcher.stop)
        self.browser.get(self.live_server_url + '/dashboard/')
        self.browser.wait("document.getElementById('loginModal') && !document.getElementById('loginModal').classList.contains('hidden')")
        self.browser.value('#loginEmail', 'browser@example.com'); self.browser.value('#loginPassword', 'Browser-Strong-735!')
        self.browser.click('#loginSubmit')
        self.browser.wait("document.getElementById('loginModal').classList.contains('hidden') && !state.loading")

    def saved_cv(self, name='Browser CV', summary=None):
        from cvs.services import create_cv
        data = deepcopy(SAMPLE_CV)
        if summary: data['summary'] = summary
        return create_cv(user=self.user, values={'name': name, 'data': data})

    def reload_dashboard(self):
        self.browser.get(self.live_server_url + '/dashboard/')
        self.browser.wait("typeof state!=='undefined' && !state.loading && !document.getElementById('loginModal').classList.contains('hidden')===false")



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
