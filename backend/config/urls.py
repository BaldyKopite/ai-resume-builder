"""URL configuration for the AI Resume Builder backend."""
from django.urls import include, path

urlpatterns = [
    path("api/", include("tailor.urls")),
]
