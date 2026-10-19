"""PDF layout regressions for whitespace after Projects and chained short entries."""
from copy import deepcopy
from io import BytesIO

from django.test import TestCase
from pypdf import PdfReader

from cvs.validation import validate_document
from m8_renderer.samples import sample_cv
from m8_renderer.services.pdf_exporter import PDFExporter
from tests.test_m8 import SAMPLE_CV


def compact_career_cv():
    """Synthetic content comparable in length to the reported two-page CV."""
    cv = deepcopy(SAMPLE_CV)
    example = sample_cv()
    cv['meta']['target_role'] = 'Software Engineer & Backend Developer'
    cv['summary'] = (
        'Software engineer specializing in practical machine learning applications and reliable backend services. '
        'Develops accessible product features, documents architecture and collaborates with cross-functional teams. '
        'Builds maintainable APIs, relational database systems and asynchronous processing workflows. '
        'Experienced in Python, Django, testing, deployment pipelines and translating user requirements into useful software.')
    job = deepcopy(example['experience'][0])
    job.update(company='Example Systems', job_title='Software Engineer & Backend Developer',
               location='', start_date='', end_date='', is_current=False,
               highlights=['Integrated application features.', 'Developed backend services.'])
    cv['experience'] = [job]
    project = deepcopy(example['projects'][0])
    project.update(name='Community Resource Assistant',
                   description=('Created a conversational assistant that captures background information through an accessible interface '
                                'and maps confirmed user input into structured document objects.'),
                   technologies=['Django', 'REST APIs', 'PostgreSQL'], url='', highlights=[])
    cv['projects'] = [project]
    cv['certifications'] = [{'name': name, 'issuer': '', 'date': '', 'url': ''} for name in (
        'User Experience Design Professional Certificate',
        'Research and Usability Testing Certificate (Example Academy)')]
    cv['achievements'] = [
        'Built and maintained reliable relational databases using PostgreSQL, improving query plans for related application data.',
        'Containerized application services using Docker and documented consistent deployment procedures for cloud environments.',
        'Implemented secure authentication and permissions across third-party REST API integrations and application services.']
    cv['languages'] = [{'name': name, 'proficiency': ''} for name in ('English', 'Urdu', 'French')]
    return validate_document(cv)


class RendererPaginationTests(TestCase):
    def render(self, data, template):
        data = deepcopy(data)
        data['meta']['template_id'] = template
        return PdfReader(BytesIO(PDFExporter.generate({'template_id': template, 'cv_data': data})))

    def test_complete_short_career_fits_one_a4_page_in_original_templates(self):
        for template in ('modern', 'classic', 'developer'):
            with self.subTest(template=template):
                cv = compact_career_cv()
                pdf = self.render(cv, template)
                self.assertEqual(len(pdf.pages), 1)
                text = pdf.pages[0].extract_text(extraction_mode='layout')
                for value in [cv['summary'], cv['projects'][0]['description'], *cv['achievements'],
                              cv['certifications'][-1]['name'], 'French', 'Example University']:
                    self.assertIn(' '.join(value.split()), ' '.join(text.split()))
                self.assertAlmostEqual(float(pdf.pages[0].mediabox.width), 595.28, delta=1)
                self.assertAlmostEqual(float(pdf.pages[0].mediabox.height), 841.89, delta=1)

    def test_optional_title_only_sections_can_fill_available_space_in_new_designs(self):
        cv = compact_career_cv()
        for template in ('ats_standard', 'minimalist_space'):
            with self.subTest(template=template):
                pdf = self.render(cv, template)
                first = pdf.pages[0].extract_text(extraction_mode='layout')
                # An airy design can need two pages, but short certificates and
                # achievements must not all move as one block after Projects.
                for value in [cv['certifications'][0]['name'], cv['achievements'][0]]:
                    self.assertIn(' '.join(value.split()), ' '.join(first.split()))
                self.assertTrue(all(page.extract_text().strip() for page in pdf.pages))

    def test_long_project_uses_remaining_space_and_continues_without_lost_text(self):
        cv = compact_career_cv()
        cv['summary'] = 'Builds reliable applications and documents useful engineering decisions. ' * 12
        cv['projects'][0]['description'] = (
            'Documented accessible services and practical engineering decisions. ' * 65) + 'PROJECT-FINAL-MARKER'
        for template in ('modern', 'classic', 'developer', 'ats_standard'):
            with self.subTest(template=template):
                pdf = self.render(cv, template)
                self.assertGreater(len(pdf.pages), 1)
                first = pdf.pages[0].extract_text(extraction_mode='layout')
                self.assertIn('Community Resource Assistant', first)
                self.assertIn('Documented accessible services', first)
                text = '\n'.join(page.extract_text(extraction_mode='layout') for page in pdf.pages)
                self.assertEqual(text.count('PROJECT-FINAL-MARKER'), 1)
                self.assertIn('French', text)
                self.assertTrue(all(page.extract_text().strip() for page in pdf.pages))
