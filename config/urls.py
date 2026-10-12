from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
   path('api/auth/', include('accounts.urls')),
   path('api/cvs/', include('cvs.urls')),
   path("api/templates/",include("templates_app.urls")),
   path("api/cv-import/",include("cv_imports.urls")),
   path("api/chat/",include("chatbot.urls")),
   path("api/ai/",include("ai.urls")),
   path("", include("m7_editor.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )