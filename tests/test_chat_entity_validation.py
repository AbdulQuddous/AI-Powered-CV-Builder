"""Wrong entity types and noise cannot become employer or credential facts."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from chatbot.models import ChatSession
from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.conversation_service import create_chat_session
from chatbot.services.entity_validation import entity_problem, obvious_noise
from chatbot.services.education_answers import parse_certificate
from chatbot.services.message_routing import classify
from chatbot.services.question_engine import next_step
from chatbot.services.qwen_client import adapt_extraction
from chatbot.services.section_answers import section_request
from chatbot.services.optional_answers import clear_certificate
from cvs.services import create_cv
from tests.test_m8 import SAMPLE_CV


class EntityValidationTests(SimpleTestCase):
    def test_experience_typos_are_commands_without_facts(self):
        for message in ['i want to add xperience', 'add experiance', 'please add experince',
                        'want to add expeerience', 'i want to add experiece', 'add expreience']:
            with self.subTest(message=message):
                self.assertEqual(section_request(message), ('experience', 'add'))
        self.assertIsNone(section_request('I worked at Xperience Systems'))

    def test_section_command_typo_matching_is_bounded_to_commands(self):
        for message, section, operation in [('add cetificate', 'certifications', 'add'),
                                             ('edit educaton', 'education', 'edit'),
                                             ('update projcet to my cv', 'projects', 'edit')]:
            with self.subTest(message=message):
                self.assertEqual(section_request(message), (section, operation))
        for message in ['I worked at Experiece Systems', 'add experience at Example Systems',
                        'add project called Scheduler', 'add unknown', 'add exxxrience', 'add ski']:
            self.assertIsNone(section_request(message), message)

    def test_direct_fool_variants_are_abuse_but_workplace_quotes_remain_eligible(self):
        for text in ['are  you fool', 'are you a fool?', 'you are a fool', 'r u a fool']:
            self.assertEqual(classify(text), 'inappropriate', text)
        for text in ['My manager called me a fool.', 'Developed fool-proof validation.',
                     '"The Fool" is the title of my project.']:
            self.assertNotEqual(classify(text), 'inappropriate', text)

    def test_random_labels_are_rejected_without_rejecting_real_codes_or_brands(self):
        for label in ['ter45fase4', 't33ssr', 'asdfghjkl', 'aaaaaa']:
            self.assertTrue(obvious_noise(label), label)
        for label in ['AZ-900', 'AWS SAA-C03', '1Z0-071', 'ISO27001', 'CS50x',
                      'eJPTv2', 'n8n', '37signals', 'a16z', '東京食堂']:
            self.assertFalse(obvious_noise(label), label)

    def test_activity_is_not_an_employer_without_explicit_workplace_context(self):
        self.assertIsNotNone(entity_problem('experience', 'company', 'lamb cooking', 'lamb cooking'))
        self.assertIsNone(entity_problem('experience', 'company', 'Lamb Cooking', 'Company: Lamb Cooking'))
        self.assertIsNone(entity_problem('experience', 'role', 'Chef', 'Chef'))
        self.assertIsNone(entity_problem('certifications', 'name', 'Lamb Cooking Certificate', 'Lamb Cooking Certificate'))

    def test_certificate_title_punctuation_is_not_invented_issuer_metadata(self):
        title = 'AWS Certified Solutions Architect - Associate'
        self.assertIsNone(parse_certificate(title))
        self.assertEqual(parse_certificate('Certification: ' + title), {'name': title})
        self.assertIsNone(parse_certificate('Professional Certificate; Advanced Level'))

    def test_explicit_certificate_issuer_and_date_are_collected_together(self):
        self.assertEqual(parse_certificate('Certification: Google AI Essentials — Google issue date 2026-06'),
                         {'name': 'Google AI Essentials', 'issuer': 'Google', 'date': '2026-06'})
        self.assertEqual(parse_certificate('Regional Professional Practice; issuer: Example Institute'),
                         {'name': 'Regional Professional Practice', 'issuer': 'Example Institute'})

    def test_issuer_cue_typo_does_not_become_part_of_the_certificate_title(self):
        for cue in ('issued', 'issud', 'issue', 'issuedd'):
            with self.subTest(cue=cue):
                self.assertEqual(parse_certificate('Advance Ai bootcamp certificate ' + cue + ' by GIKI'),
                                 {'name': 'Advance Ai bootcamp certificate', 'issuer': 'GIKI'})

    def test_polite_certificate_requests_preserve_literal_title_and_issuer(self):
        for prefix in ('Could you add', 'Can you please include', 'I want to add'):
            self.assertEqual(parse_certificate(prefix + ' Murder Investigation Certificate issued by Example Academy?'),
                             {'name': 'Murder Investigation Certificate', 'issuer': 'Example Academy'})

    def test_certificate_metadata_cannot_override_an_invalid_or_missing_title(self):
        for metadata in ({'issuer': 'PITB'}, {'date': '2026-06'}, {'url': 'https://example.test/credential'}):
            with self.subTest(metadata=metadata):
                self.assertFalse(clear_certificate({'name': 'Murderer in pakistan', **metadata}))
                self.assertFalse(clear_certificate(metadata))
        for name in ('Murder Investigation Certificate', 'Serial Killer Profiling Certificate',
                     'Murderer in Fiction Certificate', 'Regional Professional Practice'):
            self.assertTrue(clear_certificate({'name': name, 'issuer': 'Example Institute'}), name)

    def test_non_occupational_labels_and_direct_harm_are_not_work_fields(self):
        for field, value in [('role', 'a murderer'), ('job_title', 'Murderer'), ('role', 'My role is a murderer'),
                             ('responsibilities', ['Murder of persons']), ('highlights', ['Killed people'])]:
            with self.subTest(field=field):
                self.assertIsNotNone(entity_problem('experience', field, value))
        for field, value in [('role', 'Homicide Investigator'), ('role', 'Actor'),
                             ('responsibilities', ['Investigated murder cases.']),
                             ('highlights', ['Killed stalled processes to restore the service.']),
                             ('responsibilities', ['Portrayed a murderer in a fictional stage performance.'])]:
            with self.subTest(value=value):
                self.assertIsNone(entity_problem('experience', field, value))

    def test_self_claims_and_noise_are_not_responsibilities_but_real_context_is_allowed(self):
        for value in ('i am a serial killer', "I'm a murderer", 'My role is a robber',
                      'ters354d4523', 'ters354d', 'I am killing people'):
            for field in ('responsibilities', 'highlights'):
                with self.subTest(value=value, field=field):
                    self.assertIsNotNone(entity_problem('experience', field, [value]))
        for value in ('Investigated serial killer cases.', 'Portrayed a serial killer in a stage production.',
                      'Implemented RFC4122 UUID generation.', 'Killed stalled processes.',
                      'Quarterly reconciliation'):
            self.assertIsNone(entity_problem('experience', 'responsibilities', [value]), value)


class ChatEntityValidationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('entity-validation@example.test')

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.document = deepcopy(SAMPLE_CV)
        self.document['meta']['career_level'] = 'experienced'
        self.cv = create_cv(user=self.user, values={'name': 'Entity validation CV', 'data': self.document})
        mocked = patch('chatbot.services.conversation_service.QwenClient.generate',
                       side_effect=AssertionError('Clear entity checks must stay local'))
        self.qwen = mocked.start(); self.addCleanup(mocked.stop)

    def start(self, *, initial=False, section='experience'):
        if initial:
            session = create_chat_session(user=self.user, initial_values={
                'target_role': 'Backend Developer', 'career_level': 'fresher'})
            state = session.conversation_state
            state['pending_field'] = {'section': section, 'field': 'company' if section == 'experience' else section}
            session.save(update_fields=['conversation_state'])
        else:
            session = create_chat_session(user=self.user, cv_id=self.cv.pk)
            self.send(session, 'add a job' if section == 'experience' else 'add a certification')
        return session

    def send(self, session, text):
        response = self.client.post(f'/api/chat/sessions/{session.pk}/messages/', {'message': text}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {'assistant_message', 'intent', 'section', 'cv_updates', 'next_action'})
        session.refresh_from_db()
        return response.data

    def collected(self, session):
        state = session.conversation_state
        return state.get('edit_updates') if state.get('mode') == 'edit_existing' else state['collected_data']

    def assert_saved_unchanged(self):
        self.cv.refresh_from_db()
        self.assertEqual((self.cv.data, self.cv.version), (self.document, 1))

    def model_reply(self, *, intent='answer', entries=None, reason=None,
                    requires_clarification=False, uncertain_fields=None, skip_fields=None):
        return adapt_extraction({
            'intent': intent, 'section': 'experience',
            'extracted_fields': {'experience': entries} if entries else {},
            'field_corrections': {}, 'skip_fields': skip_fields or [], 'uncertain_fields': uncertain_fields or [],
            'cv_related_question': None, 'requires_clarification': requires_clarification,
            'rejection_reason': reason})

    def test_full_fresher_flow_does_not_skip_invalid_project_or_experience_answers(self):
        session = create_chat_session(user=self.user, initial_values={
            'target_role': 'Frontend Developer', 'career_level': 'fresher', 'template_id': 'modern'})
        for text in ('John', 'john@example.test', '03036096093', 'Las Vegas', 'skip', 'skip', 'no',
                     'I completed BS Software Engineering from Oxford University in 2026-06',
                     'HTML, CSS, JavaScript, TypeScript, React, Git, Unit testing, REST APIs',
                     'Ai base interview plateform', 'Helps candidates practise interviews and receive feedback.'):
            self.send(session, text)
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        before = deepcopy(self.collected(session))
        self.send(session, 'ters354d')
        self.assertEqual(next_step(session.conversation_state)['field'], 'technologies')
        self.assertEqual(self.collected(session), before)
        self.qwen.assert_not_called()
        self.send(session, 'React, Django')
        self.send(session, 'continue')
        self.assertEqual(next_step(session.conversation_state)['section'], 'experience')
        reply = self.send(session, 'yes completed intenrship')
        self.assertIn('Which company', reply['assistant_message'])
        self.assertNotIn('unqualified', reply['assistant_message'])
        self.qwen.assert_not_called()
        self.send(session, 'Python Developer intern at bitech')
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
        before = deepcopy(self.collected(session))
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(intent='skip', skip_fields=['experience'])
        for text in ('ters354d4523', 'i am a serial killer'):
            reply = self.send(session, text)
            self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
            self.assertNotIn('experience', session.conversation_state.get('skipped_sections', []))
            self.assertEqual(self.collected(session), before)
            self.assertFalse(any(reply['cv_updates'].values()))
        self.assertEqual(self.qwen.call_count, 2)
        self.send(session, 'Built and tested Django API endpoints.')
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.assertEqual(self.collected(session)['experience'][0]['responsibilities'],
                         ['Built and tested Django API endpoints.'])
        self.assert_saved_unchanged()

    def test_internship_acknowledgments_ask_for_actual_employer_without_model_guesses(self):
        for answer in ('yes completed intenrship', 'I completed an internship',
                       'yes, I have finished my internship'):
            with self.subTest(answer=answer):
                session = self.start(initial=True)
                reply = self.send(session, answer)
                self.assertIn('Which company', reply['assistant_message'])
                self.assertEqual(next_step(session.conversation_state)['field'], 'company')
                self.assertFalse(self.collected(session).get('experience'))
                self.assertFalse(any(reply['cv_updates'].values()))
        self.qwen.assert_not_called()

    def test_bad_work_source_cannot_be_rephrased_into_invented_benign_duties(self):
        for text in ('i am a serial killer', "I'm a murderer", 'ters354d4523'):
            with self.subTest(text=text):
                session = self.start()
                self.send(session, 'Bitech Systems')
                self.send(session, 'Python Developer Intern')
                before = deepcopy(session.conversation_state)
                self.qwen.side_effect = None
                proposal = self.model_reply(entries=[{'responsibilities': ['Resolved production defects.']}])
                proposal['state_updates'] = {'target_role': 'Executive', 'career_level': 'experienced'}
                proposal['_control']['question_profile'] = 'executive'
                self.qwen.return_value = proposal
                reply = self.send(session, text)
                self.assertFalse(any(reply['cv_updates'].values()))
                self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
                self.assertEqual(self.collected(session), before['edit_updates'])
                self.assertEqual(session.conversation_state.get('question_profile'), before.get('question_profile'))
                self.assertEqual(session.conversation_state['target_role'], before['target_role'])
        self.assert_saved_unchanged()

    def test_model_cannot_skip_or_undo_a_work_step_without_a_user_command(self):
        for intent in ('skip', 'go_back', 'finish'):
            with self.subTest(intent=intent):
                session = self.start()
                self.send(session, 'Bitech Systems')
                self.send(session, 'Accountant')
                before = deepcopy(self.collected(session))
                self.qwen.side_effect = None
                self.qwen.return_value = self.model_reply(intent=intent, skip_fields=['experience'])
                reply = self.send(session, 'Quarterly reconciliation')
                self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
                self.assertEqual(self.collected(session), before)
                self.assertNotIn('experience', session.conversation_state.get('skipped_sections', []))
                self.assertNotEqual(reply['next_action'], 'complete')
                self.assertEqual(session.status, 'active')

    def test_investigative_and_fictional_duties_are_not_rejected_by_source_check(self):
        for text in ('Investigated serial killer cases and prepared court files.',
                     'Portrayed a serial killer in a stage production.'):
            with self.subTest(text=text):
                session = self.start()
                self.send(session, 'Example Productions')
                self.qwen.side_effect = None
                self.qwen.return_value = self.model_reply(entries=[{'role': 'Actor'}])
                self.send(session, 'Actor')
                self.qwen.return_value = self.model_reply(entries=[{'responsibilities': [text]}])
                self.send(session, text)
                self.assertEqual(self.collected(session)['experience'][0]['responsibilities'], [text])
        self.assert_saved_unchanged()

    def test_genuine_model_rejection_keeps_its_explanation_at_responsibilities(self):
        session = self.start()
        self.send(session, 'Bitech Systems')
        self.send(session, 'Python Developer Intern')
        reason = 'That is not a professional responsibility you can put on a CV.'
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(intent='inappropriate', reason=reason)
        reply = self.send(session, 'i am a serial killer')
        self.assertIn(reason, reply['assistant_message'])
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
        self.assertEqual(reply['assistant_message'].count('?'), 1)
        self.assert_saved_unchanged()

    def test_unclear_role_uses_qwen_explanation_then_one_clear_question(self):
        session = self.start()
        self.send(session, 'bitech pvt limited')
        before = deepcopy(self.collected(session))
        reason = 'I could not tell whether that is a typo or the name of your position.'
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(
            intent='clarification', reason=reason, requires_clarification=True,
            uncertain_fields=['experience.role'])
        reply = self.send(session, 'Rubery')
        self.assertIn(reason, reply['assistant_message'])
        self.assertIn('no job title was added', reply['assistant_message'].casefold())
        self.assertIn('For example, Developer, Designer or Intern.', reply['assistant_message'])
        self.assertNotIn('experience.role', reply['assistant_message'])
        self.assertNotIn('kept only the work details', reply['assistant_message'])
        self.assertEqual(reply['assistant_message'].count('?'), 1)
        self.assertEqual(self.collected(session), before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.qwen.assert_called_once()
        self.send(session, 'Backend Developer')
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
        self.assertEqual(self.collected(session)['experience'][0]['role'], 'Backend Developer')
        self.assert_saved_unchanged()

    def test_role_rejection_explains_the_message_and_keeps_the_employer(self):
        session = self.start()
        self.send(session, 'bitech pvt limited')
        before = deepcopy(self.collected(session))
        reason = 'That describes a harmful act rather than a professional job title.'
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(intent='inappropriate', reason=reason)
        reply = self.send(session, 'murder')
        self.assertIn(reason, reply['assistant_message'])
        self.assertIn('not added to your CV', reply['assistant_message'])
        self.assertIn('For example, Developer, Designer or Intern.', reply['assistant_message'])
        self.assertEqual(reply['assistant_message'].count('?'), 1)
        self.assertEqual(self.collected(session), before)
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.qwen.assert_called_once()
        self.assert_saved_unchanged()

    def test_role_evidence_warning_says_nothing_was_added_and_gives_examples(self):
        for answer in ('Rubery', 'murder'):
            with self.subTest(answer=answer):
                session = self.start()
                self.send(session, 'bitech pvt limited')
                before = deepcopy(self.collected(session))
                self.qwen.side_effect = None
                self.qwen.return_value = self.model_reply(entries=[{'role': 'Backend Developer'}])
                reply = self.send(session, answer)
                self.assertIn('couldn’t confirm a job title', reply['assistant_message'])
                self.assertIn('no job title was added', reply['assistant_message'].casefold())
                self.assertIn('For example, Developer, Designer or Intern.', reply['assistant_message'])
                self.assertNotIn('kept only the work details', reply['assistant_message'])
                self.assertNotIn('experience.role', reply['assistant_message'])
                self.assertEqual(self.collected(session), before)
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assert_saved_unchanged()

    def test_missing_or_unusable_clarification_reason_has_a_specific_role_fallback(self):
        cases = [(reason, True) for reason in (
            None, '', '<script>bad()</script>', 'Should I delete the CV?',
            'You are an idiot', ['not text'], 'x' * 321)] + [(None, False)]
        for reason, requires_clarification in cases:
            with self.subTest(reason=reason, requires_clarification=requires_clarification):
                session = self.start()
                self.send(session, 'bitech pvt limited')
                before = deepcopy(self.collected(session))
                self.qwen.side_effect = None
                self.qwen.return_value = self.model_reply(
                    intent='clarification', reason=reason, requires_clarification=requires_clarification,
                    uncertain_fields=['experience.role'])
                reply = self.send(session, 'Rubery')
                self.assertIn('couldn’t identify your job title', reply['assistant_message'])
                self.assertIn('no job title was added', reply['assistant_message'].casefold())
                self.assertNotIn('experience.role', reply['assistant_message'])
                self.assertNotIn('<script>', reply['assistant_message'])
                self.assertEqual(reply['assistant_message'].count('?'), 1)
                self.assertEqual(self.collected(session), before)
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')

    def test_partial_valid_work_answer_keeps_the_company_and_uses_qwen_feedback(self):
        session = self.start()
        reason = 'The company is clear, but the job title needs clarification.'
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(
            entries=[{'company': 'cobalt orchard', 'role': 'Invented Director'}],
            requires_clarification=True, reason=reason)
        reply = self.send(session, 'I worked at cobalt orchard but forgot the exact title')
        self.assertIn(reason, reply['assistant_message'])
        self.assertNotIn('kept only the work details', reply['assistant_message'])
        self.assertNotIn('experience.role', reply['assistant_message'])
        self.assertEqual(self.collected(session)['experience'], [{'company': 'cobalt orchard'}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(reply['assistant_message'].count(reason), 1)
        self.assert_saved_unchanged()

    def test_non_role_clarification_also_keeps_qwen_feedback(self):
        session = self.start(section='certifications')
        reason = 'I need the course title to identify which certification you mean.'
        self.qwen.side_effect = None
        response = self.model_reply(intent='clarification', requires_clarification=True, reason=reason)
        response['section'] = 'certifications'
        self.qwen.return_value = response
        reply = self.send(session, 'I completed a course but forgot its title')
        self.assertIn(reason, reply['assistant_message'])
        self.assertEqual(reply['assistant_message'].count('?'), 1)
        self.assertFalse(self.collected(session).get('certifications'))
        self.qwen.assert_called_once()
        self.assert_saved_unchanged()

    def test_selected_job_clarification_cannot_become_a_patch_or_lose_its_explanation(self):
        self.document['experience'] = [{
            'company': 'Example Systems', 'job_title': 'Developer Intern',
            'highlights': ['Built confirmed features.'], 'start_date': '2025-01',
            'end_date': '', 'is_current': True, 'location': ''}]
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=['data'])
        session = create_chat_session(user=self.user, cv_id=self.cv.pk)
        self.send(session, 'change my job title')
        before = deepcopy(self.collected(session))
        reason = 'I cannot identify the job title you want to use from that answer.'
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(
            intent='clarification', reason=reason, requires_clarification=True,
            entries=[{'company': 'Example Systems'}])
        reply = self.send(session, 'Rubery')
        self.assertIn(reason, reply['assistant_message'])
        self.assertEqual(next_step(session.conversation_state),
                         {'section': 'experience', 'field': 'role', 'index': 0})
        self.assertEqual(self.collected(session), before)
        self.assertFalse(session.conversation_state.get('entry_patches'))
        self.assertFalse(any(reply['cv_updates'].values()))
        self.assert_saved_unchanged()

    def test_reported_typo_and_lowercase_employer_ask_for_role_without_qwen(self):
        session = create_chat_session(user=self.user, cv_id=self.cv.pk)
        self.send(session, 'i want to add experiece')
        self.assertTrue(session.conversation_state['edit_explicit_add'])
        reply = self.send(session, 'bitech pvt limited')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'bitech pvt limited'}])
        self.assertIn('role or job title', reply['assistant_message'])
        self.assertNotIn('experience.role', reply['assistant_message'])
        self.assertEqual(session.conversation_state['edit_operation'], 'add')
        self.qwen.assert_not_called()
        self.assert_saved_unchanged()

    def test_new_job_at_saved_employer_keeps_separate_role_and_preserves_saved_job(self):
        saved_job = {'company': 'bitech pvt limited', 'job_title': 'Python Intern',
                     'highlights': ['Tested confirmed API behavior.'], 'start_date': '2025-01',
                     'end_date': '', 'is_current': True, 'location': ''}
        self.document['experience'] = [saved_job]
        self.cv.data = deepcopy(self.document)
        self.cv.save(update_fields=['data'])
        session = create_chat_session(user=self.user, cv_id=self.cv.pk)
        self.send(session, 'i want to add experiece')
        self.send(session, 'bitech pvt limited')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'bitech pvt limited'}])
        self.send(session, 'Backend Developer')
        self.send(session, 'Built and tested backend APIs.')
        self.send(session, 'finish')
        self.assert_saved_unchanged()
        saved = self.client.post('/api/cvs/from-chat/', {
            'session_id': str(session.pk), 'expected_version': 1}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        jobs = saved.data['cv']['data']['experience']
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0], saved_job)
        self.assertEqual(jobs[1]['job_title'], 'Backend Developer')
        self.qwen.assert_not_called()

    def test_company_only_model_answer_drops_guessed_role_and_asks_actual_role(self):
        session = self.start()
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(entries=[{
            'company': 'cobalt orchard', 'role': 'Backend Developer'}])
        reply = self.send(session, 'cobalt orchard')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'cobalt orchard'}])
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertIn('role or job title', reply['assistant_message'])
        self.assertNotIn('experience.role', reply['assistant_message'])
        self.assertNotIn('What would you like to change', reply['assistant_message'])
        self.qwen.assert_called_once()
        self.assert_saved_unchanged()

    def test_reported_invalid_role_and_followup_reach_qwen_without_advancing(self):
        session = self.start()
        self.send(session, 'cancel')
        self.send(session, 'want to add expeerience')
        self.send(session, 'Bitech PVT limited')
        before = deepcopy(self.collected(session))
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(
            intent='inappropriate', reason='That describes harm to people rather than a professional role or duty.')
        for text in ('My role is a murderer', 'Murder of persons'):
            reply = self.send(session, text)
            self.assertEqual(reply['intent'], 'irrelevant')
            self.assertIn('rather than a professional role or duty', reply['assistant_message'])
            self.assertEqual(next_step(session.conversation_state)['field'], 'role')
            self.assertEqual(self.collected(session), before)
        self.assertEqual(self.qwen.call_count, 2)
        for call in self.qwen.call_args_list:
            self.assertIn('"field": "role"', call.args[0][1]['content'])
        self.assert_saved_unchanged()

    def test_model_cannot_approve_an_obviously_invalid_job_label(self):
        session = self.start()
        self.send(session, 'Bitech PVT limited')
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(entries=[{'role': 'murderer'}])
        reply = self.send(session, 'My role is a murderer')
        self.qwen.assert_called_once()
        self.assertEqual(reply['intent'], 'clarify_information')
        self.assertIn('not a professional job title', reply['assistant_message'])
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'Bitech PVT limited'}])
        self.assert_saved_unchanged()

    def test_unclear_duties_reach_qwen_and_invalid_proposals_stay_out(self):
        session = self.start()
        self.send(session, 'Bitech PVT limited')
        self.send(session, 'Backend Developer')
        before = deepcopy(self.collected(session))
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(entries=[{'responsibilities': ['Murder of persons']}])
        reply = self.send(session, 'Murder of persons')
        self.qwen.assert_called_once()
        self.assertEqual(reply['intent'], 'clarify_information')
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')
        self.assertEqual(self.collected(session), before)
        self.assert_saved_unchanged()

    def test_crime_related_professional_context_uses_qwen_and_is_retained(self):
        session = self.start()
        self.send(session, 'Example Investigations Office')
        duty = 'Investigated murder cases and prepared court files.'
        self.qwen.side_effect = [
            self.model_reply(entries=[{'role': 'Homicide Investigator'}]),
            self.model_reply(entries=[{'responsibilities': [duty]}])]
        self.send(session, 'My role is a Homicide Investigator')
        self.send(session, duty)
        self.assertEqual(self.qwen.call_count, 2)
        self.assertEqual(self.collected(session)['experience'], [{
            'company': 'Example Investigations Office', 'role': 'Homicide Investigator',
            'responsibilities': [duty]}])
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assert_saved_unchanged()

    def test_unknown_but_plausible_label_is_reviewed_without_a_title_catalogue(self):
        session = self.start()
        self.send(session, 'Example Institute')
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(entries=[{'role': 'Clinical Ethics Steward'}])
        self.send(session, 'My role is a Clinical Ethics Steward')
        self.qwen.assert_called_once()
        self.assertEqual(self.collected(session)['experience'][0]['role'], 'Clinical Ethics Steward')
        self.assertEqual(next_step(session.conversation_state)['field'], 'responsibilities')

    def test_noun_phrase_duties_need_interpretation_instead_of_scalar_storage(self):
        session = self.start()
        self.send(session, 'Example Institute')
        self.send(session, 'Accountant')
        self.qwen.side_effect = None
        self.qwen.return_value = self.model_reply(entries=[{'responsibilities': ['Quarterly reconciliation']}])
        self.send(session, 'Quarterly reconciliation')
        self.qwen.assert_called_once()
        self.assertEqual(self.collected(session)['experience'][0]['responsibilities'], ['Quarterly reconciliation'])

    def test_nothing_at_final_edit_prompt_finishes_locally_without_saving(self):
        session = self.start()
        self.send(session, 'cancel')
        before = deepcopy(self.collected(session))
        reply = self.send(session, 'nothing')
        self.assertEqual(reply['next_action'], 'complete')
        self.assertEqual(session.status, 'completed')
        self.assertEqual(self.collected(session), before)
        self.qwen.assert_not_called()
        self.assert_saved_unchanged()

    def test_nothing_is_not_a_global_skip_for_an_incomplete_experience(self):
        session = self.start()
        self.send(session, 'Bitech PVT limited')
        self.qwen.side_effect = None
        self.qwen.return_value = empty_ai_response()
        reply = self.send(session, 'nothing')
        self.assertNotEqual(reply['next_action'], 'complete')
        self.assertEqual(session.status, 'active')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'Bitech PVT limited'}])

    def test_reported_transcript_never_adds_noise_or_activity_as_employment(self):
        session = self.start(section='certifications')
        for text in ['o shutup', 'ter45fase4', 'yes, add it']:
            self.send(session, text)
            self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'cancel')
        self.assertEqual(self.send(session, 'are  you fool')['intent'], 'irrelevant')
        self.assertEqual(self.send(session, 'i want to add xperience')['section'], 'experience')
        self.assertEqual(self.send(session, 'are  you fool')['intent'], 'irrelevant')
        result = self.send(session, 'lamb cooking')
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.assertIn('activity', result['assistant_message'])
        self.assertFalse(self.collected(session).get('experience'))
        self.send(session, 'Bitech Systems')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.assertEqual(self.collected(session)['experience'], [{'company': 'Bitech Systems'}])
        self.qwen.assert_not_called(); self.assert_saved_unchanged()

    def test_wrong_company_entity_stays_at_company_in_both_modes(self):
        for initial in [False, True]:
            for answer in ['lamb cooking', 'playing cricket', 'Python', 'English', '2026-06', 'https://example.com']:
                with self.subTest(initial=initial, answer=answer):
                    session = self.start(initial=initial)
                    self.send(session, answer)
                    self.assertEqual(next_step(session.conversation_state)['field'], 'company')
                    self.assertFalse(self.collected(session).get('experience'))
        self.assert_saved_unchanged()

    def test_company_labels_disambiguate_unusual_names_and_are_not_saved_as_prefixes(self):
        for message, name in [('Company: Lamb Cooking', 'Lamb Cooking'),
                              ('Company: Python', 'Python'), ('n8n', 'n8n'),
                              ('A Cup of Tea', 'A Cup of Tea'), ('東京食堂', '東京食堂')]:
            with self.subTest(message=message):
                session = self.start()
                self.send(session, message)
                self.assertEqual(self.collected(session)['experience'], [{'company': name}])
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')

    def test_culinary_experience_is_valid_for_a_different_target_role(self):
        session = self.start()
        self.send(session, 'Example Restaurant')
        self.send(session, 'lamb cooking')
        self.assertEqual(next_step(session.conversation_state)['field'], 'role')
        self.send(session, 'Job title: Chef')
        self.send(session, 'Prepared meals.')
        self.assertEqual(self.collected(session)['experience'][0]['role'], 'Chef')
        self.assertEqual(next_step(session.conversation_state)['section'], 'review')
        self.assert_saved_unchanged()

    def test_random_certificate_is_not_confirmable_in_both_modes(self):
        for initial in [False, True]:
            for title in ['ter45fase4', 't33ssr', 'asdfghjkl', 'ter45fase4 Certificate']:
                with self.subTest(initial=initial, title=title):
                    session = self.start(initial=initial, section='certifications')
                    self.send(session, title)
                    self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
                    self.send(session, 'yes')
                    self.assertFalse(self.collected(session).get('certifications'))
                    self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')

    def test_structured_certificate_metadata_cannot_make_a_random_title_valid(self):
        session = self.start(section='certifications')
        self.send(session, '{"certifications": [{"name": "ter45fase4", "issuer": "Example Training", "date": "2026-06"}]}')
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_reported_certificate_sequence_keeps_the_real_course_and_rejects_person_labels(self):
        session = self.start(initial=True, section='certifications')
        reply = self.send(session, 'Advance Ai bootcamp certificate issud by GIKI')
        expected = [{'name': 'Advance Ai bootcamp certificate', 'issuer': 'GIKI'}]
        self.assertEqual(self.collected(session)['certifications'], expected)
        self.assertIn('1 certification', reply['assistant_message'])
        self.send(session, 'i want to add cetificate')
        for text in ('Murderer in pakistan', 'Murderer in pakistan issued by PITB'):
            reply = self.send(session, text)
            self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
            self.assertEqual(self.collected(session)['certifications'], expected)
            self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
            self.assertIn('not added', reply['assistant_message'])
            self.assertNotIn('full certification title for “Murderer', reply['assistant_message'])
        self.send(session, 'Application Security issued by Regional Academy')
        self.assertEqual(self.collected(session)['certifications'][-1], {
            'name': 'Application Security', 'issuer': 'Regional Academy'})
        self.qwen.assert_not_called()
        self.assert_saved_unchanged()

    def test_person_descriptor_certificate_rejected_with_any_metadata_in_both_modes(self):
        for initial in (False, True):
            for text in (
                'Murderer in pakistan', 'Murderer in pakistan issued by PITB',
                '"Murderer in pakistan" issued by PITB',
                'Certification: Murderer in Pakistan — PITB',
                'Murderer in Pakistan issued by Forensic Training Institute issue date 2026-06',
                '{"certifications":[{"name":"Murderer in Pakistan","issuer":"PITB",'
                '"date":"2026-06","url":"https://example.test/credential"}]}',
            ):
                with self.subTest(initial=initial, text=text):
                    session = self.start(initial=initial, section='certifications')
                    reply = self.send(session, text)
                    self.assertFalse(self.collected(session).get('certifications'))
                    self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
                    self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
                    self.assertIn('not added', reply['assistant_message'])
        self.qwen.assert_not_called()
        self.assert_saved_unchanged()

    def test_valid_crime_related_and_unfamiliar_certifications_are_not_word_banned(self):
        for name in ('Murder Investigation Certificate', 'Serial Killer Profiling Certificate',
                     'Murderer in Fiction Certificate', 'Distributed Systems', '地域防犯講習'):
            with self.subTest(name=name):
                session = self.start(section='certifications')
                self.send(session, name + ' issued by Example Academy')
                self.assertEqual(self.collected(session)['certifications'], [{'name': name, 'issuer': 'Example Academy'}])
        self.qwen.assert_not_called()
        self.assert_saved_unchanged()

    def test_bad_certificate_sibling_is_dropped_with_its_metadata(self):
        session = self.start(section='certifications')
        self.send(session, '{"certifications":['
                  '{"name":"AI Bootcamp Certificate","issuer":"GIKI"},'
                  '{"name":"Murderer in Pakistan","issuer":"PITB","date":"2026-06"}]}')
        self.assertEqual(self.collected(session)['certifications'], [{'name': 'AI Bootcamp Certificate', 'issuer': 'GIKI'}])
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_invalid_legacy_certificate_candidate_does_not_keep_requesting_an_issuer(self):
        session = self.start(section='certifications')
        session.conversation_state['optional_entry_confirmation'] = {
            'section': 'certifications', 'entries': [{'name': 'Murderer in Pakistan'}]}
        session.save(update_fields=['conversation_state'])
        reply = self.send(session, 'Murderer in Pakistan issued by PITB')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertIn('not added', reply['assistant_message'])
        self.assertNotIn('full certification title for', reply['assistant_message'])
        self.send(session, 'Application Security issued by Regional Academy')
        self.assertEqual(self.collected(session)['certifications'], [
            {'name': 'Application Security', 'issuer': 'Regional Academy'}])

    def test_qwen_cannot_rewrite_a_non_credential_into_a_plausible_certificate(self):
        session = self.start(section='certifications')
        self.qwen.side_effect = None
        proposal = empty_ai_response()
        proposal['section'] = 'certifications'
        proposal['cv_updates']['certifications'] = [{'name': 'Crime Investigation Certificate', 'issuer': 'PITB'}]
        self.qwen.return_value = proposal
        reply = self.send(session, 'Could you record a qualification whose title is Murderer in Pakistan and whose issuing body is PITB?')
        self.qwen.assert_called_once()
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.assertFalse(any(reply['cv_updates'].values()))

    def test_polite_request_can_add_a_legitimate_investigation_certificate_via_qwen(self):
        session = self.start(section='certifications')
        self.qwen.side_effect = None
        proposal = empty_ai_response()
        proposal['section'] = 'certifications'
        course = {'name': 'Murder Investigation Certificate', 'issuer': 'Example Academy'}
        proposal['cv_updates']['certifications'] = [course]
        self.qwen.return_value = proposal
        self.send(session, 'Could you record a qualification whose title is Murder Investigation Certificate and whose issuing body is Example Academy?')
        self.qwen.assert_called_once()
        self.assertEqual(self.collected(session)['certifications'], [course])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assert_saved_unchanged()

    def test_clear_certificate_is_kept_when_a_sibling_is_random(self):
        session = self.start(section='certifications')
        self.send(session, 'Python Certificate, ter45fase4')
        self.assertEqual(self.collected(session)['certifications'], [{'name': 'Python Certificate'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
        self.assertEqual(next_step(session.conversation_state)['section'], 'certifications')
        self.send(session, 'cancel')
        self.assertEqual(self.collected(session)['certifications'], [{'name': 'Python Certificate'}])

    def test_ambiguous_certificate_requires_actual_details_rather_than_yes(self):
        session = self.start(section='certifications')
        self.send(session, 'Regional Professional Practice')
        self.assertTrue(session.conversation_state.get('optional_entry_confirmation'))
        self.send(session, 'yes, add it')
        self.assertFalse(self.collected(session).get('certifications'))
        self.send(session, 'Certification: Regional Professional Practice — Example Institute')
        self.assertEqual(self.collected(session)['certifications'], [
            {'name': 'Regional Professional Practice', 'issuer': 'Example Institute'}])
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_legacy_random_optional_confirmation_cannot_be_accepted(self):
        session = self.start(section='certifications')
        session.conversation_state['optional_entry_confirmation'] = {
            'section': 'certifications', 'entries': [{'name': 'ter45fase4'}]}
        session.save(update_fields=['conversation_state'])
        self.send(session, 'yes')
        self.assertFalse(self.collected(session).get('certifications'))
        self.send(session, 'cancel')
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))

    def test_model_extraction_cannot_store_an_activity_as_company(self):
        session = self.start()
        response = empty_ai_response()
        response['section'] = 'experience'
        response['cv_updates']['experience'] = [{'company': 'lamb cooking'}]
        self.qwen.side_effect = None; self.qwen.return_value = response
        self.send(session, 'I was thinking about lamb cooking')
        self.assertFalse(self.collected(session).get('experience'))
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.qwen.assert_called_once()

    def test_credential_codes_and_culinary_certificates_are_accepted(self):
        for title in ['AZ-900', 'CCNA', 'ISO27001', 'Lamb Cooking Certificate']:
            with self.subTest(title=title):
                session = self.start(section='certifications')
                self.send(session, title)
                self.assertEqual(self.collected(session)['certifications'][0]['name'], title)

    def test_a_skill_or_issuer_alone_is_not_a_certification(self):
        for title in ['Python', 'SQL', 'AWS', 'Google', 'Microsoft']:
            with self.subTest(title=title):
                session = self.start(section='certifications')
                self.send(session, title)
                self.send(session, 'yes')
                self.assertFalse(self.collected(session).get('certifications'))
                self.send(session, 'Certification: Google AI Essentials — Google')
                self.assertEqual(self.collected(session)['certifications'][0]['name'], 'Google AI Essentials')

    def test_skill_and_language_replies_do_not_become_job_titles(self):
        for answer in ['Python', 'English', 'Bitech Company']:
            with self.subTest(answer=answer):
                session = self.start()
                self.send(session, 'Example Restaurant')
                self.send(session, answer)
                self.assertEqual(next_step(session.conversation_state)['field'], 'role')
                self.assertEqual(self.collected(session)['experience'], [{'company': 'Example Restaurant'}])

    def test_unknown_lowercase_employer_uses_qwen_instead_of_blind_scalar_assignment(self):
        session = self.start()
        self.qwen.side_effect = None
        self.qwen.return_value = empty_ai_response()
        self.send(session, 'mango salad')
        self.assertFalse(self.collected(session).get('experience'))
        self.assertEqual(next_step(session.conversation_state)['field'], 'company')
        self.qwen.assert_called_once()

    def test_abusive_json_entity_does_not_bypass_conduct_checks(self):
        session = self.start(section='certifications')
        self.send(session, '{"certifications": [{"name": "are you a fool", "issuer": "Example"}]}')
        self.assertFalse(self.collected(session).get('certifications'))
        self.assertFalse(session.conversation_state.get('optional_entry_confirmation'))
