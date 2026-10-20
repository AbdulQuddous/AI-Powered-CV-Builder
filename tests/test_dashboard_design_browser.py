"""Opt-in dashboard onboarding, filtering and responsive interaction journeys."""
import base64
import os
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from cvs.models import CV
from cvs.services import create_cv
from m8_renderer.samples import sample_cv
from tests.browser_e2e import Browser


@skipUnless(os.environ.get('RUN_DASHBOARD_BROWSER') == '1', 'Set RUN_DASHBOARD_BROWSER=1 for dashboard design journeys')
class DashboardDesignBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from importlib import import_module
        from django.apps import apps
        import_module('templates_app.migrations.0003_template_gallery').seed_templates(apps, None)
        self.files = tempfile.TemporaryDirectory(prefix='dashboard-design-browser-')
        self.browser = Browser(Path(self.files.name))
        self.user = get_user_model().objects.create_user('dashboard-design@example.com', 'Dashboard-design-Strong-735!')
        b = self.browser
        b.get(self.live_server_url + '/dashboard/')
        b.wait('typeof initializeDashboard === "function" && !document.querySelector("#loginModal").classList.contains("hidden")')
        b.value('#loginEmail', self.user.email)
        b.value('#loginPassword', 'Dashboard-design-Strong-735!')
        b.click('#loginSubmit')
        b.wait('!document.querySelector("#loginModal").classList.contains("hidden") === false && !state.loading')
        b.wait('document.querySelector("#toast").classList.contains("hidden")')
        b.wait('document.fonts.status === "loaded"')

    def tearDown(self):
        self.browser.close()
        self.files.cleanup()

    def screenshot(self, name):
        output = os.environ.get('DASHBOARD_SCREENSHOTS')
        if not output:
            return
        self.browser.wait('document.fonts.status === "loaded" && document.getAnimations().every(animation => animation.playState !== "running")')
        root = Path(output); root.mkdir(parents=True, exist_ok=True)
        if name.startswith('template-picker-'):
            result = self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')
            (root / name).write_bytes(base64.b64decode(result))
            return
        result = self.browser.command(f'/session/{self.browser.session}/goog/cdp/execute', {
            'cmd': 'Page.captureScreenshot', 'params': {'captureBeyondViewport': True, 'fromSurface': True},
        })
        (root / name).write_bytes(base64.b64decode(result['data']))

    def test_empty_onboarding_actions_use_existing_ai_import_and_template_flows(self):
        b = self.browser
        self.assertEqual(b.js('return document.querySelector("#emptyTitle").textContent'), 'Your first CV is waiting')
        self.assertTrue(b.js('return document.querySelector("#emptyIllustration img").complete && document.querySelector("#emptyIllustration img").naturalWidth > 0'))
        self.assertFalse(b.js('return document.querySelector("#emptyActions").classList.contains("hidden")'))
        self.assertEqual(b.js('return document.querySelector("#clearFilters").getClientRects().length'), 0)
        self.assertEqual(b.js('return document.querySelectorAll("a[href=\'/admin/\']").length'), 0)
        b.click('#emptyCreate')
        b.wait('!document.querySelector("#createModal").classList.contains("hidden")')
        self.assertEqual(b.js('return state.createMode'), 'ai')
        self.assertEqual(b.js('return document.querySelector("#createSubmit").textContent'), 'Start AI interview')
        b.click('[data-close="createModal"]')
        b.click('#emptyImport')
        b.wait('!document.querySelector("#importModal").classList.contains("hidden")')
        b.click('[data-close="importModal"]')
        b.click('#heroCreate')
        b.wait('document.querySelector("#templateId").options.length === 50')
        self.assertEqual(b.js('return state.createMode'), 'manual')
        b.click('[data-close="createModal"]')
        self.assertEqual(CV.objects.count(), 0)
        b.click('.dash-template-button')
        b.wait('location.pathname === "/templates/" && document.querySelectorAll(".template-card").length === 12')

    def test_responsive_empty_workspace_and_reduced_motion(self):
        b = self.browser
        for width, height in ((1440, 1100), (1024, 900), (768, 1024), (390, 844), (320, 844)):
            b.command(f'/session/{b.session}/window/rect', {'width': width, 'height': height})
            b.js('scrollTo(0, 0)')
            self.assertLessEqual(b.js('return document.documentElement.scrollWidth'), b.js('return innerWidth'))
            self.assertEqual(b.js('return document.querySelectorAll("h1").length'), 1)
            for selector in ('#emptyCreate', '.dash-template-button', '#createAI', '#heroCreate'):
                self.assertGreaterEqual(b.js('return document.querySelector(arguments[0]).getBoundingClientRect().height', selector), 44)
            self.screenshot(f'dashboard-empty-{width}.png')
        b.command(f'/session/{b.session}/goog/cdp/execute', {
            'cmd': 'Emulation.setEmulatedMedia', 'params': {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]},
        })
        self.assertEqual(b.js('return getComputedStyle(document.querySelector(".dash-welcome")).animationName'), 'none')
        self.assertEqual(b.js('return getComputedStyle(document.querySelector(".dash-ai-button .dash-icon")).animationName'), 'none')
        self.assertEqual(b.js('return getComputedStyle(document.documentElement).scrollBehavior'), 'auto')

    def test_saved_cv_filter_recovery_and_card_navigation(self):
        b = self.browser
        cv = create_cv(user=self.user, values={'name': 'My backend CV', 'data': sample_cv()})
        create_cv(user=self.user, values={'name': 'My research CV', 'data': sample_cv()})
        b.get(self.live_server_url + '/dashboard/')
        b.wait('document.querySelectorAll(".cv-card").length === 2 && !state.loading')
        self.assertEqual(b.js('return document.querySelector("#summaryTotal").textContent'), '2')
        b.command(f'/session/{b.session}/window/rect', {'width': 1440, 'height': 1100})
        self.screenshot('dashboard-saved-1440.png')
        b.value('#searchInput', 'nothing-matches-this')
        self.assertEqual(b.js('return document.querySelector("#emptyTitle").textContent'), 'No matching CVs')
        self.assertTrue(b.js('return document.querySelector("#emptyActions").classList.contains("hidden")'))
        self.assertTrue(b.js('return document.querySelector("#emptyIllustration").classList.contains("hidden")'))
        self.assertEqual(b.js('return document.querySelector("#emptyActions").getClientRects().length'), 0)
        self.assertGreater(b.js('return document.querySelector("#clearFilters").getClientRects().length'), 0)
        self.assertEqual(b.js('return document.querySelector("#summaryTotal").textContent'), '2')
        self.screenshot('dashboard-filtered-1440.png')
        b.click('#clearFilters')
        self.assertEqual(b.js('return document.querySelectorAll(".cv-card").length'), 2)
        self.assertEqual(b.js('return document.activeElement.id'), 'searchInput')
        b.value('#searchInput', 'My backend CV')
        self.assertEqual(b.js('return document.querySelectorAll(".cv-card").length'), 1)
        b.click('[data-action="edit"]')
        b.wait(f'location.pathname === "/cvs/{cv.pk}/edit/"')

    def test_visual_template_preview_filters_and_manual_creation(self):
        b = self.browser
        b.click('#heroCreate')
        b.wait('document.querySelectorAll(".create-template-option").length === 50')
        b.wait('Array.from(document.querySelectorAll(".create-template-thumb img")).slice(0,3).every(img => img.complete && img.naturalWidth > 0)')
        self.assertEqual(b.js('return document.querySelector(".create-template-option").dataset.templateId'), 'modern')
        b.value('#cvName', 'Visual manual CV'); b.value('#targetRole', 'Backend Developer')
        b.value('#careerLevel', 'experienced')
        b.value('#createTemplateSearch', 'ATS Standard')
        search = b.command(f'/session/{b.session}/element', {'using': 'css selector', 'value': '#createTemplateSearch'})
        b.command(f'/session/{b.session}/element/{search["element-6066-11e4-a52e-4f735466cecf"]}/value', {'text': '\ue007'})
        self.assertEqual(CV.objects.count(), 0)
        self.assertFalse(b.js('return document.querySelector("#createModal").classList.contains("hidden")'))
        b.value('#createTemplateSearch', '')
        self.screenshot('template-picker-desktop.png')
        b.click('[data-template-id="ats_standard"] .create-template-preview-button')
        b.wait('document.querySelector("#createTemplatePreviewImage").naturalWidth > 0')
        self.assertEqual(b.js('return document.querySelector("#cvName").value'), 'Visual manual CV')
        self.screenshot('template-picker-large-preview.png')
        b.click('#createTemplateUse')
        self.assertEqual(b.js('return document.querySelector("#templateId").value'), 'ats_standard')
        self.assertTrue(b.js('return document.querySelector("[data-template-id=ats_standard] input").checked'))
        b.value('#createTemplateCategory', 'creative')
        self.assertEqual(b.js('return document.querySelectorAll(".create-template-option").length'), 7)
        self.assertEqual(b.js('return document.querySelector("#templateId").value'), 'ats_standard')
        b.value('#createTemplateSearch', 'not-a-design')
        self.assertFalse(b.js('return document.querySelector("#createTemplateEmpty").classList.contains("hidden")'))
        b.value('#createTemplateSearch', '')
        b.click('#createSubmit')
        b.wait('location.pathname.includes("/edit/")')
        cv = CV.objects.get(name='Visual manual CV')
        self.assertEqual(cv.data['meta']['template_id'], 'ats_standard')
        self.assertEqual(cv.data['meta']['career_level'], 'experienced')

    def test_visual_choice_reaches_ai_interview_without_creating_a_cv(self):
        from chatbot.models import ChatSession
        b = self.browser; b.click('#createAI')
        b.wait('document.querySelectorAll(".create-template-option").length === 50')
        b.value('#cvName', 'Visual AI CV'); b.value('#targetRole', 'Backend Developer')
        b.value('#interviewProfile', 'junior')
        b.value('#createTemplateSearch', 'Horizon')
        self.assertEqual(b.js('return document.querySelectorAll(".create-template-option").length'), 1)
        b.click('[data-template-id="modern_horizon"] .create-template-choice')
        self.assertEqual(b.js('return document.querySelector("#templateId").value'), 'modern_horizon')
        b.click('#createSubmit')
        b.wait('new URL(location.href).searchParams.has("chat")')
        session = ChatSession.objects.get(user=self.user)
        self.assertEqual(session.conversation_state['template_id'], 'modern_horizon')
        self.assertEqual(session.conversation_state['cv_name'], 'Visual AI CV')
        self.assertEqual(session.conversation_state['question_profile'], 'junior')
        self.assertEqual(CV.objects.count(), 0)

    def test_template_loading_retry_retains_details_and_mobile_picker_fits(self):
        b = self.browser
        b.js('window.realPickerFetch=window.fetch; window.fetch=(url,options)=>String(url)==="/api/templates/"?Promise.resolve(new Response("{}",{status:503,headers:{"Content-Type":"application/json"}})):window.realPickerFetch(url,options)')
        b.click('#heroCreate')
        b.wait('!document.querySelector("#createTemplateError").classList.contains("hidden")')
        self.assertEqual(b.js('return document.querySelectorAll(".create-template-option").length'), 1)
        b.value('#cvName', 'Preserved CV'); b.value('#targetRole', 'Designer')
        b.js('window.fetch=window.realPickerFetch')
        b.click('#createTemplateRetry')
        b.wait('document.querySelectorAll(".create-template-option").length === 50')
        self.assertEqual(b.js('return document.querySelector("#cvName").value'), 'Preserved CV')
        self.assertEqual(b.js('return document.querySelector("#targetRole").value'), 'Designer')
        self.assertTrue(b.js('return document.querySelector("#createTemplateError").classList.contains("hidden")'))
        for width in (390, 320):
            b.command(f'/session/{b.session}/window/rect', {'width': width, 'height': 844})
            b.js('document.querySelector("#createTemplatePicker").scrollIntoView({block:"start",behavior:"instant"})')
            self.assertLessEqual(b.js('return document.documentElement.scrollWidth'), b.js('return innerWidth'))
            self.assertTrue(b.js('const card=document.querySelector(".create-cv-card");return card.scrollWidth <= card.clientWidth'))
            self.screenshot(f'template-picker-mobile-{width}.png')
        self.assertEqual(CV.objects.count(), 0)
