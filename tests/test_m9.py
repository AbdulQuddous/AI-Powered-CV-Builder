from django.test import SimpleTestCase
from django.urls import reverse
from django.contrib.staticfiles import finders


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