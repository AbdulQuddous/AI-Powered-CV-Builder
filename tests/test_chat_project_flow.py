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
from chatbot.services.field_validation import extract_skills, validated_updates
from chatbot.services.qwen_client import adapt_extraction
from cvs.services import create_cv
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
GROUPED_PROJECT = ('AI-Powered CV Maker | Django Full-Stack Project\t2026 • '
                   'Built CV management workflows with Django/DRF, PostgreSQL, a JavaScript editor, '
                   'authentication, templates, and REST APIs. • '
                   'Integrated Gemini-assisted suggestions, CV import/extraction, version history, '
                   'and PDF/DOCX export; tested backend and frontend workflows.')


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

    def test_grouped_project_preserves_description_and_actual_stack_in_one_answer(self):
        session = self.start()
        reply = self.send(session, GROUPED_PROJECT)
        entry = session.conversation_state['collected_data']['projects'][0]
        self.assertEqual(entry['name'], 'AI-Powered CV Maker | Django Full-Stack Project')
        self.assertIn('Built CV management workflows', entry['description'])
        self.assertIn('PDF/DOCX export', entry['description'])
        self.assertTrue({'Django REST Framework', 'PostgreSQL', 'JavaScript', 'REST APIs', 'Gemini'}
                        <= set(entry['technologies']))
        self.assertNotIn('AI', entry['technologies'])  # A title is not proof of a tool used.
        self.assertFalse(session.conversation_state['collected_data'].get('summary'))
        self.assertNotIn('briefly describe', reply['assistant_message'])
        self.assertEqual(next_step(session.conversation_state)['field'], 'more_entries')
        self.qwen.assert_not_called()

    def test_grouped_project_supports_newlines_without_inventing_tools_from_its_title(self):
        session = self.start()
        self.send(session, 'Django Toolkit | AI Project\nOrganizes volunteer tasks and schedules.')
        entry = session.conversation_state['collected_data']['projects'][0]
        self.assertEqual(entry['name'], 'Django Toolkit | AI Project')
        self.assertEqual(entry['description'], 'Organizes volunteer tasks and schedules.')
        self.assertFalse(entry.get('technologies'))
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.qwen.assert_not_called()

    def test_grouped_project_date_does_not_hide_an_invalid_description(self):
        session = self.start()
        self.send(session, 'CV project\t2026 • I am a terrorist')
        entry = session.conversation_state['collected_data']['projects'][0]
        self.assertNotIn('description', entry)
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.qwen.assert_not_called()

    def test_grouped_project_in_saved_cv_is_only_an_unsaved_proposal(self):
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'add a project')
        self.send(session, GROUPED_PROJECT)
        proposed = session.conversation_state['edit_new_projects'][0]
        self.assertIn('PostgreSQL', proposed['technologies'])
        self.assertIn('version history', proposed['description'])
        cv.refresh_from_db()
        self.assertEqual(cv.data, SAMPLE_CV)
        self.assertEqual(cv.version, 1)
        self.qwen.assert_not_called()

    def test_copied_interview_extracts_new_answer_and_preserves_original_chat_message(self):
        session = self.start()
        self.send(session, 'CV Maker')
        prompt = 'Could you briefly describe what this project does?'
        answer = 'This project helps users create and manage CVs using Django and PostgreSQL.'
        pasted = ('AI Mode conversation: ' + GROUPED_PROJECT + ' Assistant ' + prompt + ' '
                  + GROUPED_PROJECT + ' Assistant ' + prompt + ' ' + answer)
        reply = self.send(session, pasted)
        entry = session.conversation_state['collected_data']['projects'][0]
        self.assertEqual(entry['description'], answer)
        self.assertEqual(entry['technologies'], ['Django', 'PostgreSQL'])
        self.assertNotIn('Projects can demonstrate', reply['assistant_message'])
        self.assertEqual(session.messages.filter(role='user').last().content, pasted)
        self.qwen.assert_not_called()

    def test_copied_question_without_new_answer_does_not_become_cv_content(self):
        session = self.start()
        self.send(session, 'CV Maker')
        before = deepcopy(session.conversation_state['collected_data'])
        reply = self.send(session, 'Assistant: Could you briefly describe what this project does?')
        self.assertEqual(reply['intent'], 'clarify_information')
        self.assertIn('answer', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.qwen.assert_not_called()

    def test_model_cannot_add_an_unrequested_summary_while_extracting_a_project(self):
        session = self.start()
        self.qwen.side_effect = None
        response = empty_ai_response()
        response['section'] = 'projects'
        response['cv_updates']['projects'] = [{'name': 'Scheduling Board',
            'description': 'Tracks tasks.', 'technologies': ['Django']}]
        response['cv_updates']['summary'] = 'Senior AI Engineer with healthcare and finance expertise.'
        self.qwen.return_value = response
        self.send(session, 'Could you record Scheduling Board, built using Django to track tasks?')
        self.assertFalse(session.conversation_state['collected_data'].get('summary'))
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['name'], 'Scheduling Board')
        self.qwen.assert_called_once()

    def test_summary_skip_omits_an_earlier_unsaved_summary_from_draft(self):
        from cvs.chat_import import build_chat_document
        session = self.start(field={'section': 'summary', 'field': 'summary'})
        session.conversation_state['collected_data']['summary'] = 'Earlier unwanted summary.'
        session.save()
        self.send(session, 'skip')
        self.assertFalse(session.conversation_state['collected_data'].get('summary'))
        document, _ = build_chat_document(session)
        self.assertEqual(document['summary'], '')

    def test_legacy_skipped_summary_is_not_restored_by_draft_import(self):
        from cvs.chat_import import build_chat_document
        session = self.start()
        session.conversation_state['collected_data']['summary'] = 'Legacy unwanted summary.'
        session.conversation_state['skipped_sections'] = ['summary']
        document, _ = build_chat_document(session)
        self.assertEqual(document['summary'], '')

    def test_skipping_saved_cv_summary_edit_preserves_saved_summary(self):
        from cvs.chat_import import build_chat_document
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'edit my summary')
        self.send(session, 'skip')
        document, _ = build_chat_document(session, current=cv.data)
        self.assertEqual(document['summary'], SAMPLE_CV['summary'])

    def test_single_skip_typos_are_recognized_only_at_optional_link_questions(self):
        for word in ('sip', 'skp', 'sikp'):
            session = self.start(field={'section': 'personal', 'field': 'linkedin'})
            self.send(session, word)
            self.assertEqual(session.conversation_state['personal_fields']['linkedin'], 'skipped')
            self.assertNotEqual(next_step(session.conversation_state)['field'], 'linkedin')
        session = self.start(field={'section': 'personal', 'field': 'email'})
        self.send(session, 'skp')
        self.assertEqual(next_step(session.conversation_state)['field'], 'email')
        self.qwen.assert_not_called()

    def test_description_update_retains_confirmed_tools_without_replacing_the_stack(self):
        session = self.start()
        self.send(session, 'CV Maker')
        state = session.conversation_state
        state['collected_data']['projects'][0]['technologies'] = ['Django', 'PostgreSQL']
        state['project_fields']['technologies'] = 'collected'
        session.save()
        self.send(session, 'Uses AI to help users draft CVs.')
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['technologies'],
                         ['Django', 'PostgreSQL', 'AI'])
        self.qwen.assert_not_called()

    def test_explicit_technology_answer_can_replace_previous_tools(self):
        session = self.start(field={'section': 'projects', 'field': 'technologies'})
        state = session.conversation_state
        state['collected_data']['projects'] = [{'name': 'CV Maker', 'description': 'Manages CVs.',
                                                'technologies': ['Django']}]
        state['project_fields'].update(name='collected', description='collected')
        session.save()
        self.send(session, 'React')
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['technologies'], ['React'])
        self.qwen.assert_not_called()

    def test_legacy_history_import_respects_a_skipped_summary(self):
        from cvs.chat_import import collected_updates
        session = self.start()
        session.conversation_state.pop('collected_data')
        session.conversation_state['skipped_sections'] = ['summary']
        ChatMessage.objects.create(session=session, role='assistant', section='summary',
                                   cv_updates={'summary': 'Unwanted legacy summary.'})
        self.assertNotIn('summary', collected_updates(session))

    def test_reported_finish_typo_finishes_only_the_completed_interview(self):
        from chatbot.services.state_manager import CV_SECTIONS
        session = self.start()
        session.conversation_state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        session.conversation_state['completed_sections'] = list(CV_SECTIONS)
        session.conversation_state['project_fields'] = dict.fromkeys(session.conversation_state['project_fields'], 'collected')
        session.save()
        reply = self.send(session, 'finssh')
        self.assertEqual(reply['next_action'], 'complete')
        self.assertEqual(session.status, 'completed')
        self.qwen.assert_not_called()

    def test_random_project_titles_do_not_advance_the_reported_interview(self):
        session = self.start()
        before = deepcopy(session.conversation_state['collected_data'])
        for text in ('ters354d', 'qwertyuiop', 'aaaaaa', 'add ters354d', 'yes, add it'):
            with self.subTest(text=text):
                reply = self.send(session, text)
                self.assertEqual(reply['intent'], 'clarify_information')
                self.assertEqual(next_step(session.conversation_state), {'section': 'projects', 'field': 'name'})
                self.assertFalse(any(reply['cv_updates'].values()))
                self.assertIn('project name', reply['assistant_message'])
                self.assertIn('not added', reply['assistant_message'])
                self.assertEqual(reply['assistant_message'].count('?'), 1)
                self.assertEqual(session.conversation_state['collected_data'], before)
        self.send(session, 'Task Tracker')
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': 'Task Tracker'}])
        self.qwen.assert_not_called()

    def test_random_title_cannot_become_a_new_project_in_a_saved_cv(self):
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'add a project')
        before = deepcopy(session.conversation_state['edit_updates'])
        reply = self.send(session, 'ters354d')
        self.assertIn('not added', reply['assistant_message'])
        self.assertEqual(next_step(session.conversation_state), {'section': 'projects', 'field': 'name'})
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertFalse(session.conversation_state['edit_draft'])
        cv.refresh_from_db()
        self.assertEqual(cv.data, SAMPLE_CV)
        self.assertEqual(cv.version, 1)
        self.qwen.assert_not_called()

    def test_numeric_branded_and_international_project_names_are_not_catalogue_limited(self):
        for name in ('h2o', 'CS50x', 'R2D2', 'gpt4all', 'apollo2026', 'neon-42', '2048',
                     'AURORA', 'CV Maker', 'Vocal View', 'Q2 Dashboard', '東京案内'):
            with self.subTest(name=name):
                session = self.start()
                self.send(session, name)
                self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': name}])
                self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.qwen.assert_not_called()

    def test_an_ambiguous_project_code_can_be_explicitly_named_without_inventing_a_title(self):
        session = self.start()
        self.send(session, 'mars2026a')
        self.assertEqual(next_step(session.conversation_state)['field'], 'name')
        self.assertFalse(session.conversation_state['collected_data'].get('projects'))
        self.send(session, 'My project is called mars2026a')
        self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': 'mars2026a'}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.qwen.assert_not_called()

    def test_model_proposed_noise_does_not_attach_its_metadata_to_another_project(self):
        session = self.start()
        previous = deepcopy(SAMPLE_CV['projects'])
        state = session.conversation_state
        state['collected_data']['projects'] = deepcopy(previous)
        session.save(update_fields=['conversation_state'])
        self.send(session, 'add another project')
        self.qwen.side_effect = None
        proposed = empty_ai_response()
        proposed['section'] = 'projects'
        proposed['cv_updates']['projects'] = [{
            'name': 'ters354d', 'description': 'A task tracker.', 'technologies': ['Django']}]
        self.qwen.return_value = proposed
        reply = self.send(session, 'Could you include ters354d using Django as a task tracker?')
        self.assertEqual(reply['intent'], 'clarify_information')
        self.assertFalse(any(reply['cv_updates'].values()))
        self.assertEqual(next_step(session.conversation_state)['field'], 'name')
        self.assertEqual(session.conversation_state['collected_data']['projects'], previous)
        self.assertFalse(session.conversation_state['pending_entry']['draft'])
        self.qwen.assert_called_once()

    def test_reported_noise_at_description_and_technologies_does_not_advance(self):
        session = self.start()
        self.send(session, 'Ai base interview plateform')
        original = deepcopy(session.conversation_state['collected_data'])
        for text in ('ters354d', 'qwertyuiop', 'yes, add it', 'Description: ters354d',
                     'ters354d; ters354d', 'Django, Python'):
            with self.subTest(field='description', text=text):
                reply = self.send(session, text)
                self.assertEqual(reply['intent'], 'clarify_information')
                self.assertEqual(next_step(session.conversation_state)['field'], 'description')
                self.assertIn('describe', reply['assistant_message'].casefold())
                self.assertEqual(session.conversation_state['collected_data']['projects'][0]['name'],
                                 'Ai base interview plateform')
                self.assertNotIn('description', session.conversation_state['collected_data']['projects'][0])
                # A technology-only answer can still supply confirmed tools.
                if text != 'Django, Python':
                    self.assertEqual(session.conversation_state['collected_data'], original)
        self.send(session, 'Evaluates interviews and provides feedback.')
        # Start another project with no technology mentions in its description.
        self.send(session, 'add another project')
        self.send(session, 'Task Tracker')
        self.send(session, 'Tracks tasks and due dates.')
        before = deepcopy(session.conversation_state['collected_data'])
        for text in ('ters354d', 'qwertyuiop', 'yes, add it', '2026', 'Django ters354d', ';;;'):
            with self.subTest(field='technologies', text=text):
                reply = self.send(session, text)
                self.assertEqual(reply['intent'], 'clarify_information')
                self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
                self.assertIn('technolog', reply['assistant_message'].casefold())
                self.assertEqual(session.conversation_state['collected_data'], before)
        self.send(session, 'Django, PostgreSQL')
        self.assertEqual(session.conversation_state['collected_data']['projects'][-1]['technologies'],
                         ['Django', 'PostgreSQL'])
        self.qwen.assert_not_called()

    def test_saved_cv_project_details_reject_noise_without_changing_the_saved_document(self):
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': deepcopy(SAMPLE_CV)})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'add a project')
        self.send(session, 'Interview Platform')
        before = deepcopy(session.conversation_state['edit_updates'])
        self.send(session, 'ters354d')
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.send(session, 'Evaluates interviews.')
        before = deepcopy(session.conversation_state['edit_updates'])
        self.send(session, 'ters354d')
        self.assertEqual(session.conversation_state['edit_updates'], before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.send(session, 'Django, PostgreSQL')
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        cv.refresh_from_db()
        self.assertEqual(cv.data, SAMPLE_CV)
        self.assertEqual(cv.version, 1)
        self.qwen.assert_not_called()

    def test_mixed_technology_list_retains_actual_tools_without_random_labels(self):
        session = self.start()
        self.send(session, 'Task Tracker')
        self.send(session, 'Tracks tasks.')
        reply = self.send(session, 'Django, ters354d, PostgreSQL')
        self.assertIn('not added', reply['assistant_message'])
        self.assertIn('recognized tools were kept', reply['assistant_message'])
        self.assertNotIn('Please list the actual tools', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['technologies'],
                         ['Django', 'PostgreSQL'])
        self.qwen.assert_not_called()

    def test_unfamiliar_single_technology_uses_qwen_without_a_tool_catalogue(self):
        session = self.start()
        self.send(session, 'Task Tracker')
        self.send(session, 'Tracks tasks.')
        self.qwen.side_effect = None
        reply = empty_ai_response()
        reply['section'] = 'projects'
        reply['cv_updates']['projects'] = [{'technologies': ['CobaltScript']}]
        self.qwen.return_value = reply
        self.send(session, 'CobaltScript')
        self.qwen.assert_called_once()
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['technologies'],
                         ['CobaltScript'])

    def test_model_cannot_skip_projects_on_an_unknown_technology_answer(self):
        session = self.start()
        self.send(session, 'Task Tracker')
        self.send(session, 'Tracks tasks.')
        before = deepcopy(session.conversation_state['collected_data'])
        self.qwen.side_effect = None
        self.qwen.return_value = adapt_extraction({
            'intent': 'skip', 'section': 'projects', 'extracted_fields': {},
            'field_corrections': {}, 'skip_fields': ['projects'], 'uncertain_fields': [],
            'cv_related_question': None, 'requires_clarification': False})
        reply = self.send(session, 'CobaltScript')
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.assertNotIn('projects', session.conversation_state.get('skipped_sections', []))
        self.assertEqual(reply['intent'], 'clarify_information')
        self.send(session, 'skip')
        self.assertIn('projects', session.conversation_state['skipped_sections'])
        self.qwen.assert_called_once()

    def test_single_word_description_uses_qwen_and_displays_its_clarification(self):
        session = self.start()
        self.send(session, 'Task Tracker')
        self.qwen.side_effect = None
        reason = 'That does not explain what your project does.'
        self.qwen.return_value = adapt_extraction({
            'intent': 'clarification', 'section': 'projects', 'extracted_fields': {},
            'field_corrections': {}, 'skip_fields': [], 'uncertain_fields': ['projects.description'],
            'cv_related_question': None, 'requires_clarification': True, 'rejection_reason': reason})
        reply = self.send(session, 'Rubery')
        self.assertIn(reason, reply['assistant_message'])
        self.assertEqual(reply['assistant_message'].count('?'), 1)
        self.assertEqual(next_step(session.conversation_state)['field'], 'description')
        self.assertEqual(session.conversation_state['collected_data']['projects'], [{'name': 'Task Tracker'}])
        self.qwen.assert_called_once()

    def test_project_clarification_without_model_feedback_uses_human_field_names(self):
        for field in ('description', 'technologies'):
            with self.subTest(field=field):
                session = self.start()
                self.send(session, 'Task Tracker')
                if field == 'technologies':
                    self.send(session, 'Tracks tasks.')
                before = deepcopy(session.conversation_state['collected_data'])
                self.qwen.side_effect = None
                self.qwen.return_value = adapt_extraction({
                    'intent': 'clarification', 'section': 'projects', 'extracted_fields': {},
                    'field_corrections': {}, 'skip_fields': [], 'uncertain_fields': ['projects.' + field],
                    'cv_related_question': None, 'requires_clarification': True, 'rejection_reason': None})
                reply = self.send(session, 'Rubery')
                self.assertIn('I couldn’t identify', reply['assistant_message'])
                self.assertNotIn('projects.' + field, reply['assistant_message'])
                self.assertEqual(reply['assistant_message'].count('?'), 1)
                self.assertEqual(next_step(session.conversation_state)['field'], field)
                self.assertEqual(session.conversation_state['collected_data'], before)

    def test_descriptions_can_mention_codes_and_unusual_tools_are_retained(self):
        session = self.start()
        self.send(session, 'Trace Viewer')
        description = 'Analyzes ters354d traces and produces reports.'
        self.send(session, description)
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['description'], description)
        self.send(session, 'n8n, h2o, GPT-4o, p5.js, Cobalt Script')
        self.assertEqual(session.conversation_state['collected_data']['projects'][0]['technologies'],
                         ['n8n', 'h2o', 'GPT-4o', 'p5.js', 'Cobalt Script'])
        self.qwen.assert_not_called()

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
    def test_provider_and_structured_project_details_cannot_bypass_noise_checks(self):
        for description in ('ters354d', 'Description: qwertyuiop'):
            response = empty_ai_response()
            response['cv_updates']['projects'] = [{'name': 'Task Tracker', 'description': description,
                                                  'technologies': ['Django', 'ters354d']}]
            clean, errors, statuses = validated_updates(response, {}, user_message='{"projects": []}')
            self.assertEqual(clean['cv_updates']['projects'], [{'name': 'Task Tracker', 'technologies': ['Django']}])
            self.assertTrue(errors)
            self.assertEqual(statuses['projects.0.description'], 'invalid')

    def test_project_technology_string_and_list_forms_are_validated_after_splitting(self):
        for values in ('Django, ters354d', ['Django, ters354d'], ['Django', 'ters354d'],
                       'Django;ters354d', ['Django\nters354d'], ['ters354d']):
            response = empty_ai_response()
            response['cv_updates']['projects'] = [{'technologies': values}]
            clean, errors, _ = validated_updates(response, {})
            expected = None if values == ['ters354d'] else [{'technologies': ['Django']}]
            self.assertEqual(clean['cv_updates']['projects'], expected)
            self.assertTrue(errors)

    def test_invalid_project_identity_drops_only_its_entry_and_keeps_a_valid_sibling(self):
        response = empty_ai_response()
        response['cv_updates']['projects'] = [
            {'name': 'ters354d', 'description': 'A task tracker.', 'technologies': ['Django']},
            {'name': 'Vocal View', 'description': 'An interview tool.', 'technologies': ['Python']}]
        clean, errors, statuses = validated_updates(response, {}, user_message='ters354d and Vocal View')
        self.assertEqual(clean['cv_updates']['projects'], [response['cv_updates']['projects'][1]])
        self.assertTrue(errors)
        self.assertEqual(statuses['projects.0.name'], 'invalid')
        self.assertEqual(statuses['projects.0.description'], 'needs_clarification')

    def test_explicit_structured_project_codes_remain_valid(self):
        for message in ('{"projects": [{"name": "mars2026a"}]}',
                        '{"name": "mars2026a", "description": "A task tracker."}'):
            response = empty_ai_response()
            response['cv_updates']['projects'] = [{'name': 'mars2026a'}]
            clean, errors, _ = validated_updates(response, {}, user_message=message)
            self.assertEqual(clean['cv_updates']['projects'], [{'name': 'mars2026a'}])
            self.assertFalse(errors)

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
