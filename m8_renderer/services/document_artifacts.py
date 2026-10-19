"""Actual PDF pages shared by saved previews and fixed-layout Word downloads."""
from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

from django.core.cache import cache
from django.template.loader import render_to_string
from pypdf import PdfReader
from rest_framework.exceptions import APIException

from .pdf_exporter import PDFExporter


class PageRenderingUnavailable(APIException):
    status_code = 503
    default_code = 'page_rendering_unavailable'
    default_detail = 'Document page rendering is unavailable. Download the PDF or retry shortly.'


def pdf_pages(pdf_bytes, *, dpi=200):
    """Rasterize the PDF itself; browser fonts/layout never determine page breaks."""
    digest = sha256(pdf_bytes).hexdigest()
    key = f'm8:pages:v1:{dpi}:{digest}'
    stored = cache.get(key)
    if stored is not None:
        return stored
    executable = shutil.which('pdftoppm')
    if not executable:
        raise PageRenderingUnavailable()
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    try:
        with tempfile.TemporaryDirectory(prefix='cv-document-pages-') as tmp:
            source, prefix = Path(tmp) / 'document.pdf', Path(tmp) / 'page'
            source.write_bytes(pdf_bytes)
            subprocess.run([executable, '-r', str(dpi), '-png', str(source), str(prefix)],
                           check=True, capture_output=True, timeout=90)
            images = {int(path.stem.split('-')[-1]): path for path in Path(tmp).glob('page-*.png')}
            for index, page in enumerate(reader.pages, 1):
                # Poppler pads numbers according to the total number of pages.
                path = images[index]
                pages.append({'number': index, 'image': path.read_bytes(),
                              'width_pt': float(page.mediabox.width), 'height_pt': float(page.mediabox.height),
                              'text': page.extract_text() or ''})
    except (OSError, subprocess.SubprocessError, KeyError) as exc:
        raise PageRenderingUnavailable() from exc
    # Personal content stays in the server's transient cache; HTTP responses are no-store.
    if sum(len(page['image']) for page in pages) < 12_000_000:
        cache.set(key, pages, timeout=120)
    return pages


def preview_document(payload):
    pdf = PDFExporter.generate(payload)
    pages = pdf_pages(pdf)
    context = {'pages': [{**page, 'image_url': 'data:image/png;base64,' + b64encode(page['image']).decode('ascii')}
                         for page in pages], 'page_count': len(pages)}
    return render_to_string('m8_renderer/document_preview.html', context), len(pages), sha256(pdf).hexdigest()
