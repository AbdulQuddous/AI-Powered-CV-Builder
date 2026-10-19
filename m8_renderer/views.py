from hashlib import sha256
from io import BytesIO

from django.http import HttpResponse
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError
from cvs.services import VersionConflict
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny

from cvs.models import CV

from .services.renderer import CVRenderer
from .services.pdf_exporter import PDFExporter
from .services.docx_exporter import DOCXExporter
from .services.fixed_docx_exporter import FixedDOCXExporter
from .services.document_artifacts import preview_document


def get_cv_payload(request, cv_id):
    """
    Retrieve the authenticated user's CV.

    Compatible with the existing M2 model.

    M8 reads CV JSON without modifying it.
    """

    cv = get_object_or_404(
        CV,
        pk=cv_id,
        owner=request.user,
    )

    expected = request.query_params.get('expected_version')
    if expected is not None:
        if not expected.isascii() or not expected.isdigit() or not 1 <= len(expected) <= 10 or int(expected) < 1:
            raise ValidationError({'expected_version': 'A positive CV version is required.'})
        if int(expected) != cv.version:
            raise VersionConflict('This CV changed after it was loaded. Reload it before previewing or downloading.')

    cv_data = cv.data

    if not isinstance(cv_data, dict):
        cv_data = {}

    meta = cv_data.get("meta", {})

    if not isinstance(meta, dict):
        meta = {}

    template_id = meta.get("template_id")

    return {
        "template_id": template_id,
        "cv_data": cv_data,
        "document_version": cv.version,
    }


def secure_response(response):
    """
    Prevent sensitive CV responses from being cached.
    """
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"

    return response


class CVPreviewView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, cv_id):

        payload = get_cv_payload(
            request,
            cv_id,
        )

        html = CVRenderer.render_html(
            payload
        )

        response = HttpResponse(
            html,
            content_type="text/html; charset=utf-8",
        )

        return secure_response(response)


class CVDocumentPreviewView(APIView):
    """Paginated saved preview from the exact PDF used by downloads."""
    permission_classes = [IsAuthenticated]

    def get(self, request, cv_id):
        payload = get_cv_payload(request, cv_id)
        html, count, digest = preview_document(payload)
        response = secure_response(HttpResponse(html, content_type='text/html; charset=utf-8'))
        response['X-CV-Version'] = str(payload['document_version'])
        response['X-CV-Page-Count'] = str(count)
        response['X-CV-PDF-SHA256'] = digest
        response['Content-Security-Policy'] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; frame-ancestors 'self'"
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response


class CVPDFExportView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, cv_id):

        payload = get_cv_payload(
            request,
            cv_id,
        )

        pdf_bytes = PDFExporter.generate(
            payload
        )

        response = HttpResponse(
            pdf_bytes,
            content_type="application/pdf",
        )

        response["Content-Disposition"] = (
            f'attachment; filename="cv-{cv_id}.pdf"'
        )
        response['X-CV-Version'] = str(payload['document_version'])
        response['X-CV-PDF-SHA256'] = sha256(pdf_bytes).hexdigest()
        response['X-CV-Page-Count'] = str(len(PdfReader(BytesIO(pdf_bytes)).pages))

        return secure_response(response)


class CVDOCXExportView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, cv_id):

        payload = get_cv_payload(
            request,
            cv_id,
        )

        layout = request.query_params.get('layout', 'editable')
        if layout not in ('fixed', 'editable'):
            raise ValidationError({'layout': 'Choose fixed or editable.'})
        docx_bytes = (FixedDOCXExporter if layout == 'fixed' else DOCXExporter).generate(payload)

        response = HttpResponse(
            docx_bytes,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )

        response["Content-Disposition"] = (
            f'attachment; filename="cv-{cv_id}.docx"'
        )

        response['X-CV-Version'] = str(payload['document_version'])
        response['X-CV-Layout'] = layout
        if layout == 'fixed':
            pdf = PDFExporter.generate(payload)
            response['X-CV-Page-Count'] = str(len(PdfReader(BytesIO(pdf)).pages))
            response['X-CV-PDF-SHA256'] = sha256(pdf).hexdigest()
        return secure_response(response)

class TemplatePreviewView(APIView):
    """Public synthetic examples, or explicitly requested owner-scoped CV data."""
    permission_classes = [AllowAny]

    def get_permissions(self):
        if 'cv_id' in self.request.query_params:
            return [IsAuthenticated()]
        return super().get_permissions()

    def get(self, request, template_id):
        from .samples import sample_cv, PROFILES
        from rest_framework.exceptions import ValidationError
        if 'cv_id' in request.query_params:
            raw = request.query_params['cv_id']
            if not raw.isascii() or not raw.isdigit() or len(raw) > 18:
                raise ValidationError({'cv_id': 'A valid CV ID is required.'})
            data = get_object_or_404(CV, pk=int(raw), owner=request.user).data
        else:
            profile = request.query_params.get('sample', 'comparison')
            if profile != 'comparison' and profile not in PROFILES:
                raise ValidationError({'sample': 'Unknown synthetic profile.'})
            data = sample_cv(profile)
        html = CVRenderer.render_html({'template_id': template_id, 'cv_data': data})
        response = secure_response(HttpResponse(html, content_type='text/html; charset=utf-8'))
        response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response
