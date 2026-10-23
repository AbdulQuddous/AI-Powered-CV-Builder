"""Regression coverage for pasted UI/UX CV details and the graduation-date loop."""
import json
from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.education_answers import parse_education
from chatbot.services.field_validation import extract_skills, validate_value
from chatbot.services.question_engine import next_step
from tests.test_m8 import SAMPLE_CV

EDUCATION = '"institution": "University of California, Berkeley", "degree": "Bachelor of Science in Cognitive Science", "specialization": "Human-Computer Interaction (HCI) Concentration", "graduation_year": "2020"'
EXPECTED = {'institution': 'University of California, Berkeley', 'degree': 'Bachelor of Science in Cognitive Science',
            'field_of_study': 'Human-Computer Interaction (HCI) Concentration', 'end_date': '2020'}
GROUPS = {'ux_research': ['User Persona Creation', 'Information Architecture', 'Wireframing', 'User Journey Mapping', 'Usability Testing', 'A/B Testing'],
          'ui_design': ['Visual Design', 'Mobile App Design (iOS/Android)', 'Responsive Web Design', 'Design Systems', 'Interactive Prototyping'],
          'tools': ['Figma', 'Adobe XD', 'Sketch', 'Miro', 'Principle', 'Jira', 'Zeplin']}


class PastedAnswerParsingTests(SimpleTestCase):
    def test_complete_education_fragment_and_wrapped_json_have_all_explicit_facts(self):
        for text in [EDUCATION, '{' + EDUCATION + '}', '```json\n{' + EDUCATION + '}\n```']:
            with self.subTest(text=text): self.assertEqual(parse_education(text, 'degree'), EXPECTED)

    def test_dates_accept_the_reported_typo_and_labelled_year(self):
        for text, expected in [('i graduted in 2022-06', '2022-06'), ('I graduated in 2022-06', '2022-06'),
                               ('raduation_year": "2020"', '2020'), ('"graduation_year": "2020"', '2020')]:
            with self.subTest(text=text): self.assertEqual(parse_education(text, 'end_date'), {'end_date': expected})

    def test_grouped_json_skills_contain_values_without_property_names_or_syntax(self):
        expected = [item for group in GROUPS.values() for item in group]
        for text in [json.dumps(GROUPS), json.dumps(GROUPS)[1:-1], json.dumps({'skills': GROUPS})]:
            with self.subTest(text=text): self.assertEqual(extract_skills(text), expected)

    def test_contacts_validate_format_without_claiming_delivery_or_ownership(self):
        self.assertEqual(validate_value('email', '12qud@gmail.com'), '12qud@gmail.com')
        self.assertEqual(validate_value('phone', '03036098766'), '03036098766')
        for field, value in [('email', '12qud@gmail'), ('email', '12qud@@gmail.com'),
                             ('phone', '+1 (555) 019-2834'), ('phone', '+999123456789')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError): validate_value(field, value)

    def test_a_url_is_not_a_company_or_degree(self):
        for field in ('company', 'degree', 'institution'):
            with self.subTest(field=field), self.assertRaises(ValidationError): validate_value(field, 'https://linkedin.com')


class PastedDetailsJourneyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('pasted-details@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        provider = patch('chatbot.services.conversation_service.QwenClient.generate',
                         side_effect=AssertionError('Explicit pasted facts must not require provider guesses'))
        provider.start(); self.addCleanup(provider.stop)

    def start(self, section='education', field='degree'):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Senior UI/UX Designer', 'career_level': 'experienced', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {'personal': deepcopy(SAMPLE_CV['personal']), 'skills': ['Figma']}
        state['personal_fields'] = dict.fromkeys(state['personal_fields'], 'collected')
        state['experience_fields'] = dict.fromkeys(state['experience_fields'], 'collected')
        state['completed_sections'] = ['personal', 'experience', 'skills']
        state['pending_field'] = {'section': section, 'field': field}
        session.conversation_state = state; session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data); session.refresh_from_db()
        return result.data

    def test_complete_education_answer_skips_questions_for_already_supplied_fields(self):
        session = self.start(); result = self.send(session, EDUCATION)
        self.assertEqual(session.conversation_state['collected_data']['education'], [EXPECTED])
        self.assertEqual(result['section'], 'projects')
        self.assertNotIn('Which institution', result['assistant_message'])

    def test_typo_date_answer_updates_one_entry_and_finishes_education(self):
        for text in ['2022-06', 'i graduted in 2022-06']:
            with self.subTest(text=text):
                session = self.start(); self.send(session, 'Bachelor of Science in Cognitive Science')
                self.send(session, 'University of California, Berkeley')
                result = self.send(session, text)
                self.assertEqual(result['section'], 'projects')
                self.assertEqual(len(session.conversation_state['collected_data']['education']), 1)
                self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], '2022-06')

    def broken_session(self, history=True):
        session = self.start(field='end_date')
        state = session.conversation_state
        state['collected_data']['education'] = [
            {'degree': EDUCATION, 'institution': EXPECTED['institution']},
            {'degree': EXPECTED['degree'], 'field_of_study': 'Cognitive Science'}]
        state['education_fields'].update(degree='collected', institution='collected', field_of_study='collected', end_date='missing')
        session.save()
        if history:
            ChatMessage.objects.create(session=session, role='user', content=EDUCATION)
            ChatMessage.objects.create(session=session, role='assistant', content='Which institution?', cv_updates={'education': [{'degree': EDUCATION}]})
        return session

    def test_existing_reported_loop_recovers_from_accepted_source_evidence(self):
        session = self.broken_session(); result = self.send(session, 'i graduted in 2022-06')
        self.assertEqual(result['section'], 'projects')
        entry = session.conversation_state['collected_data']['education']
        self.assertEqual(entry, [{**EXPECTED, 'end_date': '2022-06'}])
        self.assertEqual(session.conversation_state['collected_data']['personal'], SAMPLE_CV['personal'])

    def test_ambiguous_real_degrees_are_not_combined(self):
        session = self.broken_session()
        session.conversation_state['collected_data']['education'][1]['degree'] = 'Master of Arts'
        session.save(); before = deepcopy(session.conversation_state['collected_data']['education'])
        result = self.send(session, '2022-06')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(session.conversation_state['collected_data']['education'], before)

    def test_recovery_never_promotes_unproven_text_or_merges_explicit_new_degree(self):
        for mode in ('no-history', 'another-degree', 'saved'):
            with self.subTest(mode=mode):
                session = self.broken_session(history=mode != 'no-history')
                if mode == 'another-degree': ChatMessage.objects.create(session=session, role='user', content='Add another degree')
                if mode == 'saved': session.conversation_state['chat_saved_cv_id'] = 123; session.save()
                before = deepcopy(session.conversation_state['collected_data']['education'])
                self.send(session, '2022-06')
                self.assertEqual(session.conversation_state['collected_data']['education'], before)

    def test_grouped_skills_do_not_repeat_advice_during_every_education_answer(self):
        session = self.start(section='skills', field='skills')
        result = self.send(session, json.dumps(GROUPS)[1:-1])
        self.assertIn('strongest 8–15', result['assistant_message'])
        self.send(session, 'continue')
        self.send(session, 'Bachelor of Science in Cognitive Science')
        result = self.send(session, 'University of California, Berkeley')
        self.assertNotIn('skills list', result['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['Figma', *[v for values in GROUPS.values() for v in values if v != 'Figma']])

    def test_numeric_email_then_invalid_international_and_valid_national_phone(self):
        session = self.start(section='personal', field='email')
        self.send(session, '12qud@gmail.com')
        self.assertEqual(session.conversation_state['collected_data']['personal']['email'], '12qud@gmail.com')
        session.conversation_state['pending_field'] = {'section': 'personal', 'field': 'phone'}; session.save()
        result = self.send(session, '+1 (555) 019-2834')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state)['field'], 'phone')
        self.send(session, '03036098766')
        self.assertEqual(session.conversation_state['collected_data']['personal']['phone'], '03036098766')

    def test_full_contact_skills_and_education_journey_keeps_one_qualification(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Senior UI/UX Designer', 'career_level': 'experienced', 'template_id': 'creative_studio'})
        for text in ['Alex Morgan', '12qud@gmail.com', '+1 (555) 019-2834', '03036098766',
                     'San Francisco, CA', '[https://linkedin.com](https://linkedin.com)',
                     '[https://github.com](https://github.com)', '[https://behance.net](https://behance.net)']:
            self.send(session, text)
        bad = self.send(session, 'https://linkedin.com')
        self.assertEqual(bad['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state), {'section': 'experience', 'field': 'company'})
        for text in ['Example Design Studio', 'Senior UI/UX Designer', 'Designed accessible dashboards',
                     json.dumps(GROUPS)[1:-1], 'continue', EDUCATION]:
            result = self.send(session, text)
        self.assertEqual(result['section'], 'projects')
        self.assertNotIn('skills list', result['assistant_message'])
        data = session.conversation_state['collected_data']
        self.assertEqual(data['education'], [EXPECTED])
        self.assertEqual(len(data['skills']), 18)
        self.assertEqual(data['experience'][0]['company'], 'Example Design Studio')
        self.assertEqual(session.conversation_state['template_id'], 'creative_studio')

    def test_malformed_or_conflicting_pasted_education_is_never_stored_as_a_degree(self):
        for text in ['{"degree": "BS", "degree": "MS"}',
                     '"institution": "Example University", "degree": ',
                     '{"degree": "BS", "graduation_year": "2020", "end_date": "2022"}']:
            with self.subTest(text=text):
                session = self.start()
                result = self.send(session, text)
                self.assertEqual(result['intent'], 'clarify_information')
                self.assertFalse(session.conversation_state['collected_data'].get('education'))
                self.assertEqual(next_step(session.conversation_state)['field'], 'degree')

    def test_valid_siblings_survive_an_invalid_structured_graduation_date(self):
        session = self.start()
        result = self.send(session, EDUCATION.replace('"2020"', '"2020-13"'))
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')
        result = self.send(session, 'i graduted in 2022-06')
        self.assertEqual(result['section'], 'projects')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{**EXPECTED, 'end_date': '2022-06'}])

    def test_recovered_draft_saves_corrected_education_through_m2(self):
        from cvs.chat_import import save_chat_cv
        from cvs.models import CV
        session = self.broken_session(); self.send(session, 'i graduted in 2022-06')
        session.status = 'completed'; session.save(update_fields=['status'])
        saved, _ = save_chat_cv(user=self.user, session_id=session.pk)
        self.assertEqual(saved.data['education'][0]['end_date'], '2022-06')
        self.assertEqual(saved.data['education'][0]['field_of_study'], EXPECTED['field_of_study'])
        self.assertEqual(len(saved.data['education']), 1)
        self.assertEqual(CV.objects.count(), 1)
