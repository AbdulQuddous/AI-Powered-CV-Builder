"""Saved-CV edit regressions from the optional-entry conversation transcript.

Only fictional owned CVs and mocked providers are used. In particular, the saved
CV is context rather than evidence that a new answer repeated those facts.
"""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.question_engine import next_step
from chatbot.services.state_manager import CV_SECTIONS
from cvs.services import create_cv
from cvs.validation import build_document
from tests.test_m8 import SAMPLE_CV


class ExistingChatOptionalFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('optional-edit@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.document = build_document({
            'target_role': 'Backend Developer', 'career_level': 'experienced',
            'template_id': 'modern',
        })
        self.document['personal'].update(full_name='Alex Example', email='alex@example.com')
        self.document['skills'] = ['Python']
        self.document['languages'] = [
            {'name': 'English', 'proficiency': ''}, {'name': 'Urdu', 'proficiency': ''}]
        self.document['projects'] = [{
            'name': 'Saved Project', 'description': 'A saved Python application.',
            'technologies': ['Python'], 'url': '', 'highlights': [],
        }]
        self.cv = create_cv(user=self.user, values={'name': 'Synthetic CV', 'data': self.document})
        qwen_patch = patch('chatbot.services.conversation_service.QwenClient.generate',
                           return_value=empty_ai_response())
        self.qwen = qwen_patch.start()
        self.addCleanup(qwen_patch.stop)
        gemini_patch = patch('ai.llm.gemini_client.GeminiProvider.generate_structured',
                             side_effect=AssertionError('Chat edit tests must not call Gemini'))
        gemini_patch.start()
        self.addCleanup(gemini_patch.stop)

    def start(self):
        response = self.client.post('/api/chat/sessions/', {'cv_id': self.cv.id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ChatSession.objects.get(pk=response.data['id'])

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.id}/messages/',
                                    {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        return response.data

    def updates(self, session):
        return session.conversation_state.get('edit_updates') or {}

    def draft(self, session):
        response = self.client.get(f'/api/chat/sessions/{session.id}/draft/')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        return response.data['draft']

    def assert_saved_unchanged(self):
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.version, 1)
        self.assertEqual(self.cv.data, self.document)

    def stale_auxiliary_state(self, session, section='languages'):
        state = session.conversation_state
        state.update(
            pending_field={'section': 'education', 'field': 'end_date'},
            pending_selection={'section': 'projects', 'field': 'description'},
            language_proficiency_pending=['English', 'Urdu'],
            date_confirmation_pending={
                'section': 'education', 'field': 'end_date', 'index': 0, 'year': '2028',
            },
            edit_focus=section,
        )
        # An old optional date request must not crash while a different section
        # is explicitly requested; it is deliberately absent from the saved CV.
        state.setdefault('collected_data', {})['education'] = [
            {'degree': 'BS', 'institution': 'Example University', 'end_date': '2028'}]
        session.save(update_fields=['conversation_state'])

    def test_explicit_section_switch_clears_old_followups_and_keeps_accepted_edits(self):
        for request, section in [('i want to add skill', 'skills'),
                                 ('i want to add certificate', 'certifications'),
                                 ('i want to add language', 'languages')]:
            with self.subTest(section=section):
                session = self.start()
                self.send(session, 'add Django to my skills')
                accepted = deepcopy(self.updates(session))
                self.stale_auxiliary_state(session)
                result = self.send(session, request)
                self.assertEqual(result['section'], section)
                state = session.conversation_state
                self.assertEqual(self.updates(session), accepted)
                for key in ('pending_field', 'pending_selection', 'date_confirmation_pending',
                            'language_proficiency_pending'):
                    self.assertFalse(state.get(key), key)
                self.assertEqual(next_step(state)['section'], section)
        self.assert_saved_unchanged()

    def test_switch_away_from_real_optional_proficiency_does_not_reask_it(self):
        session = self.start()
        self.send(session, 'add languages')
        self.send(session, 'Punjabi')
        self.assertEqual(next_step(session.conversation_state)['field'], 'proficiency')
        result = self.send(session, 'i want to add certificate')
        self.assertEqual(result['section'], 'certifications')
        self.assertNotIn('specify language proficiency', result['assistant_message'])
        self.assertIn({'name': 'Punjabi'}, self.updates(session)['languages'])
        self.assertFalse(session.conversation_state.get('language_proficiency_pending'))

    def test_travel_answers_do_not_become_languages_or_trigger_proficiency(self):
        for message in ['i am going to murree', 'going to Murree']:
            with self.subTest(message=message):
                session = self.start()
                self.send(session, 'i want to add language')
                before = deepcopy(self.updates(session))
                result = self.send(session, message)
                self.assertEqual(self.updates(session), before)
                self.assertEqual(result['section'], 'languages')
                self.assertNotIn('specify language proficiency', result['assistant_message'])
                self.assertFalse(session.conversation_state.get('language_proficiency_pending'))
                self.assertEqual(self.draft(session)['languages'], self.document['languages'])
        self.assert_saved_unchanged()

    def test_qwen_cannot_copy_saved_languages_into_an_unrelated_new_answer(self):
        copied = empty_ai_response()
        copied['section'] = 'languages'
        copied['cv_updates']['languages'] = deepcopy(self.document['languages'])
        self.qwen.return_value = copied
        session = self.start()
        self.send(session, 'add languages')
        result = self.send(session, 'I am thinking about my plans for next weekend')
        self.assertFalse(self.updates(session).get('languages'))
        self.assertFalse(session.conversation_state.get('language_proficiency_pending'))
        self.assertNotIn('specify language proficiency', result['assistant_message'])
        self.assertEqual(self.draft(session)['languages'], self.document['languages'])

    def test_ambiguous_certificate_titles_need_details_before_collection(self):
        for title in ['Testy McTesterson']:
            with self.subTest(title=title):
                session = self.start()
                self.send(session, 'i want to add certificate')
                result = self.send(session, title)
                self.assertFalse(self.updates(session).get('certifications'))
                self.assertEqual(self.draft(session)['certifications'], [])
                self.assertEqual(result['section'], 'certifications')
                self.assertTrue(any(word in result['assistant_message'].lower()
                                    for word in ('confirm', 'title', 'issuer')))
                self.send(session, 'yes')
                self.assertFalse(self.updates(session).get('certifications'))
                self.send(session, 'Certification: Regional Professional Practice — Example Institute')
                self.assertEqual(self.updates(session)['certifications'][0]['name'], 'Regional Professional Practice')
        self.assert_saved_unchanged()

    def test_real_certificate_titles_and_exam_codes_are_not_whitelist_blocked(self):
        for title in ['Google UX Design Professional Certificate', 'AZ-900', 'CCNA',
                      'Microsoft Certified: Azure Fundamentals']:
            with self.subTest(title=title):
                session = self.start()
                self.send(session, 'add a certification')
                self.send(session, title)
                if not self.updates(session).get('certifications'):
                    self.send(session, 'yes')
                self.assertTrue(self.updates(session).get('certifications'))
                name = self.updates(session)['certifications'][0]['name']
                self.assertIn(title.lower(), name.lower())
        self.assert_saved_unchanged()

    def test_certificate_suffix_alone_does_not_confirm_an_ambiguous_title(self):
        session = self.start()
        self.send(session, 'i want to add certificate')
        result = self.send(session, 'robery certificate')
        self.assertFalse(self.updates(session).get('certifications'))
        self.assertEqual(result['section'], 'certifications')
        self.assertTrue(any(word in result['assistant_message'].lower()
                            for word in ('confirm', 'title', 'issuer')))
        self.send(session, 'cancel')
        self.assertEqual(self.draft(session)['certifications'], [])
        self.assert_saved_unchanged()

    def test_uncommon_language_is_confirmable_without_a_fixed_whitelist(self):
        session = self.start()
        self.send(session, 'add a language')
        self.send(session, 'Kashmiri')
        self.assertFalse(self.updates(session).get('languages'))
        self.send(session, 'yes')
        self.assertIn({'name': 'Kashmiri'}, self.updates(session)['languages'])
        self.send(session, 'keep it unspecified')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        self.assertEqual([item['name'] for item in self.draft(session)['languages']],
                         ['English', 'Urdu', 'Kashmiri'])
        self.assert_saved_unchanged()

    def test_bare_language_names_keep_click_consonants_when_confirmed(self):
        for name in ['!Xóõ', 'K!ang']:
            with self.subTest(name=name):
                session = self.start()
                self.send(session, 'add a language')
                self.send(session, name)
                self.assertFalse(self.updates(session).get('languages'))
                self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
                self.send(session, 'yes')
                self.assertIn({'name': name}, self.updates(session)['languages'])
        self.assert_saved_unchanged()

    def test_explicit_spoken_language_extraction_keeps_original_orthography(self):
        literal = empty_ai_response()
        literal['section'] = 'languages'
        literal['cv_updates']['languages'] = [{'name': '!Xóõ'}]
        self.qwen.return_value = literal
        session = self.start()
        self.send(session, 'add a language')
        self.send(session, 'I speak !Xóõ')
        self.assertIn({'name': '!Xóõ'}, self.updates(session)['languages'])
        self.assertNotIn({'name': 'I speak !Xóõ'}, self.updates(session)['languages'])
        self.assert_saved_unchanged()

    def test_recognized_two_word_certificate_is_collected_without_confirmation(self):
        session = self.start()
        self.send(session, 'add a certification')
        self.send(session, 'Python Certificate')
        self.assertEqual(self.updates(session)['certifications'], [{'name': 'Python Certificate'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def mixed_certificates(self):
        session = self.start()
        self.send(session, 'add a certification')
        result = self.send(session, 'Python Certificate, Regional Professional Practice')
        self.assertEqual(self.updates(session)['certifications'], [{'name': 'Python Certificate'}])
        self.assertEqual(result['section'], 'certifications')
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
        return session

    def test_mixed_certificates_keep_valid_sibling_and_replace_only_deferred_title(self):
        session = self.mixed_certificates()
        title = 'Google UX Design Professional Certificate'
        self.send(session, title)
        self.assertEqual([item['name'] for item in self.updates(session)['certifications']],
                         ['Python Certificate', title])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def test_mixed_certificates_cancel_keeps_the_already_accepted_sibling(self):
        session = self.mixed_certificates()
        self.send(session, 'cancel')
        self.assertEqual(self.updates(session)['certifications'], [{'name': 'Python Certificate'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def test_mixed_certificates_yes_requires_details_for_deferred_sibling(self):
        session = self.mixed_certificates()
        self.send(session, 'yes')
        self.assertEqual(self.updates(session)['certifications'], [{'name': 'Python Certificate'}])
        self.send(session, 'Certification: Regional Professional Practice')
        self.assertEqual([item['name'] for item in self.updates(session)['certifications']],
                         ['Python Certificate', 'Regional Professional Practice'])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def test_stray_acknowledgements_after_cancel_or_switch_never_become_facts(self):
        for exit_message in ['cancel', 'add a language']:
            with self.subTest(exit_message=exit_message):
                session = self.start()
                self.send(session, 'add a certification')
                self.send(session, 'Testy McTesterson')
                self.send(session, exit_message)
                for acknowledgement in ['yes', 'yes', 'okay', 'sure', 'thanks']:
                    self.send(session, acknowledgement)
                self.assertFalse(self.updates(session).get('certifications'))
                self.assertFalse(self.updates(session).get('languages'))
                self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def test_affirmative_after_switch_does_not_confirm_old_certificate(self):
        session = self.start()
        self.send(session, 'add a certification')
        self.send(session, 'Testy McTesterson')
        self.send(session, 'i want to add skill')
        self.send(session, 'yes')
        self.assertFalse(self.updates(session).get('certifications'))
        self.assertFalse(self.updates(session).get('skills'))
        self.assertEqual(self.draft(session)['certifications'], [])

    def test_cancel_discards_unconfirmed_entry_but_keeps_previously_accepted_skill(self):
        session = self.start()
        self.send(session, 'add Django to my skills')
        self.send(session, 'add a certification')
        self.send(session, 'Testy McTesterson')
        result = self.send(session, 'cancel')
        self.assertEqual(result['section'], 'review')
        self.assertFalse(self.updates(session).get('certifications'))
        self.assertIn('Django', self.updates(session)['skills'])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'yes')
        self.assertFalse(self.updates(session).get('certifications'))
        self.assert_saved_unchanged()

    def test_explicit_full_certificate_replaces_pending_ambiguous_title(self):
        session = self.start()
        self.send(session, 'add a certification')
        self.send(session, 't33ssr')
        title = 'Google UX Design Professional Certificate'
        self.send(session, title)
        if not self.updates(session).get('certifications'):
            self.send(session, 'yes')
        names = [item['name'] for item in self.updates(session)['certifications']]
        self.assertEqual(names, [title])

    def test_finish_does_not_silently_confirm_pending_optional_entry(self):
        session = self.start()
        self.send(session, 'add a certification')
        self.send(session, 'Testy McTesterson')
        result = self.send(session, 'finish')
        self.assertNotEqual(result['next_action'], 'complete')
        self.assertEqual(session.status, 'active')
        self.assertFalse(self.updates(session).get('certifications'))
        self.assertTrue(any(word in result['assistant_message'].lower()
                            for word in ('confirm', 'cancel', 'discard')))
        self.send(session, 'cancel')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')

    def test_repeated_off_topic_input_cannot_lock_out_cancel_switch_or_finish(self):
        session = self.start()
        self.send(session, 'i want to add skill')
        for text in ['murder', 'lamb cooking', 'terrorist']:
            self.send(session, text)
        self.assertFalse(self.updates(session).get('skills'))
        self.assertEqual(self.send(session, 'i want to add language')['section'], 'languages')
        for text in ['are you idiot', 'i am going to murree', 'going to Murree']:
            self.send(session, text)
        self.assertFalse(self.updates(session).get('languages'))
        self.assertEqual(self.send(session, 'cancel')['section'], 'review')
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        self.assertEqual(self.draft(session)['languages'], self.document['languages'])
        self.assert_saved_unchanged()

    def test_show_collected_is_a_concise_unsaved_review_including_project_and_removal(self):
        session = self.start()
        self.send(session, 'add Django to my skills')
        self.send(session, 'remove Python from my skills')
        self.send(session, 'add a project')
        self.send(session, 'Career Tracker')
        self.send(session, 'Tracks applications and interview notes.')
        self.send(session, 'Django')
        result = self.send(session, 'show collected information')
        message = result['assistant_message']
        self.assertIn('Career Tracker', message)
        self.assertIn('Django', message)
        self.assertIn('Python', message)
        self.assertTrue(any(word in message.lower() for word in ('unsaved', 'not saved', 'before saving')))
        for unwanted in ['Candidate skills', 'Relevant topic areas to check',
                         'Prioritize 3–5 recent', 'Highlight relevant academic projects']:
            self.assertNotIn(unwanted, message)
        self.assertLess(len(message), 4000)
        self.assertEqual(self.draft(session)['skills'], ['Django'])
        self.assert_saved_unchanged()

    def test_finish_clears_stale_auxiliary_followups_on_ready_saved_cv(self):
        session = self.start()
        self.send(session, 'add Django to my skills')
        self.stale_auxiliary_state(session, section=None)
        result = self.send(session, 'finish')
        self.assertEqual(result['next_action'], 'complete', result)
        self.assertNotIn('specify language proficiency', result['assistant_message'])
        self.assertNotIn('select a listed entry', result['assistant_message'])
        self.assertIn('Django', self.updates(session)['skills'])
        self.assert_saved_unchanged()

    def test_valid_pending_date_can_be_left_to_edit_another_section(self):
        session = self.start()
        self.stale_auxiliary_state(session, section='education')
        result = self.send(session, 'i want to add skill')
        self.assertEqual(result['section'], 'skills')
        result = self.send(session, 'Django')
        self.assertEqual(result['section'], 'review')
        self.assertIn('Django', self.updates(session)['skills'])
        self.assertEqual(self.send(session, 'finish')['next_action'], 'complete')
        self.assert_saved_unchanged()


class InitialInterviewOptionalConfirmationTests(APITestCase):
    """The same confirmation exits must work before a CV has been saved."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('initial-optional@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        for target in ('chatbot.services.conversation_service.QwenClient.generate',
                       'ai.llm.gemini_client.GeminiProvider.generate_structured'):
            mocked = patch(target, side_effect=AssertionError('Optional confirmations must stay local'))
            mocked.start()
            self.addCleanup(mocked.stop)

    def start(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Python Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {key: deepcopy(SAMPLE_CV[key]) for key in CV_SECTIONS}
        state['collected_data']['certifications'] = [{'name': 'Existing Python Certificate'}]
        state['collected_data']['languages'] = []
        state['collected_data']['achievements'] = []
        state['completed_sections'] = ['personal', 'education', 'skills', 'projects', 'experience', 'summary']
        state['missing_sections'] = ['certifications', 'achievements', 'languages']
        for group in ('personal_fields', 'education_fields', 'project_fields', 'experience_fields'):
            state[group] = dict.fromkeys(state[group], 'collected')
        state['current_section'] = 'certifications'
        session.conversation_state = state
        session.current_section = 'certifications'
        session.save()
        self.assertEqual(next_step(state)['section'], 'certifications')
        return session

    def send(self, session, message):
        response = self.client.post(f'/api/chat/sessions/{session.id}/messages/',
                                    {'message': message}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        return response.data

    def collected(self, session):
        return session.conversation_state['collected_data']

    def certificate_names(self, session):
        return [item['name'] for item in self.collected(session).get('certifications') or []]

    def pending_title(self, session, title='Testy McTesterson'):
        self.send(session, title)
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))

    def test_initial_cancel_discards_only_candidate_and_allows_a_replacement(self):
        session = self.start()
        accepted = deepcopy(self.collected(session))
        self.pending_title(session)
        result = self.send(session, 'cancel')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(self.collected(session), accepted)
        self.assertNotIn('Confirm the optional entry', result['assistant_message'])
        self.send(session, 'add a certification')
        self.send(session, 'Google UX Design Professional Certificate')
        self.assertEqual(self.certificate_names(session), [
            'Existing Python Certificate', 'Google UX Design Professional Certificate'])
        self.assertEqual(self.collected(session)['personal'], accepted['personal'])
        self.assertEqual(self.collected(session)['skills'], accepted['skills'])

    def test_initial_skip_clears_candidate_and_moves_past_certifications(self):
        session = self.start()
        self.pending_title(session)
        result = self.send(session, 'skip')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
        self.assertNotEqual(result['section'], 'certifications')
        self.assertNotIn('Testy McTesterson', result['assistant_message'])

    def test_initial_switch_clears_candidate_and_bare_yes_cannot_restore_it(self):
        session = self.start()
        self.pending_title(session)
        self.assertEqual(self.send(session, 'add a language')['section'], 'languages')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'yes')
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
        self.assertFalse(self.collected(session).get('languages'))
        self.send(session, 'English')
        self.assertEqual(self.collected(session)['languages'], [{'name': 'English'}])

    def test_initial_yes_requires_details_for_the_current_candidate(self):
        session = self.start()
        accepted = deepcopy(self.collected(session))
        self.pending_title(session)
        self.send(session, 'yes')
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
        self.send(session, 'Certification: Regional Professional Practice')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(self.certificate_names(session), [
            'Existing Python Certificate', 'Regional Professional Practice'])
        for section in ('personal', 'skills', 'projects', 'education'):
            self.assertEqual(self.collected(session)[section], accepted[section])

    def test_initial_no_dismisses_candidate_and_can_collect_a_new_title(self):
        session = self.start()
        self.pending_title(session)
        self.send(session, 'no')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
        self.send(session, 'AZ-900')
        if self.certificate_names(session) == ['Existing Python Certificate']:
            self.send(session, 'yes')
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate', 'AZ-900'])

    def test_initial_unknown_language_confirmation_also_allows_cancel(self):
        session = self.start()
        self.send(session, 'add a language')
        self.send(session, 'Kashmiri')
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
        self.assertFalse(self.collected(session).get('languages'))
        self.send(session, 'cancel')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertFalse(self.collected(session).get('languages'))
        self.send(session, 'add a language')
        self.send(session, 'English')
        self.assertEqual(self.collected(session)['languages'], [{'name': 'English'}])

    def mixed_certificates(self):
        session = self.start()
        result = self.send(session, 'Python Certificate, Regional Professional Practice')
        self.assertEqual(self.certificate_names(session),
                         ['Existing Python Certificate', 'Python Certificate'])
        self.assertEqual(result['section'], 'certifications')
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
        return session

    def test_initial_mixed_certificate_replacement_keeps_all_accepted_siblings(self):
        session = self.mixed_certificates()
        title = 'Google UX Design Professional Certificate'
        self.send(session, title)
        self.assertEqual(self.certificate_names(session),
                         ['Existing Python Certificate', 'Python Certificate', title])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_initial_mixed_certificate_cancel_keeps_accepted_siblings(self):
        session = self.mixed_certificates()
        self.send(session, 'cancel')
        self.assertEqual(self.certificate_names(session),
                         ['Existing Python Certificate', 'Python Certificate'])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_initial_mixed_certificate_yes_requires_details_for_deferred_sibling(self):
        session = self.mixed_certificates()
        self.send(session, 'yes')
        self.assertEqual(self.certificate_names(session), ['Existing Python Certificate', 'Python Certificate'])
        self.send(session, 'Certification: Regional Professional Practice')
        self.assertEqual(self.certificate_names(session),
                         ['Existing Python Certificate', 'Python Certificate', 'Regional Professional Practice'])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_initial_stray_acknowledgements_after_cancel_or_switch_never_become_facts(self):
        for exit_message in ['cancel', 'add a language']:
            with self.subTest(exit_message=exit_message):
                session = self.start()
                self.pending_title(session)
                self.send(session, exit_message)
                for acknowledgement in ['yes', 'yes', 'okay', 'sure', 'thanks']:
                    self.send(session, acknowledgement)
                self.assertEqual(self.certificate_names(session), ['Existing Python Certificate'])
                self.assertFalse(self.collected(session).get('languages'))
                self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
