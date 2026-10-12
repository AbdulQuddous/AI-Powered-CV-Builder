from django.test import SimpleTestCase
from django.urls import reverse


class CVEditorShellTests(SimpleTestCase):
    def test_page_has_cv_id_and_does_not_embed_cv_data(self):
        url = reverse("m7_editor:edit", kwargs={"cv_id": "42"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="m7-config"')
        self.assertContains(response, 'cvEditor')
        self.assertNotContains(response, '"email": "someone@example.com"')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
