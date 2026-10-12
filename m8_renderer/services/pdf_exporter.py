from weasyprint import HTML

from .renderer import CVRenderer


def blocked_resource_fetcher(url):
    """
    Prevent document rendering from fetching external
    network or filesystem resources.

    Our M8 HTML templates use embedded CSS.
    """
    raise ValueError(
        "External resources are not allowed."
    )


class PDFExporter:

    @staticmethod
    def generate(payload):
        """
        Input:
        {
            "template_id": "modern",
            "cv_data": {...}
        }

        Output:
            PDF bytes
        """

        html = CVRenderer.render_html(payload)

        pdf_bytes = HTML(
            string=html,
            url_fetcher=blocked_resource_fetcher,
        ).write_pdf()

        return pdf_bytes