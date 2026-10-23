"""Regressions from the Talha interview: direct answers and project identity."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.question_engine import next_step
from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.field_validation import extract_skills
from tests.test_m8 import SAMPLE_CV

TITLE = 'i Want to add Ai base interview plateform'
SUMMARY = ('Python Developer Intern and Software Engineering graduate with hands-on experience '
           'building Django web applications and REST APIs using Python, Django REST Framework, PostgreSQL, '
           'and SQL. Worked on recruitment features, ATS scoring, and an AI-powered CV Maker during an '
           'internship, alongside independent backend and full-stack projects. Comfortable with CRUD '
           'operations, API integration, Git/GitHub, debugging, and testing; focused on clean, reusable, '
           'maintainable code and collaborative problem-solving.')
DESCRIPTION = ('Built a full-stack Django/DRF application with PostgreSQL, REST APIs, JWT authentication, '
               'interview workflows, and candidate performance reports. • Integrated third-party AI tools '
               '(Whisper, MediaPipe, Sentence Transformers) and improved answer scoring by debugging '
               'semantic-similarity and keyword-matching logic. • Performed system-level manual and API '
               'tests, investigated defects, and verified fixes with Postman.')
LATEST_DESCRIPTION = 'it evaluatee candiadate interview perfomance using facial and vocal analysis and give detailed feedback report'
FALSE_PROJECTS = [
    {'name': 'Django web application', 'technologies': ['Python', 'Django REST Framework', 'PostgreSQL', 'SQL']},
    {'name': 'REST API', 'technologies': ['Python', 'Django REST Framework', 'PostgreSQL', 'SQL']},
]


class ProjectFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('project-flow@example.com')
        cls.other = get_user_model().objects.create_user('other-project-flow@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('These direct answers should remain local'))
        self.qwen = mocked.start(); self.addCleanup(mocked.stop)

    def start(self, *, field=None):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Backend Developer', 'career_level': 'experienced', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {'personal': deepcopy(SAMPLE_CV['personal']), 'skills': ['Python']}
        state['completed_sections'] = ['personal', 'education', 'experience', 'skills']
        for group in ('personal_fields', 'education_fields', 'experience_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        if field and field['section'] == 'education':
            state['education_fields'] = dict.fromkeys(state['education_fields'], 'missing')
            state['completed_sections'].remove('education')
        if field:
            state['pending_field'] = field
        session.conversation_state = state; session.current_section = next_step(state)['section']; session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db(); return result.data

    def test_query_string_urls_and_markdown_links_stay_in_the_contact_field(self):
        for value, expected in [
            ('https://talha-portfolio.rf.gd/?i=1', 'https://talha-portfolio.rf.gd/?i=1'),
            ('[My portfolio](https://example.com/cv?i=1&add=resume)', 'https://example.com/cv?i=1&add=resume'),
        ]:
            with self.subTest(value=value):
                session = self.start(field={'section': 'personal', 'field': 'portfolio'})
                before = deepcopy(session.conversation_state['collected_data']['personal'])
                result = self.send(session, value)
                self.assertNotEqual(result['intent'], 'clarify_information')
                self.assertEqual(session.conversation_state['collected_data']['personal'], {**before, 'portfolio': expected})
                self.assertEqual(result['cv_updates']['personal'], {'portfolio': expected})

    def test_informal_degree_with_i_prefix_keeps_university_and_has_no_fake_dates(self):
        session = self.start(field={'section': 'education', 'field': 'degree'})
        result = self.send(session, 'i bs software engineering from university of minawali')
        self.assertNotEqual(result['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry, {'degree': 'bs software engineering', 'field_of_study': 'software engineering',
                                 'institution': 'university of minawali'})
        self.send(session, 'start 2022 end 2026')
        self.assertEqual(len(session.conversation_state['collected_data']['education']), 1)
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['institution'], 'university of minawali')

    def test_responsibility_sentence_with_and_is_preserved_as_one_confirmed_answer(self):
        session = self.start(field={'section': 'experience', 'field': 'responsibilities'})
        session.conversation_state['collected_data']['experience'] = [{'company': 'Nayatel', 'role': 'Backend Developer'}]
        session.save()
        answer = 'Building sclabable and maintainable backend system'
        self.send(session, answer)
        self.assertEqual(session.conversation_state['collected_data']['experience'][0]['responsibilities'], [answer])

    def test_explicit_title_profile_paragraph_and_project_description_are_separate(self):
        session = self.start()
        self.send(session, TITLE)
        self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': 'Ai base interview plateform'}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        result = self.send(session, SUMMARY)
        self.assertEqual(result['section'], 'projects')
        self.assertIn('summary', result['assistant_message'].lower())
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)
        self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': 'Ai base interview plateform'}])
        result = self.send(session, DESCRIPTION)
        self.assertIn('1 project', result['assistant_message'])
        result = self.send(session, 'continue')
        self.assertEqual(result['section'], 'certifications')
        projects = session.conversation_state['collected_data']['projects']
        self.assertEqual(len(projects), 1); self.assertEqual(projects[0]['description'], DESCRIPTION)
        self.assertIn('Django REST Framework', projects[0]['technologies'])
        self.assertIn('PostgreSQL', projects[0]['technologies']); self.assertIn('Whisper', projects[0]['technologies'])
        self.assertNotIn('React', projects[0]['technologies'])

    def test_profile_at_project_name_question_does_not_create_multiple_projects(self):
        session = self.start(); self.send(session, SUMMARY)
        self.assertEqual(next_step(session.conversation_state)['field'], 'name')
        self.assertFalse(session.conversation_state['collected_data'].get('projects'))
        self.assertEqual(session.conversation_state['collected_data']['summary'], SUMMARY)

    def test_description_before_title_is_staged_until_the_project_is_named(self):
        session = self.start(); self.send(session, DESCRIPTION)
        self.assertEqual(next_step(session.conversation_state)['field'], 'name')
        self.assertFalse(session.conversation_state['collected_data'].get('projects'))
        self.send(session, TITLE)
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['description'], DESCRIPTION)
        self.send(session, 'continue')
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')

    def test_each_description_variant_fills_the_current_project_without_an_identity_loop(self):
        for answer in [DESCRIPTION, 'i evaluatee candiadate interview perfomance using facial and vocal analysis', LATEST_DESCRIPTION]:
            with self.subTest(answer=answer):
                session = self.start(); self.send(session, TITLE)
                result = self.send(session, answer)
                self.assertNotIn('identify which entry', result['assistant_message'])
                self.assertEqual(session.conversation_state['collected_data']['projects'][0]['description'], answer)
                self.assertNotEqual(next_step(session.conversation_state)['field'], 'description')

    def test_true_ambiguity_lists_projects_and_numeric_choice_applies_the_queued_details(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['projects'] = [{'name': 'Interview platform'}, {'name': 'CV maker'}]
        state['project_fields']['name'] = 'collected'
        session.conversation_state = state; session.save()
        result = self.send(session, LATEST_DESCRIPTION)
        self.assertIn('1.', result['assistant_message']); self.assertIn('2.', result['assistant_message'])
        self.assertIn('Interview platform', result['assistant_message'])
        self.assertEqual(self.send(session, '2')['section'], 'projects')
        projects = session.conversation_state['collected_data']['projects']
        self.assertNotIn('description', projects[0]); self.assertEqual(projects[1]['description'], LATEST_DESCRIPTION)
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.send(session, 'Python, Django')
        self.assertEqual(projects[0], session.conversation_state['collected_data']['projects'][0])
        self.assertEqual(session.conversation_state['collected_data']['projects'][1]['technologies'], ['Python', 'Django'])

    def test_invalid_selection_preserves_pending_details_and_a_unique_name_can_select(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['projects'] = [{'name': 'Interview platform'}, {'name': 'CV maker'}]
        state['project_fields']['name'] = 'collected'
        session.conversation_state = state; session.save()
        self.send(session, LATEST_DESCRIPTION)
        pending = deepcopy(session.conversation_state['pending_selection'])
        self.send(session, '99')
        self.assertEqual(session.conversation_state['pending_selection'], pending)
        self.send(session, 'Interview platform')
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['description'], LATEST_DESCRIPTION)
        self.assertNotIn('description', session.conversation_state['collected_data']['projects'][1])

    def test_selection_applies_details_without_renaming_a_project(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['projects'] = [{'name': 'Interview platform'}, {'name': 'CV maker'}]
        state['project_fields']['name'] = 'collected'
        state['collection_entry_indexes'] = {'projects': 0}
        session.conversation_state = state; session.save()
        self.qwen.side_effect = None
        result = empty_ai_response(); result['section'] = 'projects'
        result['cv_updates']['projects'] = [{'name': 'CV maker', 'description': 'A clear description.'}]
        self.qwen.return_value = result
        self.send(session, 'Could you include these project details?')
        self.send(session, '1')
        self.assertEqual(session.conversation_state['collected_data']['projects'][0], {
            'name': 'Interview platform', 'description': 'A clear description.'})
        self.assertNotIn('pending_selection', session.conversation_state)

    def contaminated(self, *, history=True):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['projects'] = deepcopy(FALSE_PROJECTS)
        state['project_fields'].update(name='collected', description='missing', technologies='collected')
        state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.save()
        if history:
            ChatMessage.objects.create(session=session, role='assistant', content='What is the name of the project you would like to include?', section='projects')
            ChatMessage.objects.create(session=session, role='user', content=TITLE)
            ChatMessage.objects.create(session=session, role='assistant', content='Please confirm extracted details. What is the name of the project you would like to include?', section='projects')
            ChatMessage.objects.create(session=session, role='user', content=SUMMARY)
            ChatMessage.objects.create(session=session, role='assistant', content='Could you briefly describe what this project does?', section='projects', cv_updates={'projects': deepcopy(FALSE_PROJECTS)})
            for text in [DESCRIPTION, LATEST_DESCRIPTION]:
                ChatMessage.objects.create(session=session, role='user', content=text)
                ChatMessage.objects.create(session=session, role='assistant', content='Please identify which entry these details belong to. Could you briefly describe what this project does?', section='projects')
        return session

    def test_resume_recovers_the_evidenced_summary_split_and_rejected_description(self):
        session = self.contaminated(); personal = deepcopy(session.conversation_state['collected_data']['personal'])
        response = self.client.get(f'/api/chat/sessions/{session.id}/'); self.assertEqual(response.status_code, 200)
        session.refresh_from_db(); state = session.conversation_state
        projects = state['collected_data']['projects']
        self.assertEqual(len(projects), 1); self.assertEqual(projects[0]['name'], 'Ai base interview plateform')
        self.assertEqual(projects[0]['description'], LATEST_DESCRIPTION)
        self.assertIn('Whisper', projects[0]['technologies'])
        self.assertEqual(state['collected_data']['summary'], SUMMARY)
        self.assertEqual(state['collected_data']['personal'], personal)
        self.assertEqual(state['undo_state']['collected_data']['projects'], projects)
        self.assertEqual(session.current_section, 'certifications')

    def test_recovery_requires_matching_history_and_never_changes_saved_or_other_owned_data(self):
        for mode in ['no-history', 'saved', 'changed-project']:
            session = self.contaminated(history=mode != 'no-history')
            if mode == 'saved': session.conversation_state['chat_saved_cv_id'] = 'saved'
            if mode == 'changed-project': session.conversation_state['collected_data']['projects'][0]['name'] = 'A real corrected project'
            session.save(); before = deepcopy(session.conversation_state)
            self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
            self.assertEqual(session.conversation_state, before)
        session = self.contaminated(); self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.id}/').status_code, 404)

    def test_recovery_is_idempotent_and_stale_clients_reload_before_writing(self):
        session = self.contaminated(); timestamp = session.updated_at.isoformat()
        self.client.get(f'/api/chat/sessions/{session.id}/'); count = session.messages.count()
        self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(session.messages.count(), count)
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/',
            {'message': 'skip', 'expected_updated_at': timestamp}, format='json')
        self.assertEqual(result.status_code, 409)

    def test_recovered_draft_can_finish_and_save_one_named_project(self):
        session = self.contaminated(); self.client.get(f'/api/chat/sessions/{session.id}/')
        for message in ['skip', 'skip', 'skip', 'finish']:
            result = self.send(session, message)
        self.assertEqual(result['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id)}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(len(saved.data['cv']['data']['projects']), 1)
        self.assertEqual(saved.data['cv']['data']['projects'][0]['name'], 'Ai base interview plateform')
        self.assertEqual(saved.data['cv']['data']['summary'], SUMMARY)


class RepeatedFactGuardTests(SimpleTestCase):
    def test_explicit_skill_aliases_work_as_single_answers_and_keep_list_order(self):
        self.assertEqual(extract_skills('Restapi'), ['REST APIs'])
        self.assertEqual(extract_skills('NODE'), ['Node.js'])
        self.assertEqual(extract_skills('NEXT'), ['Next.js'])
        self.assertEqual(extract_skills('Python Django DRF MySQL Git'), ['Python', 'Django', 'Django REST Framework', 'MySQL', 'Git'])
        self.assertIsNone(extract_skills('I might learn Python next year'))

    def test_literal_technology_categories_in_a_profile_are_not_project_titles(self):
        response = empty_ai_response(); response['cv_updates']['projects'] = deepcopy(FALSE_PROJECTS)
        result = guard_extraction(response, SUMMARY, {})
        self.assertTrue(all('name' not in entry for entry in result['cv_updates']['projects']))

    def test_unchanged_context_contacts_are_removed_without_false_confirmation(self):
        response = empty_ai_response()
        response['cv_updates']['personal'] = {'email': 'talha@example.com', 'phone': '03036096093',
            'github': 'https://github.com/Github-Talha', 'portfolio': 'https://example.com/?i=1'}
        state = {'collected_data': {'personal': {key: value for key, value in response['cv_updates']['personal'].items() if key != 'portfolio'}}}
        guarded = guard_extraction(response, 'https://example.com/?i=1', state)
        self.assertEqual(guarded['cv_updates']['personal'], {'portfolio': 'https://example.com/?i=1'})
        self.assertFalse(guarded.get('_control', {}).get('evidence_warning'))

    def test_new_unmentioned_contact_is_still_rejected(self):
        response = empty_ai_response(); response['cv_updates']['personal'] = {'email': 'invented@example.com'}
        result = guard_extraction(response, 'https://example.com/?i=1', {'collected_data': {'personal': {'email': 'talha@example.com'}}})
        self.assertNotIn('email', result['cv_updates']['personal'])
