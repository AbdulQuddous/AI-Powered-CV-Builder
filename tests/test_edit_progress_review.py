"""Progress in saved-CV chats reports proposals without reprinting advice or CV facts."""
from copy import deepcopy

from django.test import SimpleTestCase

from chatbot.services.progress_review import progress_message


class EditProgressReviewTests(SimpleTestCase):
    def setUp(self):
        self.state = {
            'mode': 'edit_existing', 'edit_focus': None, 'edit_updates': {'personal': {}},
            'existing_cv': {
                'meta': {'target_role': 'Backend Developer', 'career_level': 'experienced'},
                'personal': {'full_name': 'Saved Person', 'email': 'saved@example.test'},
                'summary': 'Saved summary that should not be reprinted.',
                'skills': ['Python', 'Git', 'Django'],
                'experience': [{'company': 'Example Systems', 'job_title': 'Developer Intern',
                                'highlights': ['Saved original work contribution.']}],
                'projects': [{'name': 'Original Project', 'description': 'Saved project description.'}],
                'education': [{'institution': 'Example University', 'degree': 'BS Computer Science'}],
                'certifications': [{'name': 'Saved Certification', 'issuer': 'Example Institute'}],
            },
        }

    def test_empty_proposals_do_not_print_saved_information_or_whole_cv_guidance(self):
        message = progress_message(self.state)
        self.assertIn('No pending changes', message)
        self.assertIn('not saved', message)
        self.assertIn('saved CV is unchanged', message)
        for text in ('Saved Person', 'saved@example.test', 'Saved summary', '8–15', 'Candidate skills', 'One or two pages', '{', '}'):
            self.assertNotIn(text, message)

    def test_empty_values_are_not_reported_as_pending_changes(self):
        self.state['edit_updates'] = {'personal': {'email': ''}, 'skills': [], 'summary': '', 'education': [{}]}
        self.assertIn('No pending changes', progress_message(self.state))

    def test_certifications_and_languages_are_presented_without_json_or_saved_context(self):
        self.state['edit_updates'].update(certifications=[{'name': 'New Certificate', 'issuer': 'New Issuer'}],
                                          languages=[{'name': 'Urdu', 'proficiency': 'native'}])
        message = progress_message(self.state)
        for value in ('Certifications', 'New Certificate', 'New Issuer', 'Languages', 'Urdu', 'native'):
            self.assertIn(value, message)
        self.assertNotIn('Saved Certification', message)
        self.assertNotIn('8–15', message)
        self.assertNotIn('{', message)

    def test_contact_and_summary_changes_show_only_new_proposed_values(self):
        self.state['edit_updates'] = {'personal': {'full_name': 'Saved Person', 'email': 'changed@example.test'},
                                     'summary': 'Proposed factual summary.'}
        message = progress_message(self.state)
        self.assertIn('changed@example.test', message)
        self.assertIn('Proposed factual summary.', message)
        for unchanged in ('Saved Person', 'saved@example.test', 'Saved summary'):
            self.assertNotIn(unchanged, message)

    def test_complete_new_projects_are_distinct_from_current_unfinished_project(self):
        self.state.update(edit_new_projects=[{'name': 'Complete Addition', 'description': 'Complete confirmed description.',
                                             'technologies': ['Django']}], edit_focus='projects', edit_operation='add',
                          edit_draft=[{'name': 'Unfinished Addition'}])
        message = progress_message(self.state)
        self.assertIn('New project: Name: Complete Addition', message)
        self.assertIn('Unfinished additions (not ready to save):', message)
        self.assertIn('Unfinished Addition', message)
        self.assertIn('Still needed: description, technologies', message)
        self.assertLess(message.index('Complete Addition'), message.index('Unfinished additions'))
        self.assertEqual(message.count('Complete Addition'), 1)

    def test_completed_draft_left_in_state_is_not_repeated_as_unfinished(self):
        project = {'name': 'Completed Project', 'description': 'Delivered an application.', 'technologies': ['Django']}
        self.state.update(edit_new_projects=[project], edit_draft=[deepcopy(project)], edit_focus=None)
        message = progress_message(self.state)
        self.assertEqual(message.count('Completed Project'), 1)
        self.assertNotIn('Unfinished additions', message)

    def test_incomplete_named_education_draft_is_separated_from_ready_changes(self):
        entry = {'degree': 'BS Software Engineering', 'institution': 'New University'}
        self.state.update(edit_focus='education', edit_operation='add', edit_draft=[entry])
        self.state['edit_updates']['education'] = [deepcopy(entry)]
        message = progress_message(self.state)
        self.assertEqual(message.count('BS Software Engineering'), 1)
        self.assertGreater(message.index('BS Software Engineering'), message.index('Unfinished additions'))
        self.assertIn('Still needed: field of study, completion date', message)

    def test_sparse_existing_entry_corrections_do_not_require_a_whole_new_entry(self):
        self.state.update(edit_focus='projects', edit_operation='edit',
                          edit_draft=[{'name': 'Original Project', 'description': 'Revised contribution.'}])
        self.state['edit_updates']['projects'] = deepcopy(self.state['edit_draft'])
        message = progress_message(self.state)
        self.assertIn('Original Project', message)
        self.assertIn('Description: Revised contribution.', message)
        self.assertNotIn('Unfinished additions', message)
        self.assertNotIn('Saved project description.', message)

    def test_entry_patches_use_saved_entry_names_and_include_only_changed_fields(self):
        self.state['entry_patches'] = [
            {'section': 'projects', 'index': 0, 'updates': {'description': 'Corrected project contribution.'}},
            {'section': 'experience', 'index': 0, 'updates': {'role': 'Backend Developer'}},
            {'section': 'education', 'index': 0, 'updates': {'institution': 'Corrected University'}},
        ]
        message = progress_message(self.state)
        for value in ('Original Project', 'Corrected project contribution.', 'Example Systems', 'Developer Intern',
                      'Job title: Backend Developer', 'Example University', 'Corrected University'):
            self.assertIn(value, message)
        self.assertNotIn('Saved original work contribution.', message)
        self.assertNotIn('Saved project description.', message)

    def test_stale_patch_cannot_be_labelled_as_an_unrelated_existing_entry(self):
        self.state['entry_patches'] = [{'section': 'projects', 'index': 7, 'updates': {'description': 'Proposed description.'}}]
        message = progress_message(self.state)
        self.assertIn('Entry needs confirmation', message)
        self.assertIn('Proposed description.', message)
        self.assertNotIn('Original Project', message)
        self.assertNotIn('New project:', message)

    def test_metadata_and_removals_are_explicit_proposals_and_do_not_copy_all_skills(self):
        self.state.update(edit_metadata_updates={'target_role': 'AI Developer', 'career_level': 'experienced'},
                          removed_skills=['Git'])
        message = progress_message(self.state)
        self.assertIn('Target role: AI Developer', message)
        self.assertIn('Requested skill removals: Git', message)
        self.assertNotIn('Career level:', message)
        self.assertNotIn('Python', message)
        self.assertNotIn('Django', message)

    def test_existing_or_removed_skills_are_not_described_as_new_additions(self):
        self.state['edit_updates']['skills'] = ['Python', 'Git', 'Docker', 'Redis']
        self.state['removed_skills'] = ['Redis']
        message = progress_message(self.state)
        self.assertIn('- Skills: Docker', message)
        self.assertNotIn('Skills: Python', message)
        self.assertNotIn('Git', message)
        self.assertNotIn('Docker · Redis', message)
        self.assertIn('Requested skill removals: Redis', message)

    def test_old_collection_context_does_not_replace_current_edit_proposals(self):
        self.state['collected_data'] = {'personal': {'full_name': 'Old Interview Person'}, 'certifications': [{'name': 'Old Certificate'}]}
        self.state['edit_updates']['certifications'] = [{'name': 'Current Proposed Certificate'}]
        message = progress_message(self.state)
        self.assertIn('Current Proposed Certificate', message)
        self.assertNotIn('Old Interview Person', message)
        self.assertNotIn('Old Certificate', message)

    def test_optional_candidate_is_visible_but_separate_from_confirmed_proposals(self):
        self.state['optional_entry_confirmation'] = {'section': 'certifications', 'entries': [{'name': 'Testy McTesterson'}]}
        original = deepcopy(self.state)
        message = progress_message(self.state)
        self.assertIn('Awaiting confirmation (not added):\n- Certifications: Testy McTesterson', message)
        self.assertIn('No pending changes have been collected.', message)
        self.assertIn('saved CV is unchanged', message)
        self.assertNotIn('ready to save', message)
        self.assertEqual(self.state, original)

    def test_optional_confirmation_is_not_hidden_by_a_large_accepted_change_list(self):
        self.state['optional_entry_confirmation'] = {'section': 'languages', 'entries': [{'name': 'Kashmiri'}]}
        self.state['edit_updates']['projects'] = [{'name': f'Project {index}', 'description': 'Confirmed details. ' * 100}
                                                 for index in range(50)]
        original = deepcopy(self.state)
        message = progress_message(self.state)
        self.assertIn('Awaiting confirmation (not added):\n- Languages: Kashmiri', message)
        self.assertIn('Other collected changes (not saved):', message)
        self.assertLess(message.index('Kashmiri'), message.index('Other collected changes'))
        self.assertLessEqual(len(message), 5000)
        self.assertEqual(self.state, original)

    def test_formatting_is_plain_text_bounded_and_does_not_mutate_source_state(self):
        self.state['edit_updates']['projects'] = [{'name': f'Project {index}', 'description': 'Confirmed detail. ' * 300}
                                                 for index in range(100)]
        self.state['edit_updates']['personal']['full_name'] = 'Literal <script>value</script>\x1b[31m\u202e\nNew line'
        original = deepcopy(self.state)
        message = progress_message(self.state)
        self.assertLessEqual(len(message), 5000)
        self.assertIn('More pending details are retained', message)
        self.assertNotIn('\x1b', message)
        self.assertNotIn('\u202e', message)
        self.assertIn('Literal <script>value</script>', message)
        self.assertEqual(self.state, original)
