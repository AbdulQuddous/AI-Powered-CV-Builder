"""The real dashboard choices must create valid manual and AI drafts."""
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from cvs.models import CV
from shared.enums.career_level import CareerLevel


class CareerOptionsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_career_select = False
        self.options = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.in_career_select = attrs.get('id') == 'careerLevel'
        elif tag == 'option' and self.in_career_select:
            self.options.append(attrs.get('value'))

    def handle_endtag(self, tag):
        if tag == 'select':
            self.in_career_select = False


class CVCreationFormTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('create-form@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)

    def career_options(self):
        parser = CareerOptionsParser()
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        parser.feed(response.content.decode())
        self.assertEqual(parser.options, [level.value for level in CareerLevel])
        return parser.options

    def test_every_rendered_career_and_template_selection_creates_manual_cv(self):
        templates = self.client.get('/api/templates/').data
        templates = templates.get('results', templates) if isinstance(templates, dict) else templates
        self.assertTrue(templates)
        for level in self.career_options():
            for template in templates:
                with self.subTest(level=level, template=template['id']):
                    response = self.client.post('/api/cvs/', {
                        'name': 'Selected manual CV', 'target_role': 'Python Developer',
                        'career_level': level, 'template_id': template['id'], 'data': {},
                    }, format='json')
                    self.assertEqual(response.status_code, 201, response.data)
                    self.assertEqual(response.data['career_level'], level)
                    self.assertEqual(response.data['template_id'], template['id'])
                    self.assertEqual(response.data['version'], 1)

    def test_every_rendered_career_selection_starts_ai_without_saving_cv(self):
        for level in self.career_options():
            with self.subTest(level=level):
                response = self.client.post('/api/chat/sessions/', {
                    'cv_name': 'Selected AI CV', 'target_role': 'Python Developer',
                    'career_level': level, 'template_id': 'modern',
                }, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                session = ChatSession.objects.get(pk=response.data['id'])
                self.assertEqual(session.conversation_state['career_level'], level)
        self.assertEqual(CV.objects.count(), 0)

    def test_legacy_dropdown_values_create_canonical_manual_cv(self):
        for level in ['junior', 'mid']:
            response = self.client.post('/api/cvs/', {
                'name': 'Legacy form CV', 'target_role': 'Developer', 'career_level': level,
                'template_id': 'modern', 'data': {},
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['career_level'], 'experienced')
            self.assertEqual(response.data['data']['meta']['career_level'], 'experienced')

    def test_legacy_ai_dropdown_preserves_metadata_and_junior_profile(self):
        for level in ['junior', 'mid']:
            response = self.client.post('/api/chat/sessions/', {
                'cv_id': None, 'cv_name': 'Legacy AI CV', 'target_role': 'Python Developer',
                'career_level': level, 'template_id': 'classic',
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            session = ChatSession.objects.get(pk=response.data['id'])
            state = session.conversation_state
            self.assertEqual(state['career_level'], 'experienced')
            self.assertEqual(state['cv_name'], 'Legacy AI CV')
            self.assertEqual(state['target_role'], 'Python Developer')
            self.assertEqual(state['template_id'], 'classic')
            if level == 'junior':
                self.assertEqual(state['question_profile'], 'junior')
        self.assertEqual(CV.objects.count(), 0)

    def test_unknown_value_is_reported_as_field_error_without_writes(self):
        for level in ['invalid-level', {'level': 'junior'}]:
            response = self.client.post('/api/cvs/', {
                'name': 'Invalid CV', 'target_role': 'Developer', 'career_level': level,
                'template_id': 'modern', 'data': {},
            }, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('career_level', response.data['error']['details'])
        self.assertEqual(CV.objects.count(), 0)
