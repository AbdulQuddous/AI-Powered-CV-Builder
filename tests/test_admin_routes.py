"""Admin session security and the route families used by the workspace clients."""
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class WorkspaceNavigationTests(SimpleTestCase):
    def test_home_opens_the_dashboard(self):
        self.assertRedirects(self.client.get('/'), '/dashboard/', fetch_redirect_response=False)

    def test_admin_link_is_absent_from_workspace_pages(self):
        for path in ('/dashboard/', '/templates/', '/cvs/1/edit/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotContains(response, 'href="/admin/"')
                self.assertNotContains(response, 'Staff access; sign in with your admin account')
        self.assertIsNotNone(finders.find('admin/css/base.css'))

    def test_polish_action_is_available_in_the_existing_review(self):
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'id="aiImprove"')
        self.assertContains(response, 'Polish wording')


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.password = 'Admin-route-Strong-736!'
        cls.admin = User.objects.create_superuser('admin-route@example.com', cls.password)
        cls.member = User.objects.create_user('member-route@example.com', cls.password)
        cls.staff = User.objects.create_user('staff-route@example.com', cls.password, is_staff=True)

    def test_admin_login_renders_and_requires_email_and_csrf(self):
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, 'CV Maker administration')
        self.assertContains(response, '>Email:</label>')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'name="username"')  # Django's login form name; accepts email.
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(reverse('admin:login'), {
            'username': self.admin.email, 'password': self.password,
        }).status_code, 403)

    def test_anonymous_member_and_jwt_cannot_enter_admin(self):
        login = '/admin/login/?next=/admin/'
        self.assertRedirects(self.client.get('/admin/'), login, fetch_redirect_response=False)
        token = str(RefreshToken.for_user(self.admin).access_token)
        self.assertRedirects(self.client.get('/admin/', HTTP_AUTHORIZATION='Bearer ' + token),
                             login, fetch_redirect_response=False)
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get('/admin/'), login, fetch_redirect_response=False)

    def test_admin_login_accepts_email_and_has_working_model_links(self):
        response = self.client.post(reverse('admin:login'), {
            'username': self.admin.email, 'password': self.password, 'next': '/admin/',
        })
        self.assertRedirects(response, '/admin/')
        response = self.client.get('/admin/')
        self.assertContains(response, 'href="/dashboard/"')
        for name in ('accounts_user_changelist', 'templates_app_cvtemplate_changelist',
                     'cv_imports_cvimport_changelist', 'chatbot_chatsession_changelist'):
            with self.subTest(name=name):
                url = reverse('admin:' + name)
                self.assertContains(response, f'href="{url}"')
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_without_model_permissions_cannot_manage_templates(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:templates_app_cvtemplate_changelist')).status_code, 403)

    def test_custom_user_add_change_and_password_hashing(self):
        self.client.force_login(self.admin)
        url = reverse('admin:accounts_user_add')
        response = self.client.get(url)
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="username"')
        response = self.client.post(url, {
            'email': 'new-admin-user@example.com', 'full_name': 'New account',
            'usable_password': 'true', 'password1': self.password, 'password2': self.password,
            '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302, response.context and response.context['adminform'].form.errors)
        created = get_user_model().objects.get(email='new-admin-user@example.com')
        self.assertTrue(created.check_password(self.password))
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        response = self.client.get(reverse('admin:accounts_user_change', args=[created.pk]))
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="username"')

    def test_admin_session_does_not_replace_api_jwt_authentication(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/cvs/').status_code, 401)


class PrivateEndpointRoutingTests(TestCase):
    def test_all_workspace_private_operations_are_routed_and_require_jwt(self):
        client = APIClient()
        session = '00000000-0000-0000-0000-000000000001'
        operations = [
            ('get', '/api/auth/me/'), ('patch', '/api/auth/me/'), ('post', '/api/auth/logout/'),
            ('get', '/api/cvs/'), ('post', '/api/cvs/'), ('post', '/api/cvs/from-chat/'),
            ('get', '/api/cvs/1/'), ('patch', '/api/cvs/1/'), ('delete', '/api/cvs/1/'),
            ('post', '/api/cvs/1/duplicate/'), ('get', '/api/cvs/1/versions/'),
            ('post', '/api/cvs/1/versions/'), ('post', '/api/cvs/1/restore/'),
            ('post', '/api/cv-import/upload/'), ('get', '/api/cv-import/1/'),
            ('post', '/api/cv-import/1/extract/'),
            ('get', '/api/chat/sessions/'), ('post', '/api/chat/sessions/'),
            ('get', f'/api/chat/sessions/{session}/'),
            ('post', f'/api/chat/sessions/{session}/messages/'),
            ('get', f'/api/chat/sessions/{session}/draft/'),
            ('post', f'/api/chat/sessions/{session}/reopen/'),
            ('post', f'/api/chat/sessions/{session}/final-review/'),
            ('post', f'/api/chat/sessions/{session}/final-review/decisions/'),
            ('get', '/api/cvs/1/preview/'), ('get', '/api/cvs/1/preview/document/'),
            ('post', '/api/cvs/1/export/pdf/'), ('post', '/api/cvs/1/export/docx/'),
        ] + [('post', f'/api/ai/{operation}/') for operation in (
            'extract', 'validate', 'suggestions', 'optimize', 'rewrite', 'improve', 'tailor',
        )]
        for method, path in operations:
            with self.subTest(method=method, path=path):
                self.assertEqual(getattr(client, method)(path).status_code, 401)

    def test_public_catalogue_detail_and_sample_preview_are_reachable(self):
        client = APIClient()
        for path in ('/api/templates/', '/api/templates/modern/',
                     '/api/cvs/templates/modern/preview/'):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 200)
