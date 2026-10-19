"""Opt-in Chromium journeys; no external libraries or AI providers are needed."""
import base64
import os
import tempfile
from pathlib import Path
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from rest_framework_simplejwt.tokens import RefreshToken
from cvs.services import create_cv
from cvs.models import CV
from m8_renderer.samples import sample_cv
from tests.browser_e2e import Browser


@skipUnless(os.environ.get('RUN_GALLERY_BROWSER') == '1', 'Set RUN_GALLERY_BROWSER=1 to run real Chromium')
class GalleryBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from importlib import import_module
        from django.apps import apps
        import_module('templates_app.migrations.0003_template_gallery').seed_templates(apps, None)
        self.tmp = tempfile.TemporaryDirectory(prefix='gallery-browser-')
        self.browser = Browser(Path(self.tmp.name))
        self.user = get_user_model().objects.create_user('browser-gallery@example.com')

    def tearDown(self):
        self.browser.close(); self.tmp.cleanup()

    def sign_in(self):
        refresh = RefreshToken.for_user(self.user)
        self.browser.js('M1Session.storeTokens(arguments[0])', {'access': str(refresh.access_token), 'refresh': str(refresh)})

    def shot(self, name):
        output = os.environ.get('GALLERY_SCREENSHOTS')
        if output:
            path = Path(output); path.mkdir(parents=True, exist_ok=True)
            result = self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')
            (path / name).write_bytes(base64.b64decode(result))

    def test_desktop_filter_search_pagination_preview_and_manual_creation(self):
        b = self.browser; b.get(self.live_server_url + '/templates/')
        b.wait('document.querySelectorAll(".template-card").length === 12')
        self.assertEqual(b.js('return getComputedStyle(document.querySelector(".template-grid")).gridTemplateColumns.split(" ").length'), 3)
        b.wait('Array.from(document.querySelectorAll(".thumbnail-button img")).slice(0,3).every(img => img.complete && img.naturalWidth > 0)')
        self.shot('gallery-desktop.png')
        b.js('document.querySelector("#templateGrid").scrollIntoView({block:"start"})')
        self.shot('gallery-cards.png')
        for count in (24, 36, 48, 50):
            b.click('#loadMoreTemplates'); b.wait(f'document.querySelectorAll(".template-card").length === {count}')
        self.assertTrue(b.js('return document.querySelector("#loadMoreTemplates").hidden'))
        b.click('[data-category="ats"]'); b.wait('document.querySelectorAll(".template-card").length === 7')
        self.assertEqual(b.js('return document.querySelectorAll(".ats-badge").length'), 7)
        b.value('#templateSearch', 'not-a-template'); b.wait('document.querySelectorAll(".template-card").length === 0 && document.querySelector("#templateGrid").getAttribute("aria-busy") === "false"')
        self.assertIn('No designs', b.js('return document.querySelector("#galleryStatus").textContent'))
        b.click('#resetFilters'); b.wait('document.querySelectorAll(".template-card").length === 12')
        b.value('#templateSearch', 'Horizon'); b.wait('document.querySelectorAll(".template-card").length === 1')
        b.click('.thumbnail-button'); b.wait('document.querySelector("#templateFrame").contentDocument?.querySelector(".layout") !== null && document.querySelector("#templateFrame").contentDocument?.body?.textContent.includes("Alex Morgan")')
        b.value('#previewZoom', '1.25'); self.assertIn('1.25', b.js('return document.querySelector("#templateFrame").style.transform'))
        self.shot('gallery-preview.png'); b.click('#closePreview')
        self.sign_in(); b.click('.card-actions .primary-button')
        b.value('#galleryCVName', 'Browser Manual CV'); b.value('#galleryTargetRole', 'Backend Developer')
        b.click('#confirmUseTemplate'); b.wait('location.pathname.includes("/edit/")')
        cv = CV.objects.get(name='Browser Manual CV'); self.assertEqual(cv.data['meta']['template_id'], 'modern_horizon')

    def test_mobile_private_preview_and_versioned_switch(self):
        cv = create_cv(user=self.user, values={'name': 'Browser existing CV', 'data': sample_cv()})
        b = self.browser
        b.command(f'/session/{b.session}/window/rect', {'width': 390, 'height': 844})
        b.get(self.live_server_url + '/templates/'); self.sign_in()
        b.get(self.live_server_url + f'/templates/?cv_id={cv.pk}')
        b.wait(f'document.querySelector("#previewData").value === "{cv.pk}"')
        b.wait('document.querySelectorAll(".template-card").length === 12')
        self.assertLessEqual(b.js('return document.documentElement.scrollWidth'), b.js('return window.innerWidth'))
        self.assertEqual(b.js('return getComputedStyle(document.querySelector(".template-grid")).gridTemplateColumns.split(" ").length'), 1)
        self.shot('gallery-mobile.png')
        b.value('#templateSearch', 'Studio'); b.wait('document.querySelectorAll(".template-card").length === 1')
        b.click('.thumbnail-button'); b.wait('document.querySelector("#templateFrame").contentDocument?.body?.textContent.includes("Alex Morgan")')
        self.assertIn('Private preview', b.js('return document.querySelector("#previewStatus").textContent'))
        b.click('#previewUse'); b.wait('!document.querySelector("#confirmUseTemplate").disabled')
        b.click('#confirmUseTemplate'); b.wait('location.pathname.includes("/edit/")')
        cv.refresh_from_db(); self.assertEqual(cv.data['meta']['template_id'], 'creative_studio')
        self.assertEqual(cv.version, 2); self.assertEqual(CV.objects.count(), 1)
        expected = sample_cv(); expected['meta']['template_id'] = 'creative_studio'
        self.assertEqual(cv.data, expected)

    def test_ai_creation_handoff_preserves_selected_metadata_and_resumes_chat(self):
        from chatbot.models import ChatSession
        b = self.browser; b.get(self.live_server_url + '/templates/'); self.sign_in()
        b.wait('document.querySelectorAll(".template-card").length === 12')
        b.value('#templateSearch', 'Vector'); b.wait('document.querySelectorAll(".template-card").length === 1')
        b.click('.card-actions .primary-button')
        b.value('#galleryCVName', 'Browser AI CV'); b.value('#galleryTargetRole', 'Data Analyst')
        b.value('#galleryCareerLevel', 'experienced'); b.value('#galleryCreationMode', 'ai')
        b.click('#confirmUseTemplate')
        b.wait('location.pathname === "/dashboard/" && document.querySelector("#templateId")?.value === "modern_vector"')
        self.assertEqual(b.js('return document.querySelector("#targetRole").value'), 'Data Analyst')
        self.assertEqual(b.js('return document.querySelector("#careerLevel").value'), 'experienced')
        self.assertEqual(b.js('return document.querySelector("#cvName").value'), 'Browser AI CV')
        # Use the real form event without depending on the dashboard CDN stylesheet.
        b.js('document.querySelector("#createForm").requestSubmit()')
        b.wait('new URL(location.href).searchParams.has("chat")')
        session = ChatSession.objects.get(user=self.user)
        self.assertEqual(session.conversation_state['template_id'], 'modern_vector')
        self.assertEqual(session.conversation_state['target_role'], 'Data Analyst')
        self.assertEqual(session.conversation_state['career_level'], 'experienced')
        self.assertNotIn('create=', b.js('return location.search'))
        self.assertEqual(CV.objects.count(), 0)
