"""POST /api/plan/ — plan weather-aware truck routes.

Request JSON:
{
  "origin": "Dallas, TX",
  "destination": "Houston, TX",
  "departure": "2026-11-02T08:00:00-06:00",   // ISO datetime with offset
  "load_weight_lb": 35000,
  "interval_miles": 25,                        // 10 | 25 | 50
  "time_shift_hours": 0                       // optional, 0-48: shifts departure
}

Response JSON:
{
  "origin": {"lat", "lon", "display_name"},
  "destination": {...},
  "interval_miles": 25,
  "effective_departure": ISO,
  "routes": [ summary dicts incl. geometry, checkpoints, miles_by_risk,
              severe_miles, high_miles, avg_risk, duration_* ],
  "recommended_route_index": int,
  "recommendation_reason": str,
  "route_count": int,
  "note": str | null   // e.g. when OSRM returned fewer than 3 alternatives
}
"""

import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import services
from .risk import recommend


def health(request):
    return JsonResponse({"status": "ok"})


def frontend_index(request):
    """Serve the production React build's index.html for non-API paths.

    In single-service deployments the built frontend lives in
    backend/frontend_dist/ (populated by build.sh). Unknown /api/ paths
    stay JSON 404s instead of returning HTML.
    """
    from django.conf import settings
    from django.http import FileResponse, JsonResponse

    if request.path.startswith("/api/"):
        return JsonResponse({"error": "not found"}, status=404)
    candidates = [
        settings.FRONTEND_BUILD_DIR / "index.html",
        settings.STATIC_ROOT / "index.html",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return FileResponse(open(candidate, "rb"), content_type="text/html")
    return JsonResponse(
        {"error": "frontend build not found; run build.sh first"}, status=503
    )


@csrf_exempt
def plan(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON"}, status=400)

    origin_name = (payload.get("origin") or "").strip()
    dest_name = (payload.get("destination") or "").strip()
    departure_raw = (payload.get("departure") or "").strip()
    load_weight = payload.get("load_weight_lb")
    interval = payload.get("interval_miles", 25)
    shift = payload.get("time_shift_hours", 0) or 0
    if not origin_name or not dest_name or not departure_raw:
        return JsonResponse(
            {"error": "origin, destination, and departure are required"}, status=400
        )
    try:
        interval = float(interval)
        if interval not in (10.0, 25.0, 50.0):
            return JsonResponse(
                {"error": "interval_miles must be 10, 25, or 50"}, status=400
            )
        shift = float(shift)
        if not 0 <= shift <= 48:
            return JsonResponse(
                {"error": "time_shift_hours must be between 0 and 48"}, status=400
            )
        load_weight = float(load_weight) if load_weight is not None else None
        departure = datetime.fromisoformat(departure_raw)
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "departure must be ISO datetime; load_weight_lb and "
                      "interval_miles must be numbers"}, status=400
        )
    if departure.tzinfo is None:
        from datetime import timezone
        departure = departure.replace(tzinfo=timezone.utc)
    effective_departure = departure + timedelta(hours=shift)

    try:
        origin = services.geocode(origin_name)
        destination = services.geocode(dest_name)
        routes = services.fetch_routes(origin, destination)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    weather_cache = {}
    summaries = []
    for i, route in enumerate(routes):
        total_miles = route["distance_m"] / 1609.344
        checkpoints = services.sample_checkpoints(
            route["geometry"], interval, total_miles, route["duration_s"],
            effective_departure, load_weight, weather_cache,
        )
        summaries.append(services.summarize_route(i, route, checkpoints))

    recommended_index, reason = recommend(summaries)
    note = None
    if len(summaries) < 3:
        note = (
            f"Only {len(summaries)} genuinely routed option(s) could be "
            "produced for this corridor (OSRM alternatives plus lateral "
            "via-waypoint routes); no routes were invented."
        )
    return JsonResponse(
        {
            "origin": origin,
            "destination": destination,
            "interval_miles": interval,
            "effective_departure": effective_departure.isoformat(),
            "routes": summaries,
            "recommended_route_index": recommended_index,
            "recommendation_reason": reason,
            "route_count": len(summaries),
            "note": note,
        }
    )
