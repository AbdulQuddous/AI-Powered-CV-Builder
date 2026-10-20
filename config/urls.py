from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView


admin.site.site_header = 'CV Maker administration'
admin.site.site_title = 'CV Maker admin'
admin.site.index_title = 'Manage CV Maker'
admin.site.site_url = reverse_lazy('m9_dashboard:dashboard')


urlpatterns = [
   path('', RedirectView.as_view(pattern_name='m9_dashboard:dashboard', permanent=False), name='home'),
   path('admin/', admin.site.urls),
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
