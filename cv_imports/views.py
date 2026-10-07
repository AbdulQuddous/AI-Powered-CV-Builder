from rest_framework import status
from rest_framework.parsers import (
    FormParser,
    MultiPartParser,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CVImport
from .serializers import (
    CVImportDetailSerializer,
    CVImportUploadSerializer,
)
from .services.extractors import (
    ExtractionError,
)
from .services.import_service import (
    process_cv_import,
)


class CVImportUploadAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def post(self, request):

        serializer = CVImportUploadSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        uploaded_file = (
            serializer.validated_data["file"]
        )

        file_type = (
            serializer.context["file_type"]
        )

        cv_import = CVImport.objects.create(
            user=request.user,
            file=uploaded_file,
            original_file_name=(
                uploaded_file.name
            ),
            file_type=file_type,
            file_size=uploaded_file.size,
            status=CVImport.Status.UPLOADED,
        )

        response_serializer = (
            CVImportDetailSerializer(
                cv_import
            )
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

class CVImportDetailAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def get_object(
        self,
        request,
        import_id,
    ):

        try:
            return CVImport.objects.get(
                id=import_id,
                user=request.user,
            )

        except CVImport.DoesNotExist:
            return None

    def get(
        self,
        request,
        import_id,
    ):

        cv_import = self.get_object(
            request,
            import_id,
        )

        if cv_import is None:
            return Response(
                {
                    "detail": (
                        "CV import not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        serializer = CVImportDetailSerializer(
            cv_import
        )

        return Response(
            serializer.data
        )

class CVImportExtractAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(
        self,
        request,
        import_id,
    ):

        try:
            cv_import = CVImport.objects.get(
                id=import_id,
                user=request.user,
            )

        except CVImport.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "CV import not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        try:
            process_cv_import(
                cv_import
            )

        except ExtractionError as exc:
            return Response(
                {
                    "import_id": cv_import.id,
                    "status": (
                        CVImport.Status.FAILED
                    ),
                    "detail": str(exc),
                },
                status=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
            )

        serializer = CVImportDetailSerializer(
            cv_import
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )