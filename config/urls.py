from django.urls import path, include
urlpatterns = [path('api/auth/', include('accounts.urls')),
               path('api/cvs/', include('cvs.urls')),
               path("api/templates/",include("templates_app.urls")),
            ]
