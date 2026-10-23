"""Career-aware advice remains separate from user-confirmed M5/M10 facts."""
from copy import deepcopy
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from jsonschema import Draft202012Validator
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from chatbot.services.career_profiles import PROFILES, normalize_profile
from chatbot.services.career_guidance import (candidate_skills, skill_advice, guidance_data,
    guidance_sections, guidance_message, ranked_entries, guidance_request)
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.question_engine import next_step
from chatbot.services.qwen_client import build_qwen_messages
from chatbot.services.response_validator import CHAT_RESPONSE_SCHEMA
from chatbot.services.state_manager import ensure_state, CV_SECTIONS
from cvs.chat_import import build_chat_document
from cvs.services import create_cv, update_cv
from cvs.validation import validate_document
from tests.test_m8 import SAMPLE_CV


class CareerGuidanceRulesTests(SimpleTestCase):
    def state(self, **values):
        return ensure_state({'target_role': 'Python Backend Developer', 'career_level': 'experienced',
                             'question_profile': 'mid_level', 'collected_data': deepcopy(SAMPLE_CV), **values})

    def test_six_profiles_keep_canonical_enum_and_old_aliases(self):
        for label, expected in [('Student', ('student', 'other')), ('Fresher', ('fresher', 'fresher')),
                ('Junior', ('junior', 'experienced')), ('Mid-Level', ('mid_level', 'experienced')),
                ('mid', ('mid_level', 'experienced')), ('experienced', ('mid_level', 'experienced')),
                ('Senior', ('senior', 'experienced')), ('Executive', ('executive', 'experienced'))]:
            with self.subTest(label=label):
                state = normalize_profile({'career_level': label})
                self.assertEqual((state['question_profile'], state['career_level']), expected)

    def test_relevant_candidates_are_bounded_unique_and_profile_aware(self):
        for profile in PROFILES:
            state = self.state(question_profile=profile)
            choices = candidate_skills(state)
            self.assertGreaterEqual(len(choices), 8)
            self.assertLessEqual(len(choices), 15)
            self.assertEqual(len(set(choices)), len(choices))
            if profile == 'senior': self.assertIn('Mentoring', choices)
            if profile == 'executive': self.assertIn('Strategy', choices)
        java = candidate_skills(self.state(target_role='Java Backend Developer'))
        self.assertIn('Spring Boot', java); self.assertNotIn('Django', java)
        combined = candidate_skills(self.state(target_role='AI/ML Engineer & Backend Developer'))
        self.assertIn('Django', combined); self.assertIn('Machine learning', combined)
        frontend = candidate_skills(self.state(target_role='Frontend Engineer'))
        self.assertIn('Web accessibility', frontend); self.assertNotIn('PostgreSQL', frontend)

    def test_unknown_domain_gets_honest_general_guidance(self):
        state = self.state(target_role='Marine Biologist')
        message = guidance_message(state, 'skills')
        self.assertIn('more specific role or job description', message)
        self.assertNotIn('Django', message)

    def test_duplicates_and_other_domains_are_suggestions_not_deletions(self):
        state = self.state()
        data = {'skills': ['Python', 'python', 'NLP', 'Natural language processing', 'Figma', 'Elixir', 'Original unusual skill']}
        before = deepcopy(data)
        advice = '\n'.join(skill_advice(state, data))
        self.assertIn('duplicate', advice); self.assertIn('Figma', advice)
        self.assertNotIn('Elixir', advice); self.assertNotIn('Original unusual skill', advice)
        self.assertEqual(data, before)

    def test_fresher_numbers_are_optional_and_senior_executive_focus_differs(self):
        fresher = guidance_sections(self.state(question_profile='fresher'))
        self.assertIn('2–3', fresher['projects'][0]); self.assertIn('optional', fresher['experience'][0])
        self.assertIn('mentoring', guidance_sections(self.state(question_profile='senior'))['experience'][0])
        self.assertIn('governance', guidance_sections(self.state(question_profile='executive'))['experience'][0])
        self.assertIn('independent ownership', guidance_sections(self.state())['experience'][0])
        self.assertIn('hands-on delivery', guidance_sections(self.state(question_profile='junior'))['experience'][0])

    def test_rankings_use_only_supplied_entries_and_keep_original_numbers(self):
        state = self.state()
        state['collected_data']['projects'] = [
            {'name': 'Visual design portfolio', 'description': 'Created visual assets in Figma.'},
            {'name': 'API service', 'description': 'Built Django REST APIs using PostgreSQL and Git.'},
            {'name': 'Unspecified project', 'description': ''}]
        before = deepcopy(state)
        ranked = ranked_entries(state, 'projects')
        self.assertEqual(ranked[0]['index'], 1)
        message = guidance_message(state, 'projects')
        self.assertIn('2. API service', message)
        self.assertIn('relevance needs your confirmation', message)
        self.assertEqual(state, before)

    def test_missing_education_and_existing_credentials_are_grounded(self):
        state = self.state()
        state['collected_data']['education'] = [{'degree': 'BS', 'end_date': '2026'}]
        state['collected_data']['certifications'] = [{'name': 'Django Course', 'issuer': 'Example Academy'}]
        message = guidance_message(state, 'education')
        self.assertIn('institution', message); self.assertIn('field of study', message); self.assertIn('confirm the month', message)
        self.assertIn('only if confirmed', message)
        certs = guidance_message(state, 'certifications')
        self.assertIn('3–5', certs); self.assertIn('Django Course', certs)
        self.assertIn('if you already hold', certs); self.assertIn('topic areas', certs)

    def test_saved_edit_guidance_sees_existing_and_pending_facts_without_mutating(self):
        state = self.state(mode='edit_existing', existing_cv=deepcopy(SAMPLE_CV),
                           edit_updates={'skills': ['Docker'], 'education': [{'institution': 'Example University', 'degree': 'BS Software Engineering', 'grade': 'A'}]},
                           removed_skills=['Git'])
        before = deepcopy(state)
        data = guidance_data(state)
        self.assertIn('Python', data['skills']); self.assertIn('Docker', data['skills']); self.assertNotIn('Git', data['skills'])
        self.assertEqual(len(data['education']), 1)
        self.assertEqual(data['education'][0]['grade'], 'A')
        self.assertEqual(state, before)

    def test_length_is_advisory_and_never_claims_an_actual_page_count(self):
        state = self.state(question_profile='fresher')
        state['collected_data']['summary'] = 'Confirmed career information. ' * 200
        advice = guidance_sections(state)['review'][0]
        self.assertIn('about', advice); self.assertIn('words', advice); self.assertIn('rendered preview', advice)
        self.assertNotIn('must', advice)

    def test_guidance_commands_do_not_misclassify_factual_achievements(self):
        for value, topic in [('Recommend skills', 'skills'), ('Which projects should I include?', 'projects'),
                             ('prioritize certifications', 'certifications'), ('CV suggestions', 'all')]:
            self.assertEqual(guidance_request(value), topic)
        self.assertIsNone(guidance_request('I recommended skills development to the project team.'))


class CareerGuidanceConversationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('career-guidance@example.com')
        cls.other = get_user_model().objects.create_user('career-guidance-other@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.qwen = patch('chatbot.services.conversation_service.QwenClient.generate',
                          side_effect=AssertionError('Advice must not require extraction')).start()
        self.gemini = patch('ai.llm.gemini_client.GeminiProvider.generate_structured',
                            side_effect=AssertionError('No Gemini for M5 suggestions')).start()
        self.addCleanup(patch.stopall)

    def start(self, *, review=False, profile='fresher'):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Backend Developer', 'career_level': profile, 'template_id': 'modern'})
        session.conversation_state.setdefault('collected_data', {'personal': {}})
        session.save()
        if review:
            state = session.conversation_state
            state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
            state['completed_sections'] = list(CV_SECTIONS)
            state['skipped_sections'] = []
            for key in ('personal_fields', 'education_fields', 'experience_fields', 'project_fields'):
                state[key] = dict.fromkeys(state[key], 'collected')
            session.conversation_state = state; session.save()
        return session

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {'assistant_message', 'intent', 'section', 'cv_updates', 'next_action'})
        for field in ('assistant_message', 'intent', 'section', 'next_action'):
            self.assertTrue(Draft202012Validator(CHAT_RESPONSE_SCHEMA['properties'][field]).is_valid(response.data[field]), field)
        session.refresh_from_db()
        return response.data

    def test_api_accepts_all_six_profiles_without_adding_canonical_values(self):
        for label in ('Student', 'Fresher', 'Junior', 'Mid-Level', 'Senior', 'Executive'):
            result = self.client.post('/api/chat/sessions/', {'target_role': 'Backend Developer',
                'career_level': label, 'template_id': 'classic'}, format='json')
            self.assertEqual(result.status_code, 201, result.data)
            session = ChatSession.objects.get(pk=result.data['id'])
            self.assertIn(session.conversation_state['career_level'], ('fresher', 'experienced', 'other'))
            self.assertEqual(session.conversation_state['template_id'], 'classic')
        self.assertEqual(self.client.post('/api/chat/sessions/', {'career_level': 'invented-level'}, format='json').status_code, 400)

    def test_chat_career_selection_and_correction_work_for_every_profile(self):
        for label, profile in [('student', 'student'), ('fresher', 'fresher'), ('junior', 'junior'),
                               ('mid-level', 'mid_level'), ('senior', 'senior'), ('executive', 'executive')]:
            session = create_chat_session(user=self.user, initial_values={'target_role': 'Backend Developer'})
            self.send(session, label)
            self.assertEqual(session.conversation_state['question_profile'], profile)
            self.assertEqual(session.conversation_state['career_level'], PROFILES[profile][1])
        self.send(session, 'change my career level to mid-level')
        self.assertEqual(session.conversation_state['question_profile'], 'mid_level')

    def test_suggestions_and_yes_no_never_become_facts_or_skips(self):
        session = self.start()
        before = deepcopy(session.conversation_state['collected_data'])
        step = next_step(session.conversation_state)
        for command in ('recommend skills', 'yes', 'all of them', 'use your suggestions', 'no'):
            reply = self.send(session, command)
            self.assertEqual(reply['intent'], 'give_suggestion')
            envelope = empty_ai_response(); envelope.update(reply)
            Draft202012Validator(CHAT_RESPONSE_SCHEMA).validate(envelope)
            self.assertFalse(any(reply['cv_updates'].values()))
            self.assertEqual(session.conversation_state['collected_data'], before)
            self.assertEqual(next_step(session.conversation_state), step)
        self.qwen.assert_not_called(); self.gemini.assert_not_called()

    def test_automatic_guidance_does_not_repeat_on_each_education_question(self):
        session = self.start()
        session.conversation_state['pending_field'] = {'section': 'skills', 'field': 'skills'}
        session.conversation_state['personal_fields'] = dict.fromkeys(session.conversation_state['personal_fields'], 'collected')
        session.conversation_state['completed_sections'] = ['personal']
        session.save()
        reply = self.send(session, ', '.join('Skill ' + str(i) for i in range(20)))
        self.assertIn('20 skills', reply['assistant_message'])
        self.assertIn('strongest 8–15', reply['assistant_message'])
        self.send(session, 'continue')
        reply = self.send(session, 'BS')
        self.assertNotIn('large skills list', reply['assistant_message'])
        self.assertNotIn('20 skills', reply['assistant_message'])
        self.assertNotIn('Highlight relevant academic projects', reply['assistant_message'])

    def test_normal_interview_surfaces_skill_candidates_and_fresher_project_guidance(self):
        session = self.start()
        for answer in ('Ali Khan', 'ali@example.com', '+923001234567', 'skip', 'skip', 'skip', 'skip',
                       'BS in Software Engineering from Example University'):
            self.send(session, answer)
        reply = self.send(session, '2026-06')
        self.assertEqual(reply['section'], 'skills')
        self.assertIn('8–15', reply['assistant_message']); self.assertIn('Candidate skills', reply['assistant_message'])
        self.assertIn('PostgreSQL', reply['assistant_message'])
        self.assertNotIn('skills', session.conversation_state['collected_data'])
        reply = self.send(session, 'Python, Django')
        self.assertEqual(reply['section'], 'skills'); self.assertIn('2 skills', reply['assistant_message'])
        reply = self.send(session, 'continue')
        self.assertEqual(reply['section'], 'projects'); self.assertIn('2–3', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['Python', 'Django'])

    def test_unrelated_skills_are_flagged_but_retained_after_explicit_answer(self):
        session = self.start()
        session.conversation_state['pending_field'] = {'section': 'skills', 'field': 'skills'}; session.save()
        reply = self.send(session, 'Python, Django, Figma, Elixir')
        self.assertIn('Check whether these skills', reply['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['Python', 'Django', 'Figma', 'Elixir'])

    def test_explicit_removal_of_a_confirmed_uncommon_skill_needs_no_model_guess(self):
        session = self.start(review=True)
        session.conversation_state['collected_data']['skills'] += ['Figma', 'Elixir']
        session.save()
        self.send(session, 'remove Figma from my skills')
        document, _ = build_chat_document(session)
        self.assertNotIn('Figma', document['skills']); self.assertIn('Elixir', document['skills'])
        self.assertIn('Figma', session.conversation_state['collected_data']['skills'])
        self.qwen.assert_not_called()

    def projects(self, session):
        entries = []
        for name in ('Visual portfolio', 'API service', 'Database tool', 'Community project'):
            entry = deepcopy(SAMPLE_CV['projects'][0]); entry['name'] = name
            entries.append(entry)
        session.conversation_state['collected_data']['projects'] = entries
        session.save()
        return deepcopy(entries)

    def test_prioritizing_is_read_only_until_explicit_subset_then_save_is_idempotent(self):
        session = self.start(review=True)
        entries = self.projects(session)
        reply = self.send(session, 'prioritize projects')
        self.assertIn('2–3', reply['assistant_message'])
        self.assertNotIn('display_entry_indexes', session.conversation_state)
        self.assertEqual(session.conversation_state['collected_data']['projects'], entries)
        self.send(session, 'select projects 3, 1')
        document, _ = build_chat_document(session)
        self.assertEqual([row['name'] for row in document['projects']], ['Database tool', 'Visual portfolio'])
        self.assertEqual(session.conversation_state['collected_data']['projects'], entries)
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        first = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        again = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk)}, format='json')
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(first.data['cv']['data'], again.data['cv']['data'])
        self.assertEqual(first.data['cv']['version'], again.data['cv']['version'])
        self.assertEqual(validate_document(first.data['cv']['data'])['meta']['template_id'], 'modern')

    def test_invalid_subset_keeps_previous_selection_and_source(self):
        session = self.start(review=True); entries = self.projects(session)
        self.send(session, 'select projects 2, 1')
        for command in ('select projects 0', 'select projects 99', 'select projects 1, 1', 'select projects banana'):
            self.send(session, command)
            self.assertEqual(session.conversation_state['display_entry_indexes']['projects'], [1, 0])
            self.assertEqual(session.conversation_state['collected_data']['projects'], entries)

    def test_certification_subset_omits_unselected_year_without_demanding_month(self):
        session = self.start(review=True)
        session.conversation_state['collected_data']['certifications'] = [
            {'name': 'Earlier Course', 'date': '2022'}, {'name': 'Django Course', 'date': '2026-05'}]
        session.save()
        self.send(session, 'select certifications 2')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        document, warnings = build_chat_document(session)
        self.assertEqual([row['name'] for row in document['certifications']], ['Django Course'])
        self.assertEqual(warnings, [])

    def test_help_in_existing_cv_uses_saved_data_and_does_not_change_version(self):
        cv = create_cv(user=self.user, values={'name': 'Saved CV', 'data': SAMPLE_CV})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        before = deepcopy(cv.data)
        reply = self.send(session, 'recommend skills')
        self.assertIn('Django', reply['assistant_message'])
        self.assertEqual(session.conversation_state['edit_updates'], {'personal': {}})
        cv.refresh_from_db(); self.assertEqual(cv.version, 1); self.assertEqual(cv.data, before)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': 'recommend skills'}).status_code, 404)

    def test_one_project_and_no_experience_or_certificates_can_still_finish(self):
        session = self.start(review=True)
        original = deepcopy(session.conversation_state['collected_data'])
        self.send(session, 'CV suggestions'); self.send(session, 'no')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        self.assertEqual(session.conversation_state['collected_data'], original)
        document, _ = build_chat_document(session)
        self.assertEqual(len(document['projects']), 1)
        self.assertEqual(document['experience'], []); self.assertEqual(document['certifications'], [])

    def test_saved_cv_subset_is_proposed_then_applied_once_with_versioning(self):
        data = deepcopy(SAMPLE_CV)
        for name in ('Second project', 'Third project'):
            entry = deepcopy(data['projects'][0]); entry['name'] = name; data['projects'].append(entry)
        cv = create_cv(user=self.user, values={'name': 'Saved projects', 'data': data})
        session = create_chat_session(user=self.user, cv_id=cv.pk)
        self.send(session, 'prioritize projects'); self.send(session, 'select projects 3, 1')
        cv.refresh_from_db(); self.assertEqual(cv.data, data); self.assertEqual(cv.version, 1)
        self.send(session, 'finish')
        response = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk), 'expected_version': 1}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        cv.refresh_from_db(); self.assertEqual(cv.version, 2)
        self.assertEqual([row['name'] for row in cv.data['projects']], ['Third project', 'Employee Management System'])
        self.assertEqual(cv.data['education'], data['education'])
        update_cv(user=self.user, cv_id=cv.pk, values={'name': 'Manual rename', 'expected_version': 2})
        again = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.pk), 'expected_version': 1}, format='json')
        self.assertEqual(again.status_code, 200, again.data)
        cv.refresh_from_db(); self.assertEqual(cv.version, 3); self.assertEqual(cv.name, 'Manual rename')

    def test_qwen_context_keeps_profile_and_excludes_suggestions_and_contacts(self):
        session = self.start(profile='mid-level')
        session.conversation_state['pending_field'] = {'section': 'projects', 'field': 'description'}
        self.send(session, 'recommend skills')
        payload = json.loads(build_qwen_messages(session, 'I built a volunteer scheduling service.')[1]['content'])
        self.assertEqual(payload['context']['question_profile'], 'mid_level')
        serialized = json.dumps(payload)
        self.assertNotIn('candidate', serialized.lower()); self.assertNotIn('ali@example.com', serialized)
