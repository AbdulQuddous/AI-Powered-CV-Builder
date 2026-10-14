from django.template.loader import render_to_string
from django.test import SimpleTestCase

from m8_renderer.services.context_builder import build_context


class EditorLivePreviewTests(SimpleTestCase):
    def test_editor_loads_live_preview_assets_and_sandboxed_frame(self):
        response = self.client.get('/cvs/11/edit/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'm7_editor/js/live_preview.js')
        self.assertContains(response, 'm7_editor/css/live_preview.css')
        self.assertContains(response, 'title="Live A4 CV preview"')
        self.assertContains(response, 'sandbox="allow-same-origin"')
        self.assertContains(response, 'aria-label="Preview zoom"')
        self.assertContains(response, 'Fit width')
        self.assertContains(response, '125%')
        self.assertContains(response, "isDateField(key) ? 'month' : 'text'")
        self.assertContains(response, '@click="selectSection(pair[0])"')
        self.assertNotContains(response, 'Not PDF layout')

    def test_all_existing_templates_use_a4_screen_and_print_styles(self):
        context = build_context({'personal': {'full_name': '<script>alert(1)</script>'}})
        for theme in ['modern', 'classic', 'developer']:
            with self.subTest(theme=theme):
                markup = render_to_string(f'cv_templates/{theme}.html', context)
                self.assertIn(f'body class="theme-{theme}"', markup)
                self.assertIn('width: 210mm;', markup)
                self.assertIn('min-height: 297mm;', markup)
                self.assertIn('size: A4;', markup)
                self.assertIn('margin: 14mm;', markup)
                self.assertIn('&lt;script&gt;', markup)
                self.assertNotIn('<script>alert', markup)
