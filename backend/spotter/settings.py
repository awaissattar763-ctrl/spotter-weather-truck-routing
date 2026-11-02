import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")

# Production default is DEBUG off; local dev can opt back in with
# DJANGO_DEBUG=1. Never enable DEBUG on a deployed service.
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

# Hosts: explicit ALLOWED_HOSTS env (comma-separated) wins; otherwise
# Render's external hostname (when present) plus local defaults.
# PythonAnywhere: set PYTHONANYWHERE_HOSTNAME to the site's hostname
# (e.g. <username>.pythonanywhere.com), or PYTHONANYWHERE_USER to
# derive it; no other host behaviour changes.
_allowed = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    _allowed.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
if os.environ.get("PYTHONANYWHERE_HOSTNAME"):
    _allowed.append(os.environ["PYTHONANYWHERE_HOSTNAME"])
if os.environ.get("PYTHONANYWHERE_USER"):
    _allowed.append(f"{os.environ['PYTHONANYWHERE_USER']}.pythonanywhere.com")
ALLOWED_HOSTS = _allowed or ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "spotter.cors_middleware.CorsMiddleware",
]

ROOT_URLCONF = "spotter.urls"
WSGI_APPLICATION = "spotter.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

# --- Single-service static serving (production React build + API) ---
# build.sh copies frontend/dist/ to backend/frontend_dist/. WhiteNoise
# serves that directory at the site root, so /assets/* (Vite's hashed
# bundles) resolve without a separate frontend host, and /api/* keeps
# routing to Django views. In local dev without a build, the frontend
# runs on Vite's dev server (port 5173) and proxies /api to Django.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_BUILD_DIR = BASE_DIR / "frontend_dist"
if FRONTEND_BUILD_DIR.is_dir():
    STATICFILES_DIRS = [FRONTEND_BUILD_DIR]
    WHITENOISE_ROOT = FRONTEND_BUILD_DIR
