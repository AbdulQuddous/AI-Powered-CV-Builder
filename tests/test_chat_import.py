from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from chatbot.models import ChatMessage, ChatSession
from cvs.models import CV, CVVersion
from cvs.services import create_cv
from m8_renderer.services.context_builder import build_context
from templates_app.models import CVTemplate


class ChatImportTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('savechat@example.com', 'Strong-password-123!')
        self.other = get_user_model().objects.create_user('otherchat@example.com', 'Strong-password-123!')
        self.client.force_authenticate(self.user)
        self.cv = create_cv(user=self.user, values={'name': 'AI Engineer', 'target_role': 'AI Engineer', 'data': {}})
        self.session = ChatSession.objects.create(user=self.user, cv_id=self.cv.id, status='completed', conversation_state={'target_role': 'AI Engineer', 'career_level': 'fresher'})

    def proposal(self, updates, **metadata):
        return ChatMessage.objects.create(session=self.session, role='assistant', content='Collected', cv_updates=updates, **metadata)

    def save_chat(self, **values):
        return self.client.post('/api/cvs/from-chat/', {'session_id': str(self.session.id), **values}, format='json')

    def test_completed_chat_saves_all_sections_and_preview_content(self):
        self.proposal({'personal': {'full_name': 'Ali Khan', 'email': None}, 'education': [{'degree': 'BS', 'institution': 'FAST', 'field_of_study': 'CS', 'end_date': '2026-06'}], 'skills': ['Python', 'Django'], 'experience': [{'company': 'Bitech', 'role': 'Developer'}], 'projects': [{'name': 'Recruitment Module'}, {'name': 'CV Maker'}]})
        self.proposal({'personal': {'email': 'ali@example.com', 'phone': '03001234567', 'location': 'Lahore'}, 'education': [{'start_date': '2022-09', 'grade': '3.2'}], 'experience': [{'responsibilities': ['Developed APIs using Django']}], 'projects': [{'name': 'CV Maker', 'description': 'Creates CVs', 'technologies': ['Django']}], 'summary': 'Backend developer', 'certifications': [{'name': 'Python Course', 'issuer': 'Example Academy'}], 'achievements': ['Built a CV application'], 'languages': [{'name': 'English', 'proficiency': 'fluent'}]})
        self.proposal({'personal': {'location': 'Islamabad', 'full_name': None}})
        response = self.save_chat(expected_version=1)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data['cv']['data']
        self.assertEqual(data['personal']['full_name'], 'Ali Khan')
        self.assertEqual(data['personal']['location'], 'Islamabad')
        self.assertEqual(data['education'][0]['institution'], 'FAST')
        self.assertEqual(data['education'][0]['grade'], '3.2')
        self.assertEqual(data['experience'][0]['job_title'], 'Developer')
        self.assertEqual(data['experience'][0]['highlights'], ['Developed APIs using Django'])
        self.assertEqual(len(data['projects']), 2)
        self.assertEqual(data['projects'][0]['technologies'], [])
        self.assertEqual(data['projects'][1]['technologies'], ['Django'])
        self.assertEqual(data['skills'], ['Python', 'Django'])
        self.assertEqual(data['certifications'][0]['name'], 'Python Course')
        self.assertEqual(data['achievements'], ['Built a CV application'])
        self.assertEqual(data['languages'][0]['proficiency'], 'fluent')
        self.assertEqual(data['summary'], 'Backend developer')
        context = build_context(data)
        self.assertEqual(context['personal']['full_name'], 'Ali Khan')
        self.assertIn('ali@example.com', context['contact'])
        self.assertTrue(any(item['label'] == 'Education' for item in context['sections']))
        self.assertEqual(CVVersion.objects.filter(cv=self.cv).count(), 2)
        CVTemplate.objects.update_or_create(id='modern', defaults={
            'name': 'Modern', 'category': 'professional',
            'template_path': 'cv_templates/modern.html', 'is_available': True,
        })
        preview = self.client.get(f'/api/cvs/{self.cv.id}/preview/')
        self.assertEqual(preview.status_code, 200)
        for detail in ('Ali Khan', 'ali@example.com', 'FAST', 'Django', 'Developed APIs', 'CV Maker'):
            self.assertContains(preview, detail)
        again = self.save_chat(expected_version=2)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['cv']['version'], 2)

    def test_string_languages_and_certifications_do_not_duplicate_on_retry(self):
        self.proposal({'languages': ['English'], 'certifications': ['Python Course']})
        first = self.save_chat(expected_version=1)
        self.assertEqual(first.status_code, 200, first.data)
        again = self.save_chat(expected_version=2)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['cv']['version'], 2)
        self.assertEqual(len(again.data['cv']['data']['languages']), 1)

    def test_new_cv_creation_and_retries_are_idempotent(self):
        self.session.cv_id = None
        self.session.save()
        self.proposal({'personal': {'full_name': 'Ali Khan'}})
        first = self.save_chat()
        self.assertEqual(first.status_code, 200, first.data)
        second = self.save_chat()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data['cv']['id'], second.data['cv']['id'])
        self.session.refresh_from_db()
        self.assertEqual(self.session.cv_id, first.data['cv']['id'])
        self.assertEqual(CV.objects.count(), 2)
        self.assertEqual(second.data['cv']['version'], 1)

    def test_ownership_of_both_session_and_cv(self):
        self.session.user = self.other
        self.session.save()
        self.assertEqual(self.save_chat(expected_version=1).status_code, 404)
        self.session.user = self.user
        other_cv = create_cv(user=self.other, values={'name': 'Private', 'data': {}})
        self.session.cv_id = other_cv.id
        self.session.save()
        self.assertEqual(self.save_chat(expected_version=1).status_code, 404)
        other_cv.refresh_from_db()
        self.assertEqual(other_cv.version, 1)

    def test_active_session_and_stale_version_do_not_save(self):
        self.session.status = 'active'
        self.session.save()
        self.proposal({'summary': 'Developer'})
        self.assertEqual(self.save_chat(expected_version=1).status_code, 409)
        self.session.status = 'completed'
        self.session.save()
        self.assertEqual(self.save_chat(expected_version=99).status_code, 409)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.version, 1)

    def test_preserves_manual_details_and_ignores_irrelevant_proposals(self):
        from cvs.services import update_cv
        data = self.cv.data
        data['personal']['phone'] = '03001234567'
        data['skills'] = ['Git']
        update_cv(user=self.user, cv_id=self.cv.id, values={'data': data, 'expected_version': 1})
        self.proposal({'personal': {'full_name': 'Ali Khan', 'phone': None}, 'skills': ['Python']})
        self.proposal({'personal': {'full_name': 'Mango'}}, intent='irrelevant')
        response = self.save_chat(expected_version=2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['cv']['data']['personal']['phone'], '03001234567')
        self.assertEqual(response.data['cv']['data']['personal']['full_name'], 'Ali Khan')
        self.assertEqual(response.data['cv']['data']['skills'], ['Git', 'Python'])

    def test_year_only_dates_have_explicit_warnings_without_inventing_months(self):
        self.proposal({'education': [{'degree': 'BS', 'institution': 'FAST', 'end_date': '2026'}]})
        response = self.save_chat(expected_version=1)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['cv']['data']['education'][0]['end_date'], '')
        self.assertIn('2026', response.data['warnings'][0])

    def test_ambiguous_project_followup_does_not_mix_projects_or_save(self):
        self.proposal({'projects': [{'name': 'Recruitment'}, {'name': 'CV Maker'}]})
        self.proposal({'projects': [{'technologies': ['Django']}]})
        self.assertEqual(self.save_chat(expected_version=1).status_code, 400)
        self.cv.refresh_from_db()
        self.assertEqual(self.cv.version, 1)

    def test_identical_date_warnings_are_only_returned_once(self):
        self.proposal({'education': [
            {'degree': 'BS', 'institution': 'FAST', 'start_date': '2022', 'end_date': '2026'},
            {'degree': 'Diploma', 'institution': 'Other College', 'start_date': '2022', 'end_date': '2026'},
        ]})
        response = self.save_chat(expected_version=1)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['warnings']), 2)
        self.assertEqual(len(response.data['cv']['data']['education']), 2)

    def test_saving_chat_again_preserves_months_confirmed_in_editor(self):
        from cvs.services import update_cv
        self.proposal({'education': [{'degree': 'BS', 'institution': 'FAST', 'start_date': '2022', 'end_date': '2026'}]})
        response = self.save_chat(expected_version=1)
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data['cv']['data']
        data['education'][0]['start_date'] = '2022-09'
        data['education'][0]['end_date'] = '2026-06'
        update_cv(user=self.user, cv_id=self.cv.id, values={'data': data, 'expected_version': 2})
        again = self.save_chat(expected_version=3)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['cv']['data']['education'][0]['start_date'], '2022-09')
        self.assertEqual(again.data['cv']['data']['education'][0]['end_date'], '2026-06')
        self.assertEqual(again.data['warnings'], [])
        self.assertEqual(again.data['cv']['version'], 3)

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.save_chat().status_code, 401)
