from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import CV
from .serializers import (CVReadSerializer, CVWriteSerializer, CVPatchSerializer,
                          CVVersionSerializer, CheckpointSerializer, DuplicateSerializer, ChatImportSerializer)
from . import services

class CVPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class CVViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CVReadSerializer
    pagination_class = CVPagination
    http_method_names = ['get','post','patch','delete','head','options']
    def get_queryset(self):
        return CV.objects.filter(owner=self.request.user)
    @action(detail=False, methods=['post'], url_path='from-chat')
    def from_chat(self, request):
        from .chat_import import save_chat_cv
        serializer = ChatImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cv, warnings = save_chat_cv(user=request.user, **serializer.validated_data)
        return Response({'cv': CVReadSerializer(cv).data, 'warnings': warnings})
    def create(self, request):
        serializer = CVWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cv = services.create_cv(user=request.user, values=serializer.validated_data)
        return Response(CVReadSerializer(cv).data, status=status.HTTP_201_CREATED)
    def partial_update(self, request, pk=None):
        self.get_object()  # Hide other users' IDs before body validation.
        serializer = CVPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cv = services.update_cv(user=request.user, cv_id=pk, values=serializer.validated_data)
        return Response(CVReadSerializer(cv).data)
    def destroy(self, request, pk=None):
        services.delete_cv(user=request.user, cv_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        self.get_object()
        serializer = DuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cv = services.duplicate_cv(user=request.user, cv_id=pk, **serializer.validated_data)
        return Response(CVReadSerializer(cv).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=['get','post'])
    def versions(self, request, pk=None):
        cv = self.get_object()
        if request.method == 'GET':
            page = self.paginate_queryset(cv.versions.all())
            return self.get_paginated_response(CVVersionSerializer(page,many=True).data)
        serializer = CheckpointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = services.checkpoint_cv(user=request.user, cv_id=pk, **serializer.validated_data)
        return Response(CVVersionSerializer(version).data, status=status.HTTP_201_CREATED)
