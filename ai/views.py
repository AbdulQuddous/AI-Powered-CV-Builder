import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ai.exceptions import (
    InvalidAIInputError,
    AIProviderError,
    AIStructuredOutputError,
)
from ai.serializers import (
    ExtractionSerializer,
    CVAnalysisSerializer,
    WritingSerializer,
    CVTailoringSerializer,
)
from ai.services.extraction import extract_cv
from ai.services.analysis import analyze_cv
from ai.services.writing import improve_text
from ai.services.tailoring import tailor_cv


logger = logging.getLogger(__name__)


class BaseAIAPIView(APIView):
    permission_classes = [IsAuthenticated]

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "m6_ai"

    def execute(self, serializer_class, request, handler):
        serializer = serializer_class(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        try:
            result = handler(
                serializer.validated_data
            )

            return Response({
                "data": result
            })

        except InvalidAIInputError as exc:
            return Response(
                {
                    "error": {
                        "code": "invalid_ai_input",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except AIStructuredOutputError as exc:
            logger.warning(
                "M6 AI structured output rejected. operation=%s reason=%s",
                type(self).__name__, exc.reason,
            )
            error = {
                "code": "ai_output_invalid",
                "message": "AI returned an invalid response.",
            }
            if exc.reason != "ai_output_invalid":
                error["reason"] = exc.reason
            return Response(
                {"error": error},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except AIProviderError as exc:
            logger.warning('M6 AI provider request failed. operation=%s reason=%s', type(self).__name__, exc.reason)
            error = {
                'code': 'ai_provider_unavailable',
                'message': 'AI processing is currently unavailable.',
            }
            if exc.reason != 'provider_unavailable':
                error['reason'] = exc.reason
            return Response(
                {'error': error},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class ExtractCVView(BaseAIAPIView):

    def post(self, request):
        return self.execute(
            ExtractionSerializer,
            request,
            lambda data: extract_cv(
                data["raw_text"],
                user_id=request.user.pk,
            ),
        )


class ValidateCVView(BaseAIAPIView):

    def post(self, request):

        def handler(data):
            result = analyze_cv(
                cv=data["cv"],
                user_id=request.user.pk,
                target_role=data["target_role"],
                job_description=data["job_description"],
                use_ai=data["use_ai"],
            )

            # AI recommendations are optional additional
            # warnings, not structural schema errors.
            if data["use_ai"]:
                for suggestion in result["suggestions"]:
                    if suggestion["source"] == "ai":
                        result["warnings"].append({
                            "code": "AI_IMPROVEMENT",
                            "section": suggestion["section"],
                            "severity": suggestion["priority"],
                            "source": "ai",
                            "message": suggestion["message"],
                        })

            return result

        return self.execute(
            CVAnalysisSerializer,
            request,
            handler,
        )


class SuggestionsView(BaseAIAPIView):

    def post(self, request):
        return self.execute(
            CVAnalysisSerializer,
            request,
            lambda data: analyze_cv(
                cv=data["cv"],
                user_id=request.user.pk,
                target_role=data["target_role"],
                job_description=data["job_description"],
                use_ai=data["use_ai"],
            ),
        )


class OptimizeCVView(BaseAIAPIView):

    def post(self, request):

        def handler(data):
            if not data["target_role"].strip():
                raise InvalidAIInputError(
                    "Target role is required."
                )

            return analyze_cv(
                cv=data["cv"],
                user_id=request.user.pk,
                target_role=data["target_role"],
                job_description=data["job_description"],
                use_ai=True,
            )

        return self.execute(
            CVAnalysisSerializer,
            request,
            handler,
        )


class RewriteView(BaseAIAPIView):

    def post(self, request):
        return self.execute(
            WritingSerializer,
            request,
            lambda data: improve_text(
                text=data["text"],
                section=data["section"],
                target_role=data["target_role"],
                job_description=data["job_description"],
                user_id=request.user.pk,
                mode="rewrite",
            ),
        )


class ImproveView(BaseAIAPIView):

    def post(self, request):
        return self.execute(
            WritingSerializer,
            request,
            lambda data: improve_text(
                text=data["text"],
                section=data["section"],
                target_role=data["target_role"],
                job_description=data["job_description"],
                user_id=request.user.pk,
                mode="improve",
            ),
        )


class TailorCVView(BaseAIAPIView):
    def post(self, request):
        return self.execute(
            CVTailoringSerializer,
            request,
            lambda data: tailor_cv(user=request.user, **data),
        )
