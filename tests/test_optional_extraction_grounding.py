"""Optional editing cannot copy saved facts into an unrelated user answer."""
from copy import deepcopy

from django.test import SimpleTestCase

from chatbot.services.conversation_router import empty_ai_response
from chatbot.services.extraction_guard import guard_extraction
from chatbot.services.existing_cv_conversation import edit_step, update_edit_state
from chatbot.services.field_validation import validated_updates


class OptionalExtractionGroundingTests(SimpleTestCase):
    def setUp(self):
        self.state = {
            'mode': 'edit_existing', 'edit_focus': 'languages', 'edit_operation': 'add',
            'edit_updates': {'personal': {}}, 'current_section': 'languages',
            'existing_cv': {
                'languages': [{'name': 'English', 'proficiency': ''}, {'name': 'Urdu', 'proficiency': ''}],
                'certifications': [{'name': 'CCNA', 'issuer': 'Cisco'}],
                'projects': [{'name': 'Saved Project'}],
                'education': [{'degree': 'BS Computer Science', 'institution': 'Example University'}],
            },
        }

    def guard(self, message, *, state=None, **updates):
        response = empty_ai_response()
        response['cv_updates'].update(updates)
        return guard_extraction(response, message, self.state if state is None else state)

    def clean(self, response, state=None):
        return validated_updates(response, self.state if state is None else state)[0]['cv_updates']

    def test_travel_cannot_authorize_saved_language_names_or_proficiency(self):
        state, original = deepcopy(self.state), deepcopy(self.state)
        result = self.guard('i am going to murree', state=state,
                            languages=[{'name': 'English'}, {'name': 'Urdu'}])
        self.assertIsNone(self.clean(result)['languages'])
        self.assertIn('evidence_warning', result['_control'])
        self.assertEqual(state, original)

    def test_literal_and_context_copied_language_siblings_are_checked_independently(self):
        result = self.guard('English', languages=[{'name': 'English'}, {'name': 'Urdu'}])
        self.assertEqual(self.clean(result)['languages'], [{'name': 'English'}])

    def test_named_proficiency_is_supported_without_copying_another_pending_language(self):
        self.state['language_proficiency_pending'] = ['English', 'Urdu']
        result = self.guard('English professional', languages=[
            {'name': 'English', 'proficiency': 'professional'}, {'name': 'Urdu'}])
        self.assertEqual(self.clean(result)['languages'], [{'name': 'English', 'proficiency': 'professional'}])

    def test_single_pending_language_can_receive_an_explicit_anonymous_proficiency(self):
        self.state['language_proficiency_pending'] = ['Urdu']
        result = self.guard('native', languages=[{'name': 'Urdu', 'proficiency': 'native'}])
        self.assertEqual(self.clean(result)['languages'], [{'name': 'Urdu', 'proficiency': 'native'}])

    def test_anonymous_proficiency_cannot_choose_between_multiple_languages(self):
        self.state['language_proficiency_pending'] = ['English', 'Urdu']
        result = self.guard('native', languages=[{'name': 'Urdu', 'proficiency': 'native'}])
        self.assertNotIn('name', result['cv_updates']['languages'][0])
        self.assertIsNone(self.clean(result)['languages'])

    def test_selected_language_can_receive_proficiency_without_repeating_its_name(self):
        self.state.update(edit_operation='edit', pending_field={'section': 'languages', 'field': 'proficiency', 'index': 1})
        result = self.guard('my proficiency is fluent', languages=[{'name': 'Urdu', 'proficiency': 'fluent'}])
        self.assertEqual(self.clean(result)['languages'], [{'name': 'Urdu', 'proficiency': 'fluent'}])

    def test_word_professional_in_unrelated_prose_is_not_anonymous_proficiency(self):
        self.state['language_proficiency_pending'] = ['Urdu']
        result = self.guard('I am a professional travel guide', languages=[{'name': 'Urdu'}])
        self.assertIsNone(self.clean(result)['languages'])

    def test_uncommon_and_international_literal_language_names_remain_supported(self):
        for name in ('Kʷak̓ʷala', 'ʻŌlelo Hawaiʻi', 'বাংলা', 'Kurdish Kurmanji', 'British Sign Language'):
            with self.subTest(name=name):
                result = self.guard(f'I speak {name}', languages=[{'name': name}])
                self.assertEqual(self.clean(result)['languages'], [{'name': name}])

    def test_certificate_add_cannot_reuse_a_saved_name_from_unrelated_text(self):
        self.state.update(edit_focus='certifications', edit_operation='add', current_section='certifications')
        result = self.guard('I am going to Murree', certifications=[{'name': 'CCNA'}])
        self.assertIsNone(self.clean(result)['certifications'])

    def test_explicit_certificate_codes_and_names_still_ground_in_latest_message(self):
        self.state.update(edit_focus='certifications', edit_operation='add', current_section='certifications')
        for name in ('AZ-900', 'CCNA', 'AWS SAA-C03', '認定情報技術者'):
            with self.subTest(name=name):
                result = self.guard(f'My certification is {name}', certifications=[{'name': name}])
                self.assertEqual(self.clean(result)['certifications'], [{'name': name}])

    def test_selected_certificate_identity_can_identify_a_date_correction(self):
        self.state.update(edit_focus='certifications', edit_operation='edit',
                          pending_field={'section': 'certifications', 'field': 'date', 'index': 0})
        result = self.guard('2026-06', certifications=[{'name': 'CCNA', 'date': '2026-06'}])
        self.assertEqual(self.clean(result)['certifications'], [{'name': 'CCNA', 'date': '2026-06'}])

    def test_active_language_add_cannot_turn_a_literal_name_into_a_certificate_or_skill(self):
        result = self.guard('English', languages=[{'name': 'English'}], certifications=[{'name': 'English'}], skills=['English'])
        clean = self.clean(result)
        self.assertEqual(clean['languages'], [{'name': 'English'}])
        self.assertIsNone(clean['certifications'])
        self.assertIsNone(clean['skills'])

    def test_explicitly_grouped_other_section_facts_are_kept(self):
        result = self.guard('English professional; skills: Python; certification: AZ-900',
                            languages=[{'name': 'English', 'proficiency': 'professional'}],
                            skills=['Python'], certifications=[{'name': 'AZ-900'}])
        clean = self.clean(result)
        self.assertEqual(clean['skills'], ['Python'])
        self.assertEqual(clean['certifications'], [{'name': 'AZ-900'}])

    def test_focused_project_and_education_identity_corrections_still_work(self):
        for section, message, update in (
            ('projects', 'The description is a scheduling tool.', {'name': 'Saved Project', 'description': 'a scheduling tool'}),
            ('education', 'My graduation date is 2026-06.', {'degree': 'BS Computer Science', 'institution': 'Example University', 'end_date': '2026-06'}),
        ):
            with self.subTest(section=section):
                state = deepcopy(self.state)
                state.update(edit_focus=section, edit_operation='edit', current_section=section)
                result = self.guard(message, state=state, **{section: [update]})
                self.assertEqual(result['cv_updates'][section], [update])

    def test_new_job_cannot_copy_saved_or_prior_proposed_role(self):
        for source in ('existing_cv', 'edit_updates'):
            with self.subTest(source=source):
                state = deepcopy(self.state)
                state.update(edit_focus='experience', edit_operation='add', current_section='experience')
                state[source]['experience'] = [{'company': 'Another Employer', 'role': 'Developer',
                                                 'job_title': 'Developer'}]
                result = self.guard('cobalt orchard', state=state, experience=[{
                    'company': 'cobalt orchard', 'role': 'Developer'}])
                self.assertEqual(result['cv_updates']['experience'], [{'company': 'cobalt orchard'}])

    def test_rejecting_one_role_does_not_claim_a_supported_sibling_was_not_added(self):
        state = deepcopy(self.state)
        state.update(edit_focus='experience', edit_operation='add', current_section='experience')
        result = self.guard('Backend Developer at Example Systems; another job at Other Systems.',
                            state=state, experience=[
                                {'company': 'Example Systems', 'role': 'Backend Developer'},
                                {'company': 'Other Systems', 'role': 'Invented Director'}])
        self.assertEqual(result['cv_updates']['experience'], [
            {'company': 'Example Systems', 'role': 'Backend Developer'}, {'company': 'Other Systems'}])
        self.assertNotIn('no job title was added', result['_control']['evidence_warning'])

    def test_new_entry_identity_context_is_scoped_to_its_active_draft(self):
        for section, draft, update, message in (
            ('experience', {'company': 'New Employer', 'role': 'Developer'},
             {'company': 'New Employer', 'role': 'Developer', 'responsibilities': ['Tested APIs.']}, 'Tested APIs.'),
            ('projects', {'name': 'New Project'},
             {'name': 'New Project', 'description': 'Tracks confirmed tasks.'}, 'Tracks confirmed tasks.'),
            ('education', {'degree': 'BSc', 'institution': 'New University'},
             {'degree': 'BSc', 'institution': 'New University', 'end_date': '2028-06'}, 'I expect to graduate in 2028-06'),
        ):
            with self.subTest(section=section):
                state = deepcopy(self.state)
                state.update(edit_focus=section, edit_operation='add', edit_draft=[draft])
                result = self.guard(message, state=state, **{section: [update]})
                self.assertEqual(result['cv_updates'][section], [update])

    def test_new_project_and_degree_cannot_copy_saved_identities(self):
        for section, message, update in (
            ('projects', 'It tracks confirmed tasks.',
             {'name': 'Saved Project', 'description': 'It tracks confirmed tasks.'}),
            ('education', 'I expect to graduate in 2028-06.',
             {'institution': 'Example University', 'degree': 'BS Computer Science', 'end_date': '2028-06'}),
        ):
            with self.subTest(section=section):
                state = deepcopy(self.state)
                state.update(edit_focus=section, edit_operation='add', edit_draft=[])
                result = self.guard(message, state=state, **{section: [update]})
                for identity in ('name', 'institution', 'degree'):
                    self.assertNotIn(identity, result['cv_updates'][section][0])

    def test_partial_saved_identity_does_not_switch_an_inferred_add_to_edit(self):
        for section, saved, answer, missing in (
            ('experience', {'company': 'Example Systems', 'job_title': 'Developer'},
             {'company': 'Example Systems'}, 'role'),
            ('education', {'institution': 'Example University', 'degree': 'BSc'},
             {'institution': 'Example University'}, 'degree'),
        ):
            with self.subTest(section=section):
                state = deepcopy(self.state)
                state.update(edit_focus=section, edit_operation='add', edit_draft=[])
                state['existing_cv'][section] = [saved]
                response = empty_ai_response()
                response['section'] = section
                response['cv_updates'][section] = [answer]
                updated = update_edit_state(state, response)
                self.assertEqual(updated['edit_operation'], 'add')
                self.assertEqual(edit_step(updated)['field'], missing)
