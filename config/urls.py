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
   path("api/cvs/",include("m8_renderer.urls")),
   path("",include("m9_dashboard.urls")),
]

# Imported CV documents are private storage, never public /media/ assets.
