from rest_framework.routers import DefaultRouter
from .views import CVViewSet
router = DefaultRouter()
router.register('', CVViewSet, basename='cv')
urlpatterns = router.urls
