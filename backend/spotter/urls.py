from django.urls import include, path, re_path

from routing import views as routing_views

urlpatterns = [
    path("", include("routing.urls")),
    # Single-page frontend fallback for every non-API path.
    re_path(r"^.*$", routing_views.frontend_index),
]
