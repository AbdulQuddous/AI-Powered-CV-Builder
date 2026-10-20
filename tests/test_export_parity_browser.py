"""Opt-in browser verification of actual page previews and both download modes."""
import base64
import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest import skipUnless
from zipfile import ZipFile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from pypdf import PdfReader
from rest_framework_simplejwt.tokens import RefreshToken

from cvs.services import create_cv
from m8_renderer.samples import sample_cv
from tests.browser_e2e import Browser


class EditorLibrariesMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if response.get('Content-Type', '').startswith('text/html'):
            response.content = response.content.decode().replace(
                'https://cdn.jsdelivr.net/npm/alpinejs@3.17.4/dist/cdn.min.js', '/static/export-test-libraries/alpine.js').encode()
            response['Content-Length'] = len(response.content)
        return response


@skipUnless(os.environ.get('RUN_EXPORT_BROWSER') == '1', 'Set RUN_EXPORT_BROWSER=1 for Chromium export checks')
class ExportParityBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = tempfile.TemporaryDirectory(prefix='export-test-vendor-')
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
        self.files = tempfile.TemporaryDirectory(prefix='export-browser-')
        self.browser = Browser(Path(self.files.name))
        self.user = get_user_model().objects.create_user('export-browser@example.com')

    def tearDown(self):
        self.browser.close(); self.files.cleanup()

    def journey(self, data, name):
        b = self.browser
        cv = create_cv(user=self.user, values={'name': name, 'data': data})
        b.get(self.live_server_url + f'/cvs/{cv.pk}/edit/')
        b.wait('typeof M1Session !== "undefined"')
        token = RefreshToken.for_user(self.user)
        b.js('M1Session.storeTokens(arguments[0])', {'access': str(token.access_token), 'refresh': str(token)})
        b.get(self.live_server_url + f'/cvs/{cv.pk}/edit/')
        b.wait('typeof Alpine !== "undefined" && Alpine.$data(document.querySelector("[x-data]")).loaded !== null')
        from m8_renderer.services.context_builder import build_context
        expected_groups = build_context(data)['skill_groups']
        if expected_groups:
            b.wait(f'document.querySelector(".m7-live-frame").contentDocument?.querySelectorAll(".skill-group").length === {len(expected_groups)}')
            rows = b.js('''return Array.from(document.querySelector('.m7-live-frame').contentDocument.querySelectorAll('.skill-group')).map(row => ({
                label: row.querySelector('strong')?.textContent || '',
                values: row.querySelector('.skill-group-values').textContent,
                bold: row.ownerDocument.defaultView.getComputedStyle(row.querySelector('strong')).fontWeight,
                top: row.getBoundingClientRect().top,
                fits: row.scrollWidth <= row.clientWidth + 1
            }))''')
            self.assertEqual([row['label'] for row in rows], [group['label'] + ':' for group in expected_groups])
            self.assertEqual([row['values'] for row in rows], [', '.join(group['items']) for group in expected_groups])
            self.assertTrue(all(int(row['bold']) >= 600 and row['fits'] for row in rows))
            self.assertEqual([row['top'] for row in rows], sorted(set(row['top'] for row in rows)))
        b.click('#preview-cv-btn')
        b.wait('Alpine.$data(document.querySelector("[x-data]")).m8PreviewOpen')
        # The production iframe has an opaque sandbox origin. WebDriver enters
        # the frame directly; application scripts do not gain access to it.
        frame = b.command(f'/session/{b.session}/element', {'using': 'css selector', 'value': '.m8-viewer__iframe'})
        b.command(f'/session/{b.session}/frame', {'id': frame})
        b.wait('document.querySelectorAll(".pdf-page").length > 0')
        b.wait('document.querySelector(".pdf-page img").complete && document.querySelector(".pdf-page img").naturalWidth > 0')
        count = b.js('return document.querySelectorAll(".pdf-page").length')
        b.command(f'/session/{b.session}/frame', {'id': None})
        self.assertIn(str(count) + ' A4 page', b.js('return document.querySelector(".m8-viewer__title p").textContent'))
        b.click('.m8-viewer__button--primary')
        target = Path(self.files.name) / f'cv-{cv.pk}.pdf'
        import time
        deadline = time.monotonic() + 15
        while not target.exists() and time.monotonic() < deadline: time.sleep(.05)
        self.assertTrue(target.exists()); self.assertEqual(len(PdfReader(target).pages), count)
        b.wait('!Alpine.$data(document.querySelector("[x-data]")).m8Busy')
        b.click('.m8-viewer__actions button:nth-of-type(2)')
        target = Path(self.files.name) / f'cv-{cv.pk}.docx'
        deadline = time.monotonic() + 15
        while not target.exists() and time.monotonic() < deadline: time.sleep(.05)
        self.assertTrue(target.exists())
        with ZipFile(target) as archive:
            from lxml import etree
            xml = etree.fromstring(archive.read('docProps/app.xml'))
            self.assertEqual(xml.find('{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Pages').text, str(count))
        output = os.environ.get('EXPORT_SCREENSHOTS')
        if output:
            path = Path(output); path.mkdir(parents=True, exist_ok=True)
            screenshot = b.command(f'/session/{b.session}/screenshot', None, 'GET')
            (path / (name + '.png')).write_bytes(base64.b64decode(screenshot))
        return count

    def test_one_page_preview_and_downloads_match(self):
        data = sample_cv(); data['meta']['template_id'] = 'modern_current'
        self.assertEqual(self.journey(data, 'one-page-preview'), 1)

    def test_multiple_page_preview_and_downloads_match(self):
        data = sample_cv(); data['meta']['template_id'] = 'modern_current'
        data['summary'] = ('Builds dependable services and shares engineering knowledge. ' * 65)
        data['projects'] *= 5
        self.assertGreater(self.journey(data, 'multiple-page-preview'), 1)

    def test_grouped_skills_match_live_preview_and_both_downloads(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures/skill_groups.json').read_text())
        data = sample_cv()
        data['meta']['template_id'] = 'ats_chronicle'
        data['skills'] = fixtures[0]['skills']
        self.assertGreaterEqual(self.journey(data, 'grouped-skills-preview'), 1)
