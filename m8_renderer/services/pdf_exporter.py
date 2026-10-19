from hashlib import sha256

from django.core.cache import cache
from weasyprint import HTML, __version__ as WEASYPRINT_VERSION

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

        key = 'm8:pdf:v1:' + sha256((WEASYPRINT_VERSION + html).encode('utf-8')).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached
        pdf_bytes = HTML(
            string=html,
            url_fetcher=blocked_resource_fetcher,
        ).write_pdf()

        if len(pdf_bytes) < 4_000_000:
            cache.set(key, pdf_bytes, timeout=120)
        return pdf_bytes