from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from cvs.models import CV

from .services.renderer import CVRenderer
from .services.pdf_exporter import PDFExporter
from .services.docx_exporter import DOCXExporter


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

        return secure_response(response)


class CVDOCXExportView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, cv_id):

        payload = get_cv_payload(
            request,
            cv_id,
        )

        docx_bytes = DOCXExporter.generate(
            payload
        )

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

        return secure_response(response)