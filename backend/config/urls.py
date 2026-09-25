from django.contrib import admin
from django.urls import include, path
from chatbot.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health"),
    path("api/", include("chatbot.urls")),
]
