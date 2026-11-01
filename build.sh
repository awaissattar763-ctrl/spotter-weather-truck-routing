#!/usr/bin/env bash
# Build the app exactly the way Render's free web service will:
# install backend deps, build the React frontend, copy the build into
# Django's static-serving directory, and collect static files — so ONE
# gunicorn process serves both the frontend and the /api/* API.
# No secrets, keys, or tokens are used or written anywhere: the app only
# calls keyless public APIs (OSRM, Nominatim, Open-Meteo).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required to build the frontend but was not found." >&2
  exit 1
fi

python -m pip install -r "$ROOT/backend/requirements.txt"

cd "$ROOT/frontend"
npm ci
npm run build

rm -rf "$ROOT/backend/frontend_dist"
cp -r "$ROOT/frontend/dist" "$ROOT/backend/frontend_dist"

cd "$ROOT/backend"
python manage.py collectstatic --noinput

echo "Build complete: backend/frontend_dist/ + backend/staticfiles/ ready."
