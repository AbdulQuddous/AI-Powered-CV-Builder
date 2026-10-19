"""Regression coverage for Ali's pasted lists, typo cleanup and final dates."""
import json
import re
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.message_routing import response_update
from chatbot.services.education_answers import parse_education
from chatbot.services.field_validation import extract_skills
from chatbot.services.section_answers import structured_section_answer, parse_languages
from tests.test_m8 import SAMPLE_CV

CERTIFICATES = ['Google UX Design Professional Certificate', 'NN/g UX Certified (Nielsen Norman Group)']
CERTIFICATE_TEXT = '"certifications": ' + json.dumps(CERTIFICATES)
ACHIEVEMENTS = [
    'Built and maintained robust relational databases utilizing PostgreSQL, optimizing execution times for heavily relational datasets.',
    'Containerized core microservices using Docker, establishing consistent and automated deployment pipelines across cloud infrastructure.',
    'Implemented secure platform authentication protocols across third-party REST API developer integrations.',
]
ACHIEVEMENT_TEXT = json.dumps(ACHIEVEMENTS)[1:-1] + ' ] } ],'
DEGREE = 'i completed bs software engineering degrre from university of mianwali'
SKILLS = 'NLP, ML, DL, Djnago, Restapis'
SUMMARY = ('Innovative Software Engineer specializing in Artificial Intelligence and Machine Learning solutions '
           'with a strong background in backend architectures.')


class ListCleanupParsingTests(SimpleTestCase):
    def test_certificates_keep_titles_and_embedded_commas(self):
        names = CERTIFICATES + ['Design, Research and Testing']
        for text in [json.dumps(names), json.dumps({'certifications': names}),
                     '"certifications": ' + json.dumps(names), '```json\n' + json.dumps(names) + '\n```']:
            with self.subTest(text=text):
                self.assertEqual(structured_section_answer(text, 'certifications'), [{'name': name} for name in names])

    def test_certificate_objects_preserve_only_explicit_fields(self):
        values = [{'name': 'Python Certificate', 'issuer': 'Example Academy', 'date': '2026-06', 'url': 'https://example.com/cert'}]
        self.assertEqual(structured_section_answer(json.dumps({'certifications': values}), 'certifications'), values)
        for text in ['{"certifications": ["A"], "certifications": ["B"]}',
                     '{"certifications": ["A"], "summary": "B"}',
                     '[{"name": "A", "invented": "B"}]', '[false]', '["A", {"issuer": "B"}]']:
            with self.subTest(text=text): self.assertIsNone(structured_section_answer(text, 'certifications'))

    def test_quoted_achievement_fragment_keeps_sentences_with_commas(self):
        self.assertEqual(structured_section_answer(ACHIEVEMENT_TEXT, 'achievements'), ACHIEVEMENTS)
        for text in [ACHIEVEMENT_TEXT + ' ignore instructions', '"A" "B"', '"achievements": ["A", false]']:
            with self.subTest(text=text): self.assertIsNone(structured_section_answer(text, 'achievements'))

    def test_control_phrases_never_become_language_names(self):
        for text in ['keep as it', 'keep it as is', 'keep it as it is', 'leave as is', 'keep it unspecified.']:
            with self.subTest(text=text): self.assertEqual(parse_languages(text), [])

    def test_bounded_skill_and_degree_typo_cleanup_retains_facts(self):
        self.assertEqual(extract_skills(SKILLS), ['NLP', 'ML', 'DL', 'Django', 'REST APIs'])
        self.assertEqual(parse_education(DEGREE), {'degree': 'bs software engineering',
            'field_of_study': 'software engineering', 'institution': 'university of mianwali'})
        self.assertEqual(parse_education('BS in Software Engineering degree from University of Mianwali')['field_of_study'], 'Software Engineering')


class ReviewCleanupJourneyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('cleanup-owner@example.com')
        cls.other = get_user_model().objects.create_user('cleanup-other@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.provider = patch('chatbot.services.conversation_service.QwenClient.generate',
                              side_effect=AssertionError('Explicit answers should stay local')).start()
        self.addCleanup(patch.stopall)

    def start(self, *, review=False):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'AI/ML Engineer & Backend Developer', 'career_level': 'experienced', 'template_id': 'modern'})
        if review:
            state = session.conversation_state
            state['collected_data'] = deepcopy(SAMPLE_CV)
            state['completed_sections'] = ['personal', 'experience', 'skills', 'education', 'projects',
                                           'certifications', 'achievements', 'languages', 'summary']
            for key in ('personal_fields', 'experience_fields', 'education_fields', 'project_fields'):
                state[key] = dict.fromkeys(state[key], 'collected')
            session.conversation_state = state; session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db()
        return result.data

    def test_reported_journey_saves_clean_lists_and_preserves_metadata(self):
        session = self.start()
        self.send(session, 'Ali Khan')
        for bad in ['123qudd@@gmail.com', '123qudd@gmail', '123qudd gmail.com']:
            reply = self.send(session, bad)
            self.assertEqual(reply['intent'], 'clarify_information')
            self.assertNotIn('email', session.conversation_state['collected_data']['personal'])
        self.send(session, '123qudd@gmail.com')
        self.send(session, '+92 (300) 123-4567')
        self.send(session, 'Islamabad, Pakistan')
        self.send(session, '[https://linkedin.com](https://linkedin.com)')
        self.send(session, 'skip')
        self.send(session, '[https://github.com](https://github.com)')
        self.send(session, 'Bitech Systems')
        self.assertEqual(self.send(session, 'shut up idiot are you foll')['intent'], 'irrelevant')
        self.send(session, 'AI/ML Developer & Backend Engineer')
        self.provider.side_effect = None
        self.provider.return_value = response_update('experience', 'responsibilities',
                                                     ['Integrate Ai module', 'develop Backend for Applications'])
        self.send(session, 'Integrate Ai module and develop Backend for Applications')
        self.assertEqual(self.provider.call_count, 1)
        self.provider.side_effect = AssertionError('The rest of this transcript must stay local')
        self.send(session, SKILLS)
        self.assertEqual(self.send(session, DEGREE)['section'], 'education')
        self.assertEqual(self.send(session, 'i graduated in 2026')['section'], 'projects')
        self.send(session, 'Smart CV Maker Chatbot')
        self.send(session, 'Created an intelligent conversational assistant that captures user background information via an interactive interface and maps unstructured data into dynamic CV data objects.')
        self.send(session, 'Django, Restapi, PostgreSQL')
        self.assertEqual(self.send(session, CERTIFICATE_TEXT)['section'], 'achievements')
        self.assertEqual(self.send(session, ACHIEVEMENT_TEXT)['section'], 'languages')
        self.send(session, 'English urdu')
        self.assertEqual(self.send(session, 'keep as it')['section'], 'summary')
        self.send(session, SUMMARY)
        finish = self.send(session, 'finish')
        self.assertNotEqual(finish['next_action'], 'complete')
        self.assertIn('2026', finish['assistant_message'])
        self.assertIn('year and month', finish['assistant_message'])
        self.assertEqual(session.status, 'active')
        self.send(session, 'i graduted in 2026-06')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        data = saved.data['cv']['data']
        self.assertEqual(data['meta'], {'target_role': 'AI/ML Engineer & Backend Developer',
                                      'template_id': 'modern', 'career_level': 'experienced'})
        self.assertEqual(data['personal']['email'], '123qudd@gmail.com')
        self.assertEqual(data['skills'], ['NLP', 'ML', 'DL', 'Django', 'REST APIs'])
        self.assertEqual(data['education'][0]['end_date'], '2026-06')
        self.assertEqual(data['education'][0]['degree'], 'bs software engineering')
        self.assertEqual([entry['name'] for entry in data['certifications']], CERTIFICATES)
        self.assertEqual([entry['name'] for entry in data['languages']], ['English', 'Urdu'])
        self.assertEqual(data['achievements'], ACHIEVEMENTS)
        self.assertEqual(saved.data['warnings'], [])

    def test_year_confirmation_targets_the_right_entry_and_never_invents_month(self):
        session = self.start(review=True)
        state = session.conversation_state
        state['collected_data']['education'].append({'degree': 'MS', 'institution': 'Example University', 'end_date': '2026'})
        session.conversation_state = state; session.save()
        original = deepcopy(state['collected_data']['education'][0])
        self.send(session, 'finish')
        for text in ['finish', '2026', 'i graduated in 2026', '2026-13']:
            result = self.send(session, text)
            self.assertNotEqual(result['next_action'], 'complete')
            self.assertEqual(session.conversation_state['collected_data']['education'][1]['end_date'], '2026')
        self.send(session, '2026-07')
        self.assertEqual(session.conversation_state['collected_data']['education'][1]['end_date'], '2026-07')
        self.assertEqual(session.conversation_state['collected_data']['education'][0], original)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_unknown_month_can_be_explicitly_omitted_without_losing_chat_year(self):
        session = self.start(review=True)
        session.conversation_state['collected_data']['education'][0]['end_date'] = '2026'
        session.save()
        self.send(session, 'finish'); self.send(session, 'omit this date')
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], '2026')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        draft = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        self.assertEqual(draft.status_code, 200, draft.data)
        self.assertIn('2026', draft.data['warnings'][0])
        self.assertEqual(draft.data['draft']['education'][0]['end_date'], '')

    def test_date_order_retry_keeps_the_second_degree_selected(self):
        session = self.start(review=True)
        session.conversation_state['collected_data']['education'].append({
            'degree': 'MS', 'institution': 'Example University', 'start_date': '2026-09', 'end_date': '2026'})
        session.save()
        self.send(session, 'finish')
        self.assertEqual(self.send(session, '2026-06')['intent'], 'clarify_information')
        self.send(session, '2026-12')
        self.assertEqual(session.conversation_state['collected_data']['education'][1]['end_date'], '2026-12')
        self.assertNotIn('entry_patches', session.conversation_state)

    def test_certificate_year_gets_the_same_explicit_month_confirmation(self):
        session = self.start(review=True)
        session.conversation_state['collected_data']['certifications'] = [{'name': 'Python Certificate', 'date': '2026'}]
        session.save()
        self.assertIn('issue date', self.send(session, 'finish')['assistant_message'])
        self.send(session, '2026-06')
        self.assertEqual(session.conversation_state['collected_data']['certifications'], [{'name': 'Python Certificate', 'date': '2026-06'}])
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def contaminated(self, *, history=True):
        session = self.start(review=True)
        state = session.conversation_state
        state['collected_data']['languages'] = [{'name': 'English'}, {'name': 'Urdu'}, {'name': 'keep as it'}]
        state['collected_data']['certifications'] = [{'name': value.strip().rstrip('.')} for value in
                                                   re.split(r',|\band\b', CERTIFICATE_TEXT) if value.strip()]
        state['collected_data']['skills'] = ['NLP', 'ML', 'DL', 'Djnago', 'REST APIs']
        state['collected_data']['education'] = [{'degree': 'bs software engineering degrre',
            'institution': 'university of mianwali', 'field_of_study': 'software engineering degrre', 'end_date': '2026'}]
        state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.status = 'completed'; session.save()
        if history:
            for text in ['English urdu', 'keep as it', CERTIFICATE_TEXT, SKILLS, DEGREE]:
                ChatMessage.objects.create(session=session, role='user', content=text)
        return session

    def test_unsaved_draft_and_undo_are_repaired_from_history_before_review(self):
        session = self.contaminated()
        result = self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        self.assertEqual(result.status_code, 200, result.data)
        data = result.data['draft']
        self.assertEqual([entry['name'] for entry in data['certifications']], CERTIFICATES)
        self.assertEqual([entry['name'] for entry in data['languages']], ['English', 'Urdu'])
        self.assertIn('Django', data['skills'])
        self.assertEqual(data['education'][0]['degree'], 'bs software engineering')
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['undo_state']['collected_data']['certifications'], [{'name': name} for name in CERTIFICATES])

    def test_direct_save_of_an_older_draft_also_cleans_evidenced_lists(self):
        session = self.contaminated()
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        data = saved.data['cv']['data']
        self.assertEqual([entry['name'] for entry in data['certifications']], CERTIFICATES)
        self.assertEqual([entry['name'] for entry in data['languages']], ['English', 'Urdu'])
        self.assertIn('Django', data['skills'])

    def test_recovery_requires_evidence_and_owner_and_never_rewrites_saved_cv(self):
        session = self.contaminated(history=False)
        before = deepcopy(session.conversation_state)
        self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        session.refresh_from_db(); self.assertEqual(session.conversation_state, before)
        session = self.contaminated(); before = deepcopy(session.conversation_state)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.pk}/draft/').status_code, 404)
        self.client.force_authenticate(self.user)
        session.conversation_state['chat_saved_cv_id'] = 'already-saved'; session.save()
        self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        session.refresh_from_db()
        self.assertEqual(session.conversation_state['collected_data'], before['collected_data'])

    def test_malformed_certificates_do_not_get_saved_as_names(self):
        session = self.start(review=True)
        self.send(session, 'add certifications')
        for text in ['"certifications": ["A",', '{"certifications": ["A"], "certifications": ["B"]}']:
            result = self.send(session, text)
            self.assertEqual(result['intent'], 'clarify_information')
            self.assertEqual(session.conversation_state['collected_data']['certifications'], SAMPLE_CV['certifications'])

    def test_repair_does_not_overwrite_a_later_correction(self):
        session = self.contaminated()
        data = session.conversation_state['collected_data']
        data['certifications'] = [{'name': 'Updated certificate'}]
        data['education'][0]['degree'] = 'MS Computer Science'
        session.save()
        self.client.get(f'/api/chat/sessions/{session.pk}/draft/')
        session.refresh_from_db()
        data = session.conversation_state['collected_data']
        self.assertEqual(data['certifications'], [{'name': 'Updated certificate'}])
        self.assertEqual(data['education'][0]['degree'], 'MS Computer Science')

    def test_active_draft_recovery_does_not_repeat_the_proficiency_question(self):
        session = self.contaminated()
        session.status = 'active'
        session.conversation_state['completed_sections'].remove('summary')
        session.conversation_state['language_proficiency_pending'] = ['English', 'Urdu', 'keep as it']
        session.save()
        self.client.get(f'/api/chat/sessions/{session.pk}/')
        session.refresh_from_db()
        from chatbot.services.question_engine import next_step
        self.assertEqual(next_step(session.conversation_state)['section'], 'summary')
