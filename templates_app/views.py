# templates_app/views.py

from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import CVTemplate
from .serializers import CVTemplateSerializer


class TemplateListAPIView(generics.ListAPIView):
    serializer_class = CVTemplateSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return CVTemplate.objects.filter(
            is_available=True
        )


class TemplateDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CVTemplateSerializer
    permission_classes = [AllowAny]
    lookup_field = "id"

    def get_queryset(self):
        return CVTemplate.objects.filter(
            is_available=True
        )