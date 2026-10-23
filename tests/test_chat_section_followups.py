"""Count advice and literal cleanup from the FAST / Vocal View interview."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.services.conversation_service import create_chat_session
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.field_validation import validated_updates, normalise_skill_list
from chatbot.services.question_engine import next_step
from chatbot.services.state_manager import CV_SECTIONS
from cvs.chat_import import build_chat_document
from tests.test_m8 import SAMPLE_CV


class SectionFollowupTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('section-followups@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        provider = patch('chatbot.services.conversation_service.QwenClient.generate',
                         side_effect=AssertionError('Explicit interview answers need no model guesses'))
        provider.start()
        self.addCleanup(provider.stop)

    def start(self, section, profile='fresher'):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Django Backend Developer', 'career_level': profile, 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        state['collected_data'][section] = []
        state['completed_sections'] = [key for key in CV_SECTIONS if key != section]
        for key in ('personal_fields', 'education_fields', 'experience_fields', 'project_fields'):
            state[key] = dict.fromkeys(state[key], 'collected')
        group = {'projects': 'project_fields', 'education': 'education_fields',
                 'experience': 'experience_fields'}.get(section)
        if group:
            state[group] = dict.fromkeys(state[group], 'missing')
        session.conversation_state = state
        session.current_section = section
        session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(set(result.data), {'assistant_message', 'intent', 'section', 'cv_updates', 'next_action'})
        session.refresh_from_db()
        return result.data

    def project(self, session, name='Vocal View'):
        self.send(session, name)
        reply = self.send(session, 'An interview platform that gives detailed feedback and suggestions.')
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.assertNotIn('section_followup', session.conversation_state)
        return self.send(session, 'Django Restapi React Ai NLP')

    def test_four_skills_offer_more_then_continue_without_skipping_or_losing_any(self):
        session = self.start('skills')
        reply = self.send(session, 'C++, Git, DJango, SQL')
        self.assertEqual(reply['section'], 'skills')
        self.assertIn('4 skills', reply['assistant_message'])
        self.assertIn('8–15', reply['assistant_message'])
        self.assertIn('fewer are fine', reply['assistant_message'])
        before = deepcopy(session.conversation_state['collected_data'])
        reply = self.send(session, 'continue')
        self.assertEqual(reply['section'], 'review')
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.assertNotIn('skills', session.conversation_state.get('skipped_sections', []))
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, _ = build_chat_document(session)
        self.assertEqual(document['skills'], ['C++', 'Git', 'Django', 'SQL'])

    def test_add_more_uses_real_answer_and_does_not_nag_for_minimum(self):
        session = self.start('skills')
        self.send(session, 'C++ Git Github Restapi DJango')
        before = deepcopy(session.conversation_state['collected_data']['skills'])
        self.send(session, 'yes')
        self.assertEqual(session.conversation_state['collected_data']['skills'], before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'skills')
        self.send(session, 'Python')
        self.assertEqual(session.conversation_state['collected_data']['skills'],
                         ['C++', 'Git', 'GitHub', 'REST APIs', 'Django', 'Python'])
        self.assertNotIn('section_followup', session.conversation_state)
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')

    def test_eight_skills_need_no_extra_pause(self):
        session = self.start('skills')
        reply = self.send(session, 'Python, Django, REST APIs, PostgreSQL, Git, GitHub, SQL, Docker')
        self.assertEqual(reply['section'], 'review')
        self.assertNotIn('section_followup', session.conversation_state)

    def test_overflow_offers_prioritization_and_keeps_all_facts(self):
        session = self.start('skills')
        skills = ['Python', 'Django', 'PostgreSQL', 'JavaScript', 'TypeScript', 'HTML', 'CSS',
                  'React', 'MySQL', 'Git', 'C++', 'C#', 'Docker', 'Flask', 'JWT', 'Postman']
        reply = self.send(session, ', '.join(skills))
        self.assertIn('16 skills', reply['assistant_message'])
        self.assertIn('strongest 8–15', reply['assistant_message'])
        self.assertIn('Everything is retained', reply['assistant_message'])
        self.send(session, 'yes')
        self.assertEqual(session.conversation_state['collected_data']['skills'], skills)
        self.assertEqual(self.send(session, 'continue')['section'], 'review')
        self.assertEqual(session.conversation_state['collected_data']['skills'], skills)

    def test_one_complete_project_offers_another_and_technologies_remain_separate(self):
        session = self.start('projects')
        reply = self.project(session)
        self.assertIn('1 project', reply['assistant_message'])
        self.assertIn('2–3', reply['assistant_message'])
        first = deepcopy(session.conversation_state['collected_data']['projects'][0])
        self.assertEqual(first['technologies'], ['Django', 'REST APIs', 'React', 'AI', 'NLP'])
        self.send(session, 'add more')
        self.assertEqual(next_step(session.conversation_state)['field'], 'name')
        self.project(session, 'CV Maker')
        projects = session.conversation_state['collected_data']['projects']
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0], first)
        self.assertNotIn('section_followup', session.conversation_state)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_single_project_is_enough_and_skip_only_dismisses_advice(self):
        session = self.start('projects')
        self.project(session)
        self.send(session, 'skip')
        self.assertNotIn('projects', session.conversation_state.get('skipped_sections', []))
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, _ = build_chat_document(session)
        self.assertEqual(len(document['projects']), 1)

    def test_certification_preserves_user_wording_and_optional_count(self):
        session = self.start('certifications')
        reply = self.send(session, 'GOOGLE AI ESSENtial issued by coursra')
        self.assertIn('1 certification', reply['assistant_message'])
        self.assertIn('3–5', reply['assistant_message'])
        self.assertIn('only if you already hold', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['certifications'],
                         [{'name': 'GOOGLE AI ESSENtial', 'issuer': 'coursra'}])
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, _ = build_chat_document(session)
        self.assertEqual(document['certifications'],
                         [{'name': 'GOOGLE AI ESSENtial', 'issuer': 'coursra', 'date': '', 'url': ''}])

    def test_certificate_add_more_and_section_switch_never_add_choice_words(self):
        session = self.start('certifications')
        self.send(session, 'GOOGLE AI ESSENtial issued by coursra')
        self.send(session, 'yes')
        self.send(session, 'Google Prompting Essentials issued by Google')
        self.assertEqual([entry['name'] for entry in session.conversation_state['collected_data']['certifications']],
                         ['GOOGLE AI ESSENtial', 'Google Prompting Essentials'])
        session = self.start('skills')
        self.send(session, 'Python, Django')
        self.send(session, 'add more projects')
        self.assertNotIn('section_followup', session.conversation_state)
        self.assertEqual(next_step(session.conversation_state), {'section': 'projects', 'field': 'name'})

    def test_unrecognized_choice_is_explained_and_never_saved(self):
        session = self.start('skills')
        self.send(session, 'Python, Django')
        before = deepcopy(session.conversation_state['collected_data'])
        reply = self.send(session, 'use everything you think is best')
        self.assertIn('Say "add more"', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data'], before)

    def test_contact_correction_can_leave_count_advice_without_losing_entries(self):
        session = self.start('skills')
        self.send(session, 'Python, Django')
        self.send(session, 'change my email to updated@example.com')
        self.assertEqual(session.conversation_state['collected_data']['personal']['email'], 'updated@example.com')
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['Python', 'Django'])
        self.assertNotIn('section_followup', session.conversation_state)

    def test_fast_and_expected_year_are_separated_without_inventing_a_month(self):
        session = self.start('education')
        self.send(session, 'Bs software engineering from Fast excpected to end in 2027')
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry['institution'], 'Fast')
        self.assertEqual(entry['end_date'], '2027')
        self.assertEqual(entry['degree'], 'Bs software engineering')
        self.send(session, 'finish')
        self.assertEqual(next_step(session.conversation_state), {'section': 'education', 'field': 'end_date'})
        self.send(session, '2027-06')
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['institution'], 'Fast')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_direct_skills_answer_the_optional_prompt_without_an_extra_command(self):
        session = self.start('skills')
        session.conversation_state['target_role'] = 'Python Developer | AI Integration | Django Developer'
        session.save()
        reply = self.send(session, 'HTML, CSS, Javascript')
        self.assertIn('3 skills', reply['assistant_message'])
        self.assertNotIn('Check whether these skills', reply['assistant_message'])
        reply = self.send(session, 'Django, Rest Api, Ai integration, NLP')
        self.assertEqual(reply['section'], 'review')
        self.assertNotIn('Say "add more"', reply['assistant_message'])
        self.assertNotIn('Check whether these skills', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['skills'],
                         ['HTML', 'CSS', 'JavaScript', 'Django', 'REST APIs', 'Ai integration', 'NLP'])
        session = self.start('skills')
        self.send(session, 'Python, Django')
        self.send(session, 'add more SQL, PostgreSQL')
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['Python', 'Django', 'SQL', 'PostgreSQL'])

    def test_unchanged_relevance_advice_does_not_repeat_after_more_skills(self):
        session = self.start('skills')
        reply = self.send(session, 'Python, Figma')
        self.assertIn('Check whether these skills', reply['assistant_message'])
        reply = self.send(session, 'Django, SQL')
        self.assertNotIn('Check whether these skills', reply['assistant_message'])
        self.assertIn('Figma', session.conversation_state['collected_data']['skills'])

    def test_add_more_with_a_project_title_opens_its_description_directly(self):
        session = self.start('projects')
        self.project(session)
        first = deepcopy(session.conversation_state['collected_data']['projects'][0])
        reply = self.send(session, 'Add more Cv maker')
        self.assertEqual(next_step(session.conversation_state), {'section': 'projects', 'field': 'description'})
        self.assertNotIn('Your entries are kept. Say', reply['assistant_message'])
        self.assertEqual(session.conversation_state['pending_entry']['draft']['name'], 'Cv maker')
        self.send(session, 'Build cv maker with chatbot integration which give suggestion.')
        self.send(session, 'Use following technologies Django, PostgreSQL, React, LLM, AI')
        projects = session.conversation_state['collected_data']['projects']
        self.assertEqual(projects[0], first)
        self.assertEqual(projects[1]['name'], 'Cv maker')
        self.assertEqual(projects[1]['technologies'], ['Django', 'PostgreSQL', 'React', 'LLM', 'AI'])

    def test_explicit_certificate_details_can_answer_the_optional_prompt(self):
        session = self.start('certifications')
        self.send(session, 'Distributed Systems issued by Open Learning Academy')
        reply = self.send(session, 'Application Security issued by Independent Institute')
        self.assertEqual(reply['section'], 'review')
        self.assertEqual(session.conversation_state['collected_data']['certifications'], [
            {'name': 'Distributed Systems', 'issuer': 'Open Learning Academy'},
            {'name': 'Application Security', 'issuer': 'Independent Institute'}])

    def test_yes_requests_actual_employer_and_internship_sentence_extracts_only_the_title(self):
        session = self.start('experience')
        reply = self.send(session, 'yes')
        self.assertIn('Which company', reply['assistant_message'])
        self.assertNotIn('extracted details', reply['assistant_message'])
        self.assertFalse(any(reply['cv_updates'].values()))
        self.assertEqual(session.conversation_state['collected_data']['experience'], [])
        self.send(session, 'i completed intership as a python Developer at bitech')
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
        self.assertEqual(session.conversation_state['collected_data']['experience'],
                         [{'role': 'python Developer', 'company': 'bitech'}])
        self.send(session, 'Manage Backennd')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, _ = build_chat_document(session)
        self.assertEqual(document['experience'][0]['job_title'], 'python Developer')
        self.assertEqual(document['experience'][0]['company'], 'bitech')

    def test_graduation_sentence_cannot_leak_into_institution(self):
        session = self.start('education')
        self.send(session, 'i completed Bs software engineering from university of Mianwali. i am graduated in 2026-06')
        self.assertEqual(session.conversation_state['collected_data']['education'], [{
            'degree': 'Bs software engineering', 'institution': 'university of Mianwali',
            'field_of_study': 'software engineering', 'end_date': '2026-06'}])
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, _ = build_chat_document(session)
        self.assertEqual(document['education'][0]['institution'], 'university of Mianwali')

    def test_reported_interview_accepts_inline_additions_and_saves_clean_fields(self):
        summary = ('Software Engineering graduate and Python Developer Intern experienced in building, '
                   'testing, and debugging Python backend applications using Django and PostgreSQL.')
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Developer | AI Integration | Django Developer',
            'career_level': 'fresher', 'template_id': 'modern'})
        for answer in ('skip it', 'Abdul Quddous', 'quddous2369@gmail.com', '03036096093',
                       'Islamabad, Pakistan', 'http://linkedin.com', 'http://github.com', 'skip',
                       'i completed Bs software engineering from university of Mianwali. i am graduated in 2026-06',
                       'HTML, CSS, Javascript', 'Django, Rest Api, Ai integration, NLP',
                       'Vocal View(Ai Based Interview Plateform)',
                       'Vocal View is an AI-powered mock interview evaluation system built with Django and Python. Speech delivery is analyzed using Librosa.',
                       'Add more Cv maker', 'Build cv maker with chatbot integration which give suggestion.',
                       'Use following technologies Django, PostgreSQL, React, LLM, AI', 'yes',
                       'i completed intership as a python Developer at bitech', 'Manage Backennd',
                       'skip', 'skip', 'skip', summary):
            self.send(session, answer)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        result = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        document = result.data['cv']['data']
        self.assertEqual(document['education'][0]['institution'], 'university of Mianwali')
        self.assertEqual(document['experience'][0]['job_title'], 'python Developer')
        self.assertIn('Librosa', document['projects'][0]['technologies'])
        self.assertEqual(document['projects'][1]['technologies'], ['Django', 'PostgreSQL', 'React', 'LLM', 'AI'])
        self.assertEqual(len(document['skills']), 7)
        self.assertEqual(document['summary'], summary)
        self.assertFalse(any('Check whether these skills' in advice
                             for advice in session.conversation_state['recommendations']))


class LiteralCleanupTests(SimpleTestCase):
    def test_explicit_named_tools_in_descriptions_are_not_limited_to_a_catalogue(self):
        from chatbot.services.project_answers import project_description
        for tool in ('Librosa', 'QuartzVector', 'Acme.Signal Toolkit'):
            with self.subTest(tool=tool):
                entry = project_description('The project analyzes input using ' + tool + '.')
                self.assertEqual(entry['technologies'], [tool])
        for prose in ('The project analyzes input using browser recordings.',
                      'The project analyzes input using New York data.'):
            with self.subTest(prose=prose):
                self.assertNotIn('technologies', project_description(prose))

    def test_explicit_technology_list_introductions_preserve_unknown_tools(self):
        from chatbot.services.field_validation import extract_skills
        for prefix in ('Use following technologies ', 'I used the following tools: ', 'The following technologies: '):
            with self.subTest(prefix=prefix):
                self.assertEqual(extract_skills(prefix + 'Django, React, QuartzVector'),
                                 ['Django', 'React', 'QuartzVector'])

    def test_education_and_role_parsing_are_not_tied_to_specific_names(self):
        from chatbot.services.education_answers import parse_education, parse_employer
        for prefix in ('i graduated', 'i am graduated', 'I have graduated'):
            with self.subTest(prefix=prefix):
                result = parse_education('BS Computer Science from Eastern Institute. ' + prefix + ' in 2027-06')
                self.assertEqual(result['institution'], 'Eastern Institute')
                self.assertEqual(result['end_date'], '2027-06')
        self.assertEqual(parse_employer('I finished an internship as an AI Engineer at Example Labs'),
                         {'role': 'AI Engineer', 'company': 'Example Labs'})
        self.assertEqual(parse_employer('I worked as a Backend Developer at Example Labs'),
                         {'role': 'Backend Developer', 'company': 'Example Labs'})

    def test_provider_packed_lists_split_only_when_every_technology_is_understood(self):
        for raw in ('Django Restapi React Ai NLP', ['Django Restapi React Ai NLP']):
            response = empty_ai_response()
            response['cv_updates']['projects'] = [{'technologies': raw}]
            result, errors, _ = validated_updates(response, {})
            self.assertEqual(errors, [])
            self.assertEqual(result['cv_updates']['projects'][0]['technologies'], ['Django', 'REST APIs', 'React', 'AI', 'NLP'])
        self.assertEqual(normalise_skill_list(['Custom Django Plugin', 'React Native', 'AI ethics research']),
                         ['Custom Django Plugin', 'React Native', 'AI ethics research'])

    def test_validation_preserves_arbitrary_certificate_titles_and_issuers(self):
        for name, issuer in [('GOOGLE AI ESSENtial', 'coursra'),
                             ('google prompting essential', 'google'),
                             ('Applied Robotics Workshop', 'Independent Academy')]:
            with self.subTest(name=name):
                entry = {'name': name, 'issuer': issuer}
                response = empty_ai_response()
                response['cv_updates']['certifications'] = [entry]
                result, errors, _ = validated_updates(response, {})
                self.assertEqual(errors, [])
                self.assertEqual(result['cv_updates']['certifications'], [entry])
