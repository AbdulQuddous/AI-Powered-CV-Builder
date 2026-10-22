"""Natural education answers must retain their explicit fields and entry identity."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.question_engine import next_step
from chatbot.services.education_answers import parse_education
from chatbot.services.field_validation import validate_value, extract_skills
from chatbot.services.content_handling import is_self_harm_concern
from tests.test_m8 import SAMPLE_CV

DEGREE_ANSWER = 'I completed Bs Software ENgineering from University of Mianwali'


class AcademicParsingTests(SimpleTestCase):
    def test_model_output_cannot_bypass_institution_validation(self):
        for value in ['2022', '2022 2026', '2022–2026', 'start date 2022 end 2026']:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_value('institution', value)

    def test_unstated_fields_and_months_are_never_invented(self):
        self.assertEqual(parse_education('BS from University of Mianwali'), {
            'degree': 'BS', 'institution': 'University of Mianwali'})
        self.assertEqual(parse_education('graduated in 2026', 'end_date'), {'end_date': '2026'})
        self.assertEqual(parse_education('start date 2022 end 2026'), {'start_date': '2022', 'end_date': '2026'})

    def test_grouped_completed_degree_accepts_explicit_completion_year(self):
        self.assertEqual(parse_education(DEGREE_ANSWER + ' in 2026'), {
            'degree': 'Bs Software ENgineering', 'institution': 'University of Mianwali',
            'field_of_study': 'Software ENgineering', 'end_date': '2026'})

    def test_negation_multiple_entries_and_unrelated_prose_need_interpretation(self):
        for text in ['I did not complete BS Software Engineering',
                     'BS Software Engineering from A and MS Computer Science from B',
                     'I worked on university projects in 2026']:
            with self.subTest(text=text): self.assertIsNone(parse_education(text))
        self.assertIsNone(extract_skills('I might learn Python next year'))

    def test_distress_check_excludes_project_and_quoted_workplace_text(self):
        self.assertTrue(is_self_harm_concern('i comit sucide or not'))
        self.assertTrue(is_self_harm_concern('I want to kill myself'))
        self.assertFalse(is_self_harm_concern('I developed a suicide prevention app.'))
        self.assertFalse(is_self_harm_concern('My client said "I want to die".'))


class EducationAnswerTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('education-answers@example.com')
        cls.other = get_user_model().objects.create_user('other-education-answers@example.com')

    def setUp(self):
        self.client.force_authenticate(self.user)
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('These explicit answers must not require model guesses'))
        mocked.start(); self.addCleanup(mocked.stop)

    def start(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Frontend Developer', 'career_level': 'experienced', 'template_id': 'modern'})
        state = session.conversation_state
        state['collected_data'] = {'personal': deepcopy(SAMPLE_CV['personal']), 'skills': ['React']}
        state['completed_sections'] = ['personal', 'skills', 'experience']
        state['personal_fields'] = dict.fromkeys(state['personal_fields'], 'collected')
        state['experience_fields'] = dict.fromkeys(state['experience_fields'], 'collected')
        session.conversation_state = state; session.current_section = 'education'; session.save()
        return session

    def send(self, session, text):
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/', {'message': text}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        session.refresh_from_db()
        return result.data

    def test_exact_degree_university_and_years_need_no_repeated_facts(self):
        session = self.start()
        result = self.send(session, DEGREE_ANSWER)
        self.assertNotIn('confirm extracted', result['assistant_message'])
        self.assertEqual(next_step(session.conversation_state), {'section': 'education', 'field': 'end_date'})
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry['degree'], 'Bs Software ENgineering')
        self.assertEqual(entry['institution'], 'University of Mianwali')
        self.assertEqual(entry['field_of_study'], 'Software ENgineering')
        self.assertNotIn('start_date', entry); self.assertNotIn('end_date', entry)
        self.assertEqual(self.send(session, 'start date 2022 end 2026')['section'], 'projects')
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry['institution'], 'University of Mianwali')
        self.assertEqual((entry['start_date'], entry['end_date']), ('2022', '2026'))

    def test_short_degree_infers_only_the_explicit_specialization(self):
        for answer in ['bs software engineering', 'BS in Software Engineering',
                       'Bachelor of Science in Software Engineering']:
            with self.subTest(answer=answer):
                session = self.start(); self.send(session, answer)
                self.assertEqual(next_step(session.conversation_state)['field'], 'institution')
                self.assertIn('software engineering', session.conversation_state['collected_data']['education'][0]['field_of_study'].lower())
                self.send(session, 'University of Mianwali')
                self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')

    def test_dates_given_at_institution_question_are_never_saved_as_the_university(self):
        session = self.start(); self.send(session, 'BS Software Engineering')
        self.send(session, 'start date 2022 end 2026')
        self.assertEqual(next_step(session.conversation_state)['field'], 'institution')
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertNotIn('institution', entry)
        self.assertEqual(entry['start_date'], '2022')
        self.assertEqual(self.send(session, 'University of Mianwali')['section'], 'projects')

    def test_university_can_be_supplied_before_degree(self):
        session = self.start(); self.send(session, 'University of Mianwali')
        self.assertEqual(next_step(session.conversation_state)['field'], 'degree')
        self.send(session, 'BS Software Engineering')
        self.assertEqual(len(session.conversation_state['collected_data']['education']), 1)
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')

    def test_explicit_months_and_ranges_are_normalized_without_inventing_months(self):
        for answer, start, end in [
            ('BS Software Engineering from University of Mianwali, 2022–2026', '2022', '2026'),
            ('I completed BS Software Engineering from University of Mianwali, start date September 2022 end June 2026', '2022-09', '2026-06'),
            ('BS Software Engineering from University of Mianwali, from 2022-09 to 2026-06', '2022-09', '2026-06'),
        ]:
            with self.subTest(answer=answer):
                session = self.start(); self.send(session, answer)
                entries = session.conversation_state['collected_data']['education']
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]['institution'], 'University of Mianwali')
                self.assertEqual((entries[0]['start_date'], entries[0]['end_date']), (start, end))
                self.assertEqual(next_step(session.conversation_state)['section'], 'projects')

    def test_graduation_month_sentence_and_invalid_date_do_not_overwrite_institution(self):
        session = self.start(); self.send(session, DEGREE_ANSWER)
        result = self.send(session, 'graduated in 2026-13')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')
        self.send(session, 'I graduated in June 2026')
        self.assertEqual(session.conversation_state['collected_data']['education'][0]['end_date'], '2026-06')

    def test_reversed_dates_do_not_advance_and_preserve_valid_siblings(self):
        session = self.start(); self.send(session, DEGREE_ANSWER)
        result = self.send(session, 'start date 2026 end 2022')
        self.assertEqual(result['intent'], 'clarify_information')
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry['institution'], 'University of Mianwali')
        self.assertNotIn('end_date', entry)

    def test_date_answer_with_multiple_entries_requires_identity(self):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['education'] = [{'degree': 'BS'}, {'degree': 'MS'}]
        state['education_fields']['degree'] = 'collected'
        session.conversation_state = state; session.save()
        before = deepcopy(state['collected_data']['education'])
        result = self.send(session, 'start date 2022 end 2026')
        self.assertEqual(result['intent'], 'clarify_information')
        self.assertEqual(session.conversation_state['collected_data']['education'], before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'institution')

    def test_new_education_in_existing_cv_keeps_the_saved_entry(self):
        from cvs.services import create_cv
        cv = create_cv(user=self.user, values={'name': 'Existing', 'data': SAMPLE_CV})
        session = create_chat_session(user=self.user, cv_id=cv.id)
        self.send(session, 'add another degree'); self.send(session, DEGREE_ANSWER)
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')
        self.assertEqual(self.send(session, 'start date 2022-09 end 2026-06')['section'], 'review')
        self.assertEqual(self.send(session, 'No other thing')['next_action'], 'complete')
        saved = self.client.post('/api/cvs/from-chat/', {'session_id': str(session.id), 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['cv']['data']['education'][0], SAMPLE_CV['education'][0])
        self.assertEqual(saved.data['cv']['data']['education'][1]['institution'], 'University of Mianwali')

    def test_certificate_followup_offers_finish_and_understands_no_other_thing(self):
        from cvs.services import create_cv
        for ending in ['No other thing', 'nothing else', 'no more changes', 'no thanks']:
            with self.subTest(ending=ending):
                cv = create_cv(user=self.user, values={'name': 'Existing', 'data': SAMPLE_CV})
                session = create_chat_session(user=self.user, cv_id=cv.id)
                self.send(session, 'i want to add another certificate')
                result = self.send(session, 'Google Ai prompting Essential')
                self.assertFalse(session.conversation_state['edit_updates'].get('certifications'))
                result = self.send(session, 'Certification: Google Ai prompting Essential')
                self.assertIn('finish', result['assistant_message'].lower())
                self.assertEqual(self.send(session, ending)['next_action'], 'complete')
                cv.refresh_from_db(); self.assertEqual(cv.version, 1)

    def test_transcript_skills_and_languages_preserve_every_explicit_item(self):
        session = self.start()
        session.conversation_state['pending_field'] = {'section': 'skills', 'field': 'skills'}; session.save()
        self.send(session, 'I like to highlight React, Next, Node, Javascript, HTML, CSS')
        self.assertEqual(session.conversation_state['collected_data']['skills'], ['React', 'Next.js', 'Node.js', 'JavaScript', 'HTML', 'CSS'])
        session.conversation_state['pending_field'] = {'section': 'languages', 'field': 'languages'}; session.save()
        self.send(session, 'English urdu saraiki hindku')
        self.assertEqual([entry['name'] for entry in session.conversation_state['collected_data']['languages']], ['English', 'Urdu', 'Saraiki', 'Hindku'])

    def test_transcript_certificate_separates_explicit_issue_date(self):
        session = self.start()
        session.conversation_state['pending_field'] = {'section': 'certifications', 'field': 'certifications'}; session.save()
        self.send(session, 'Giki ai advance bootcamp issue date agust2026')
        self.assertEqual(session.conversation_state['collected_data']['certifications'], [
            {'name': 'Giki ai advance bootcamp', 'date': '2026-08'}])

    def test_role_at_company_is_not_stored_as_a_company_name(self):
        session = self.start()
        session.conversation_state['experience_fields'] = dict.fromkeys(session.conversation_state['experience_fields'], 'missing')
        session.conversation_state['completed_sections'].remove('experience')
        session.conversation_state['pending_field'] = {'section': 'experience', 'field': 'company'}; session.save()
        self.send(session, 'Frontend Developer at bitech')
        self.assertEqual(session.conversation_state['collected_data']['experience'], [
            {'company': 'bitech', 'role': 'Frontend Developer'}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')

    def test_nothing_else_during_education_cannot_become_a_degree_or_skip_required_fields(self):
        session = self.start()
        self.assertEqual(self.send(session, 'No other thing')['next_action'], 'ask_question')
        self.assertEqual(next_step(session.conversation_state)['field'], 'degree')
        self.assertEqual(session.status, 'active')
        self.assertNotIn('education', session.conversation_state['collected_data'])

    def contaminated(self, *, history=True):
        session = self.start()
        state = session.conversation_state
        state['collected_data']['education'] = [{
            'degree': 'Bs Software Engineering', 'field_of_study': 'Software Engineering',
            'institution': 'start date 2022 end 2026', 'end_date': '2026'}]
        state['education_fields'] = dict.fromkeys(state['education_fields'], 'collected')
        state['completed_sections'].append('education')
        state['undo_state'] = deepcopy(state)
        session.conversation_state = state; session.save()
        if history:
            for text in [DEGREE_ANSWER, 'start date 2022 end 2026']:
                ChatMessage.objects.create(session=session, role='user', content=text)
        return session

    def test_resume_repairs_only_the_history_proven_date_as_university(self):
        session = self.contaminated()
        before = deepcopy(session.conversation_state['collected_data']['personal'])
        count = session.messages.count()
        response = self.client.get(f'/api/chat/sessions/{session.id}/')
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        entry = session.conversation_state['collected_data']['education'][0]
        self.assertEqual(entry['institution'], 'University of Mianwali')
        self.assertEqual(entry['start_date'], '2022')
        self.assertEqual(session.conversation_state['undo_state']['collected_data']['education'][0], entry)
        self.assertEqual(session.conversation_state['collected_data']['personal'], before)
        self.assertEqual(session.messages.count(), count)

    def test_recovery_does_not_rewrite_without_proof_or_for_saved_or_multiple_entries(self):
        for options in ['no-history', 'saved', 'multiple']:
            with self.subTest(options=options):
                session = self.contaminated(history=options != 'no-history')
                state = session.conversation_state
                if options == 'saved': state['chat_saved_cv_id'] = 'saved'
                if options == 'multiple': state['collected_data']['education'].append({'degree': 'MS'})
                session.save(); before = deepcopy(state)
                self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
                self.assertEqual(session.conversation_state, before)

    def test_recovery_is_owner_scoped_and_rejects_stale_messages(self):
        session = self.contaminated(); before = session.updated_at.isoformat()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/chat/sessions/{session.id}/').status_code, 404)
        self.client.force_authenticate(self.user)
        self.client.get(f'/api/chat/sessions/{session.id}/')
        result = self.client.post(f'/api/chat/sessions/{session.id}/messages/',
            {'message': 'graduated in 2026', 'expected_updated_at': before}, format='json')
        self.assertEqual(result.status_code, 409)

    def test_recovery_does_not_restore_an_old_university_over_later_changes(self):
        for evidence in ['accepted', 'correction']:
            with self.subTest(evidence=evidence):
                session = self.contaminated()
                if evidence == 'accepted':
                    ChatMessage.objects.create(session=session, role='assistant', content='Collected',
                                               cv_updates={'education': [{'institution': 'FAST'}]})
                else:
                    ChatMessage.objects.create(session=session, role='user', content='Change my university to FAST')
                self.client.get(f'/api/chat/sessions/{session.id}/'); session.refresh_from_db()
                self.assertNotIn('institution', session.conversation_state['collected_data']['education'][0])
                self.assertEqual(next_step(session.conversation_state)['field'], 'institution')

    def test_transcript_distress_message_pauses_cv_collection_instead_of_redirecting(self):
        session = self.start(); before = deepcopy(session.conversation_state['collected_data'])
        result = self.send(session, 'i comit sucide or not')
        self.assertIn('immediate danger', result['assistant_message'])
        self.assertNotIn('What degree', result['assistant_message'])
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.send(session, 'yes')
        self.assertEqual(session.conversation_state['collected_data'], before)
        self.assertEqual(self.send(session, 'resume CV')['section'], 'education')
        self.send(session, DEGREE_ANSWER)
        self.assertEqual(next_step(session.conversation_state)['field'], 'end_date')
