"""Opt-in checks of navigation, editing and responsive workspace layouts."""
import base64
import os
import shutil
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from cvs.services import create_cv
from m8_renderer.samples import sample_cv
from tests.browser_e2e import Browser


@skipUnless(os.environ.get('RUN_WORKSPACE_BROWSER') == '1', 'Set RUN_WORKSPACE_BROWSER=1 for Chromium workspace journeys')
class WorkspaceBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = tempfile.TemporaryDirectory(prefix='workspace-test-vendor-')
        root = Path(cls.vendor.name) / 'export-test-libraries'; root.mkdir()
        shutil.copyfile(os.environ['EXPORT_ALPINE_JS'], root / 'alpine.js')
        cls.config = override_settings(STATICFILES_DIRS=[*settings.STATICFILES_DIRS, Path(cls.vendor.name)],
            MIDDLEWARE=[*settings.MIDDLEWARE, 'tests.test_export_parity_browser.EditorLibrariesMiddleware'])
        cls.config.enable(); super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass(); cls.config.disable(); cls.vendor.cleanup()

    def setUp(self):
        from importlib import import_module
        from django.apps import apps
        import_module('templates_app.migrations.0003_template_gallery').seed_templates(apps, None)
        self.files = tempfile.TemporaryDirectory(prefix='workspace-browser-')
        self.browser = Browser(Path(self.files.name))
        self.user = get_user_model().objects.create_user('workspace-browser@example.com')
        self.cv = create_cv(user=self.user, values={'name': 'Frontend developer CV', 'data': sample_cv()})
        self.browser.get(self.live_server_url + '/dashboard/')
        self.browser.wait('typeof M1Session !== "undefined"')
        refresh = RefreshToken.for_user(self.user)
        self.browser.js('M1Session.storeTokens(arguments[0])', {'access': str(refresh.access_token), 'refresh': str(refresh)})

    def tearDown(self):
        self.browser.close(); self.files.cleanup()

    def screenshot(self, name):
        output = os.environ.get('WORKSPACE_SCREENSHOTS')
        if output:
            path = Path(output); path.mkdir(parents=True, exist_ok=True)
            screenshot = self.browser.command(f'/session/{self.browser.session}/screenshot', None, 'GET')
            (path / name).write_bytes(base64.b64decode(screenshot))
            import json
            (path / (name + '.json')).write_text(json.dumps(self.browser.js('return [document.body, ...document.querySelectorAll("button, .workspace-brand")].slice(0,12).map(el => ({label: el === document.body ? "body" : el.textContent.trim().slice(0,80), family: getComputedStyle(el).fontFamily, weight: getComputedStyle(el).fontWeight}))'), indent=2))

    def assert_layout(self, name):
        b = self.browser
        self.assertLessEqual(b.js('return document.documentElement.scrollWidth'), b.js('return innerWidth'))
        self.assertTrue(b.js('return !!document.querySelector(".workspace-nav [aria-current=page]")'))
        colors = b.js('return [getComputedStyle(document.body).backgroundColor, getComputedStyle(document.body).fontFamily, getComputedStyle(document.querySelector(".workspace-nav [aria-current=page]")).backgroundColor]')
        self.screenshot(name)
        return colors

    def test_desktop_navigation_edit_save_and_download_menu(self):
        b = self.browser
        b.command(f'/session/{b.session}/window/rect', {'width': 1440, 'height': 1000})
        b.get(self.live_server_url + '/dashboard/')
        b.wait('document.querySelectorAll(".cv-card").length === 1')
        expected = self.assert_layout('dashboard-desktop.png')
        b.click('[data-action="edit"]')
        b.wait('typeof Alpine !== "undefined" && !!Alpine.$data(document.querySelector("[x-data]")).loaded')
        b.wait('document.querySelector(".m7-live-frame").contentDocument?.body?.textContent.includes("Alex Morgan")')
        self.assertEqual(self.assert_layout('editor-desktop.png'), expected)
        b.value('.m7-edit-form input', 'Jordan Morgan')
        b.wait('!document.querySelector("#save-cv-btn").disabled')
        b.click('#save-cv-btn')
        b.wait('!Alpine.$data(document.querySelector("[x-data]")).dirty')
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.data['personal']['full_name'], 'Jordan Morgan')
        b.click('.workspace-export-menu summary')
        self.assertTrue(b.js('return document.querySelector("#export-docx-btn").getBoundingClientRect().height > 0'))
        b.js('document.querySelector(".workspace-export-menu summary").dispatchEvent(new KeyboardEvent("keydown", {key:"Escape", bubbles:true}))')
        self.assertFalse(b.js('return document.querySelector(".workspace-export-menu").open'))
        b.click('.workspace-nav a[href="/templates/"]')
        b.wait('document.querySelectorAll(".template-card").length === 12')
        self.assertEqual(self.assert_layout('templates-desktop.png'), expected)
        b.click('.workspace-nav .workspace-create')
        b.wait('location.pathname === "/dashboard/" && !document.querySelector("#createModal").classList.contains("hidden")')

    def test_mobile_navigation_forms_and_gallery_fit_the_viewport(self):
        b = self.browser
        for width in (390, 320):
            b.command(f'/session/{b.session}/window/rect', {'width': width, 'height': 844})
            b.get(self.live_server_url + '/dashboard/')
            b.wait('document.querySelectorAll(".cv-card").length === 1')
            expected = self.assert_layout(f'dashboard-{width}.png')
            b.click('#sidebarCreate')
            b.wait('!document.querySelector("#createModal").classList.contains("hidden")')
            self.assert_layout(f'create-{width}.png')
            b.click('[data-close="createModal"]')
            b.click('[data-action="edit"]')
            b.wait('typeof Alpine !== "undefined" && !!Alpine.$data(document.querySelector("[x-data]")).loaded')
            self.assertEqual(self.assert_layout(f'editor-{width}.png'), expected)
            b.click('.m7-section-links button:nth-of-type(2)')
            self.assertEqual(b.js('return Alpine.$data(document.querySelector("[x-data]")).active'), 'summary')
            b.click('.workspace-nav a[href="/templates/"]')
            b.wait('document.querySelectorAll(".template-card").length === 12')
            self.assertEqual(self.assert_layout(f'templates-{width}.png'), expected)
            self.assertEqual(b.js('return getComputedStyle(document.querySelector(".template-grid")).gridTemplateColumns.split(" ").length'), 1)
