"""Explicit skill categories remain readable across M7 and all M8 formats."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from docx import Document
from lxml import html
from pypdf import PdfReader

from m8_renderer.samples import sample_cv
from m8_renderer.services.context_builder import build_context
from m8_renderer.services.docx_exporter import DOCXExporter
from m8_renderer.services.pdf_exporter import PDFExporter
from m8_renderer.services.renderer import CVRenderer
from m8_renderer.services.skill_groups import group_skills
from templates_app.catalogue import catalogue


FIXTURES = json.loads((Path(__file__).parent / 'fixtures/skill_groups.json').read_text())


def by_class(node, value):
    return node.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), concat(" ", $value, " "))]', value=value)


class SkillGroupParsingTests(SimpleTestCase):
    def test_shared_browser_and_server_cases_preserve_input_and_group_only_explicit_labels(self):
        for fixture in FIXTURES:
            with self.subTest(case=fixture['name']):
                before = deepcopy(fixture['skills'])
                self.assertEqual(group_skills(fixture['skills']), fixture['groups'])
                context = build_context({'skills': fixture['skills']})
                self.assertEqual(context['skills'], before)
                self.assertEqual(context['skill_groups'], fixture['groups'])
                self.assertEqual(fixture['skills'], before)

    def test_editor_explains_optional_grouping(self):
        response = self.client.get('/cvs/1/edit/')
        self.assertContains(response, 'Each category appears on its own row with a bold label')


class SkillGroupRenderingTests(TestCase):
    def payload(self, template='ats_chronicle', fixture=0):
        data = sample_cv()
        data['skills'] = deepcopy(FIXTURES[fixture]['skills'])
        data['meta']['template_id'] = template
        return {'template_id': template, 'cv_data': data}

    def test_all_fifty_templates_use_separate_bold_rows_and_keep_every_skill(self):
        for template in catalogue():
            with self.subTest(template=template):
                payload = self.payload(template)
                before = deepcopy(payload)
                markup = html.fromstring(CVRenderer.render_html(payload))
                rows = by_class(markup, 'skill-group')
                self.assertEqual(len(rows), 4)
                for row, expected in zip(rows, FIXTURES[0]['groups']):
                    self.assertEqual(row.find('strong').text, expected['label'] + ':')
                    self.assertEqual(row.find('span').text, ', '.join(expected['items']))
                self.assertFalse(by_class(by_class(markup, 'skill-groups')[0], 'skill'))
                self.assertEqual(payload, before)

    def test_flat_skills_still_use_tags_or_inline_styles_without_invented_categories(self):
        for template in ('modern', 'ats_chronicle', 'modern_horizon'):
            markup = html.fromstring(CVRenderer.render_html(self.payload(template, fixture=2)))
            self.assertFalse(by_class(markup, 'skill-group'))
            self.assertEqual(' '.join(by_class(markup, 'skills')[0].itertext()).count('Django'), 2)

    def test_markup_in_group_labels_and_values_remains_plain_text(self):
        payload = self.payload()
        payload['cv_data']['skills'] = ['Custom <img src=x>: <script>alert(1)</script>, Git']
        markup = html.fromstring(CVRenderer.render_html(payload))
        self.assertFalse(markup.xpath('.//script | .//img'))
        self.assertIn('Custom <img src=x>:', by_class(markup, 'skill-group')[0].text_content())
        self.assertIn('<script>alert(1)</script>', by_class(markup, 'skill-group')[0].text_content())

    def test_pdf_uses_distinct_category_lines_in_original_ats_tag_and_sidebar_designs(self):
        for template in ('modern', 'ats_chronicle', 'modern_horizon', 'professional_meridian'):
            with self.subTest(template=template):
                pdf = PdfReader(BytesIO(PDFExporter.generate(self.payload(template))))
                text = '\n'.join(page.extract_text(extraction_mode='layout') for page in pdf.pages)
                # Preserve PDF content order: layout mode interleaves adjacent
                # columns, which is useful visually but breaks phrase searches.
                normalized = ' '.join(('\n'.join(page.extract_text() for page in pdf.pages)).split())
                for group in FIXTURES[0]['groups']:
                    self.assertIn(group['label'] + ':', normalized)
                    for skill in group['items']:
                        self.assertIn(skill, normalized)
                if template in ('modern', 'ats_chronicle'):
                    for group in FIXTURES[0]['groups']:
                        self.assertTrue(any(line.lstrip().startswith(group['label'] + ':') for line in text.splitlines()))
                self.assertTrue(all(page.extract_text().strip() for page in pdf.pages))

    def test_editable_word_matches_reference_with_bold_labels_and_regular_values(self):
        document = Document(BytesIO(DOCXExporter.generate(self.payload())))
        for expected in FIXTURES[0]['groups']:
            row = next(p for p in document.paragraphs if p.text.startswith(expected['label'] + ':'))
            self.assertEqual(row.text, expected['label'] + ': ' + ', '.join(expected['items']))
            self.assertTrue(row.runs[0].bold)
            self.assertFalse(row.runs[1].bold)

    def test_large_group_can_continue_across_pages_without_lost_skills(self):
        payload = self.payload()
        payload['cv_data']['skills'] = ['Specialist skills:'] + [
            f'Specialist skill {index:02d} with practical application and testing' for index in range(99)]
        pdf = PdfReader(BytesIO(PDFExporter.generate(payload)))
        self.assertGreater(len(pdf.pages), 1)
        # PDF list markers from earlier sections may be emitted at page end,
        # between the two halves of a continued paragraph in extraction order.
        text = ' '.join(('\n'.join(page.extract_text() for page in pdf.pages)).replace('•', '').split())
        self.assertEqual(text.count('Specialist skills:'), 1)
        for skill in payload['cv_data']['skills'][1:]:
            self.assertEqual(text.count(skill), 1)
        self.assertTrue(all(page.extract_text().strip() for page in pdf.pages))
