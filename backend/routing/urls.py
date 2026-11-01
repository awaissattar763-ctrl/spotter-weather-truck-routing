from django.urls import path

from . import views

urlpatterns = [
    path("api/health/", views.health),
    path("api/plan/", views.plan),
]
