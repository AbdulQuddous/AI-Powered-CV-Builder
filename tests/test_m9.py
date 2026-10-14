from django.test import SimpleTestCase
from django.urls import reverse
from django.contrib.staticfiles import finders
from unittest.mock import patch


class M9DashboardTests(SimpleTestCase):

    def test_dashboard_page_loads(self):
        """
        Dashboard page must return HTTP 200.
        """

        response = self.client.get(
            "/dashboard/"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "m9_dashboard/dashboard.html",
        )

    def test_dashboard_contains_required_elements(self):
        """
        Check that the dashboard interface
        contains the required components.
        """

        response = self.client.get(
            "/dashboard/"
        )

        self.assertContains(
            response,
            'id="cardsGrid"',
        )

        self.assertContains(
            response,
            'id="searchInput"',
        )

        self.assertContains(
            response,
            'id="templateFilter"',
        )

        self.assertContains(
            response,
            'id="createForm"',
        )

        self.assertContains(
            response,
            'id="previewFrame"',
        )

    def test_dashboard_static_files_exist(self):
        """
        Confirm JavaScript and CSS files
        are discoverable by Django.
        """

        js_file = finders.find(
            "m9_dashboard/js/dashboard.js"
        )

        css_file = finders.find(
            "m9_dashboard/css/dashboard.css"
        )

        self.assertIsNotNone(js_file)
        self.assertIsNotNone(css_file)

    def test_dashboard_named_route(self):
        """
        Verify dashboard URL configuration.
        """

        url = reverse(
            "m9_dashboard:dashboard"
        )

        self.assertEqual(
            url,
            "/dashboard/",
        )

    def test_dashboard_rejects_post(self):
        """
        Dashboard page only supports GET.
        """

        response = self.client.post(
            "/dashboard/"
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_ai_chat_controls_preserve_existing_dashboard(self):
        response = self.client.get("/dashboard/")
        for element_id in (
            "createAI", "chatModal", "chatHistory", "chatForm", "chatInput",
            "chatSend", "chatRetry", "chatError", "chatComplete", "chatEditor", "chatSave", "chatSaveStatus",
            "cardsGrid", "createForm", "previewFrame",
        ):
            with self.subTest(element_id=element_id):
                self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'maxlength="10000"')
        self.assertContains(response, 'aria-labelledby="chatTitle"')

    def test_import_controls_and_assets_are_available(self):
        response = self.client.get('/dashboard/')
        for element_id in ('importCV', 'importModal', 'importFile', 'importUpload', 'importExtract', 'importRefresh', 'importText'):
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'accept=".pdf,.docx"')
        self.assertContains(response, 'does not create or update a saved CV')
        self.assertTemplateUsed(response, 'm9_dashboard/import_modal.html')
        for asset in ('js/import_cv.js', 'css/import_cv.css'):
            self.assertIsNotNone(finders.find('m9_dashboard/' + asset))

    def test_ai_intelligence_controls_and_assets(self):
        response = self.client.get('/dashboard/')
        for element_id in ('aiModal', 'aiRole', 'aiValidate', 'aiOptimize', 'aiViewSuggestions', 'aiRewrite', 'aiImprove', 'aiApply', 'aiDiscard', 'importParse', 'importConfirm'):
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'Role')
        self.assertContains(response, 'not a certified ATS score')
        self.assertTemplateUsed(response, 'm9_dashboard/ai_review.html')
        for asset in ('js/ai_api.js', 'js/ai_ui.js', 'js/ai_review.js', 'css/ai_review.css'):
            self.assertIsNotNone(finders.find('m9_dashboard/' + asset))

    def test_crud_dialogs_and_asset_are_available(self):
        response = self.client.get('/dashboard/')
        self.assertTemplateUsed(response, 'm9_dashboard/crud_modals.html')
        for element_id in ('deleteModal', 'deleteCVName', 'deleteConfirm', 'deleteCancel', 'deleteError', 'versionsModal', 'versionsRows', 'versionsMore'):
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'aria-describedby="deleteDescription"')
        self.assertContains(response, 'History is read-only')
        self.assertIsNotNone(finders.find('m9_dashboard/js/cv_operations.js'))

    def test_registration_form_reuses_dashboard_authentication_interface(self):
        response = self.client.get('/dashboard/')
        self.assertTemplateUsed(response, 'm9_dashboard/register_modal.html')
        for element_id in ('openRegister', 'registerModal', 'registerForm', 'registerName',
                           'registerEmail', 'registerPassword', 'registerConfirm', 'registerError',
                           'registerSubmit', 'backToLogin'):
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'aria-labelledby="registerTitle"')
        self.assertContains(response, 'autocomplete="new-password"')

    def test_dashboard_reloads_assets_after_an_update(self):
        from m9_dashboard.views import dashboard_asset_version
        self.assertGreater(int(dashboard_asset_version()), 0)
        for revision in ('100', '200'):
            with patch('m9_dashboard.views.dashboard_asset_version', return_value=revision):
                response = self.client.get('/dashboard/')
            self.assertContains(response, f'/static/m9_dashboard/js/dashboard.js?v={revision}')
            self.assertContains(response, f'/static/m9_dashboard/js/cv_operations.js?v={revision}')
            self.assertContains(response, f'/static/m9_dashboard/css/dashboard.css?v={revision}')
            self.assertIn('no-store', response['Cache-Control'])

    def test_profile_form_edits_name_and_displays_readonly_email(self):
        response = self.client.get('/dashboard/')
        self.assertTemplateUsed(response, 'm9_dashboard/profile_modal.html')
        for element_id in ('profileBtn', 'profileModal', 'profileForm', 'profileEmail',
                           'profileName', 'profileError', 'profileStatus', 'profileSubmit',
                           'profileCancel', 'profileRetry'):
            self.assertContains(response, f'id="{element_id}"')
        self.assertContains(response, 'readonly aria-describedby="profileEmailHelp"')
        self.assertContains(response, 'aria-labelledby="profileTitle"')
