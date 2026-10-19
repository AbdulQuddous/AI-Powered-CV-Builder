from django.db.models import Q, Case, When, IntegerField
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from .serializers import CVTemplateSerializer
from .services import TemplateService
from .catalogue import definition, FEATURED


class GalleryPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 24


class TemplateListAPIView(generics.ListAPIView):
    serializer_class = CVTemplateSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = TemplateService.list_available_templates()
        query = self.request.query_params
        if query.get('search'):
            term = query['search'][:100]
            qs = qs.filter(Q(name__icontains=term) | Q(description__icontains=term) | Q(id__icontains=term))
        category, level = query.get('category'), query.get('career_level')
        role = query.get('role', '').casefold()
        if category or level or role:
            ids = []
            for t in qs:
                row = definition(t)
                actual = row['category'] if row else {'minimal': 'minimalist', 'technical': 'modern'}.get(t.category, t.category)
                if category and category != actual:
                    continue
                if level and t.supported_levels and level not in t.supported_levels:
                    continue
                if role and not any(role in r.casefold() for r in t.supported_roles):
                    continue
                ids.append(t.pk)
            qs = qs.filter(pk__in=ids)
        if 'page' in query:
            rank = Case(*[When(pk=id, then=index) for index, id in enumerate(FEATURED)], default=len(FEATURED), output_field=IntegerField())
            qs = qs.order_by(rank, 'name')
        return qs

    def get_paginated_response(self, data):
        # DRF keeps pagination state on its paginator instance.
        return self._gallery_paginator.get_paginated_response(data)

    def paginate_queryset(self, queryset):
        if 'page' not in self.request.query_params:
            return None
        self._gallery_paginator = GalleryPagination()
        return self._gallery_paginator.paginate_queryset(queryset, self.request, view=self)


class TemplateDetailAPIView(generics.RetrieveAPIView):
    serializer_class = CVTemplateSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_queryset(self):
        return TemplateService.list_available_templates()
