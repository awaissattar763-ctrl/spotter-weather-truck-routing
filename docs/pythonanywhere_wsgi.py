# PythonAnywhere WSGI configuration for the Spotter assessment app.
#
# Copy this file's contents VERBATIM into the WSGI configuration file
# of the PythonAnywhere web app (Web tab -> Code -> WSGI configuration
# file), then edit ONLY the two marked lines:
#   1. <username> -> your PythonAnywhere username
#   2. the DJANGO_SECRET_KEY value -> a fresh secret you generate at
#      deploy time (e.g. from a Python shell: django.core.management.
#      utils.get_random_secret_key()). NEVER commit a real secret key
#      to the repo.
#
# The repo layout on PythonAnywhere after `git clone` is assumed to be:
#   /home/<username>/spotter-weather-truck-routing/
#     backend/                  <- Django project (this WSGI file's home
#                                  is backend/spotter/ in the repo, but
#                                  PythonAnywhere's WSGI file lives
#                                  outside the repo; sys.path below
#                                  points at backend/)
#       spotter/settings.py
#       frontend_dist/          <- prebuilt React build, committed to
#                                  git (no node build step on the server)
#
# No node build step runs on PythonAnywhere: the frontend build is
# already in backend/frontend_dist/ and is served by WhiteNoise from
# the same WSGI process as the /api/* API.

import os
import sys

# --- EDIT THIS LINE: your PythonAnywhere username ---
USERNAME = "<username>"

REPO_BACKEND = f"/home/{USERNAME}/spotter-weather-truck-routing/backend"
if REPO_BACKEND not in sys.path:
    sys.path.insert(0, REPO_BACKEND)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter.settings")

# --- EDIT THIS LINE: fresh secret generated at deploy time ---
os.environ.setdefault("DJANGO_SECRET_KEY", "<paste-a-fresh-generated-secret-here>")
os.environ.setdefault("DJANGO_DEBUG", "0")
# Hostname for ALLOWED_HOSTS (settings.py also reads this env var):
os.environ.setdefault(
    "PYTHONANYWHERE_HOSTNAME", f"{USERNAME}.pythonanywhere.com"
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
