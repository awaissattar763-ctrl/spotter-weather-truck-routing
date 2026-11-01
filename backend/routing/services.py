"""Server-side routing / geocoding / weather services.

Data sources (all free, no API keys):
- Geocoding: Nominatim (OpenStreetMap), https://nominatim.openstreetmap.org
- Routing:   OSRM public demo server, https://router.project-osrm.org
- Weather:   Open-Meteo forecast API, https://api.open-meteo.com

No route, checkpoint, or weather value is ever invented: if an upstream
call fails, the error propagates to the API response instead of a fake
value being returned. Weather that cannot be fetched for a checkpoint is
reported as null with risk "Unknown" and is excluded from the averages.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone

import requests

from .risk import UNKNOWN, SCORE, classify_checkpoint

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "spotter-assessment/1.0 (local assessment build)"
EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def geocode(place):
    """Return {'lat', 'lon', 'display_name'} for a place name, or raise ValueError."""
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": place, "format": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode place: {place!r}")
    first = results[0]
    return {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "display_name": first.get("display_name", place),
    }


def _osrm_route(coords, timeout=30):
    """Single OSRM request. Returns list of route dicts or raises RuntimeError."""
    try:
        resp = requests.get(
            OSRM_URL.format(coords=coords),
            params={
                "alternatives": 3,
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Routing service unreachable: {exc}") from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Routing service returned no routes: {data.get('code')}")
    return [
        {
            "distance_m": route["distance"],
            "duration_s": route["duration"],
            "geometry": route["geometry"]["coordinates"],
        }
        for route in data["routes"]
    ]


def _midpoint_and_heading(geometry):
    """Point near the route's midpoint plus the route heading there."""
    if len(geometry) < 2:
        return None
    mid = geometry[len(geometry) // 2]
    before = geometry[max(0, len(geometry) // 2 - 5)]
    after = geometry[min(len(geometry) - 1, len(geometry) // 2 + 5)]
    heading = math.atan2(after[0] - before[0], after[1] - before[1])
    return mid[1], mid[0], heading  # lat, lon, heading (radians, east-of-north)


def _offset_point(lat, lon, heading, side_miles):
    """Point `side_miles` perpendicular to `heading` from (lat, lon)."""
    perp = heading + math.pi / 2
    dlat = side_miles * math.cos(perp) / 69.0
    dlon = side_miles * math.sin(perp) / (69.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _is_duplicate(candidate, existing):
    for route in existing:
        if abs(candidate["distance_m"] - route["distance_m"]) < 1609:  # <1 mile apart
            return True
    return False


def fetch_routes(origin, destination):
    """Return up to 3 routes: OSRM alternatives first, then genuinely
    OSRM-routed alternatives via lateral waypoints if the demo server
    returns fewer than 3 (it commonly returns 1-2). Via-waypoint routes
    are labelled with alternative_method='via_waypoint'; their geometry,
    distance, and duration all still come from OSRM — nothing is invented.
    Raises RuntimeError on failure."""
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    routes = _osrm_route(coords)
    for route in routes:
        route["alternative_method"] = "osrm"
    if len(routes) >= 3:
        return routes[:3]
    anchor = _midpoint_and_heading(routes[0]["geometry"])
    if anchor is None:
        return routes
    mid_lat, mid_lon, heading = anchor
    for side_miles in (25, 50, -25, -50):
        if len(routes) >= 3:
            break
        v_lat, v_lon = _offset_point(mid_lat, mid_lon, heading, side_miles)
        via_coords = (
            f"{origin['lon']},{origin['lat']};{v_lon},{v_lat};"
            f"{destination['lon']},{destination['lat']}"
        )
        try:
            extra = _osrm_route(via_coords)
        except RuntimeError:
            continue
        for candidate in extra:
            if len(routes) >= 3:
                break
            if _is_duplicate(candidate, routes):
                continue
            candidate["alternative_method"] = "via_waypoint"
            routes.append(candidate)
    return routes[:3]


def _fetch_weather_for_hour(lat, lon, utc_hour_iso):
    """Fetch one hour of Open-Meteo data. Returns (wind, rain, snow) or None.

    utc_hour_iso is an ISO hour string in UTC, e.g. '2026-11-02T14:00'.
    Open-Meteo is queried with timezone=UTC so the returned hourly times
    line up with the ETA converted to UTC.
    """
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "wind_speed_10m,precipitation,snowfall",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "UTC",
                "forecast_days": 16,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
    except (requests.RequestException, KeyError, ValueError):
        return None
    times = hourly.get("time", [])
    if utc_hour_iso not in times:
        return None
    i = times.index(utc_hour_iso)
    try:
        wind = hourly["wind_speed_10m"][i]
        rain = hourly["precipitation"][i]
        snow = hourly["snowfall"][i]
    except (KeyError, IndexError, TypeError):
        return None
    if wind is None and rain is None and snow is None:
        return None
    return (wind, rain, snow)


def sample_checkpoints(geometry, interval_miles, total_distance_miles,
                       duration_s, departure_dt, load_weight_lb, weather_cache):
    """Walk the route geometry, placing a checkpoint every interval_miles
    (plus the final destination). Each checkpoint carries its ETA, computed
    as departure + cumulative travel time assuming the route's average
    speed (total distance / total duration), and its weather + risk.

    weather_cache: dict shared across routes in one request, keyed by
    (rounded lat, rounded lon, utc hour) to avoid duplicate API calls.
    Returns a list of checkpoint dicts.
    """
    total_m = total_distance_miles
    checkpoints = []
    # Points along the geometry with cumulative miles.
    cumulative = [0.0]
    for (lon1, lat1), (lon2, lat2) in zip(geometry, geometry[1:]):
        cumulative.append(cumulative[-1] + haversine_miles(lat1, lon1, lat2, lon2))

    def point_at(target_miles):
        """Interpolate a (lat, lon) at target_miles along the geometry."""
        for i in range(1, len(cumulative)):
            if cumulative[i] >= target_miles:
                seg_len = cumulative[i] - cumulative[i - 1]
                frac = 0.0 if seg_len == 0 else (target_miles - cumulative[i - 1]) / seg_len
                (lon1, lat1), (lon2, lat2) = geometry[i - 1], geometry[i]
                return lat1 + frac * (lat2 - lat1), lon1 + frac * (lon2 - lon1)
        lon_last, lat_last = geometry[-1][0], geometry[-1][1]
        return lat_last, lon_last

    targets = []
    m = 0.0
    while m < total_m:
        targets.append(m)
        m += interval_miles
    if not targets or targets[-1] < total_m - 1e-9:
        targets.append(total_m)

    # Fetch weather concurrently (bounded pool), then assemble in order.
    jobs = []
    for target in targets:
        lat, lon = point_at(target)
        frac = target / total_m if total_m else 0.0
        from datetime import timedelta
        eta = departure_dt + timedelta(seconds=duration_s * frac)
        eta_utc = eta.astimezone(timezone.utc)
        hour_iso = eta_utc.strftime("%Y-%m-%dT%H:00")
        jobs.append((target, lat, lon, eta, hour_iso))

    def resolve(job):
        target, lat, lon, eta, hour_iso = job
        key = (round(lat, 3), round(lon, 3), hour_iso)
        if key not in weather_cache:
            weather_cache[key] = _fetch_weather_for_hour(lat, lon, hour_iso)
        return weather_cache[key]

    with ThreadPoolExecutor(max_workers=8) as pool:
        weathers = list(pool.map(resolve, jobs))

    for (target, lat, lon, eta, _hour), weather in zip(jobs, weathers):
        if weather is None:
            wind = rain = snow = None
            risk = UNKNOWN
        else:
            wind, rain, snow = weather
            risk = classify_checkpoint(wind, rain, snow, load_weight_lb)
        checkpoints.append(
            {
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "miles_from_start": round(target, 2),
                "eta": eta.isoformat(),
                "wind_mph": wind,
                "rain_in_hr": rain,
                "snow_in_hr": snow,
                "risk": risk,
            }
        )
    return checkpoints


def summarize_route(index, route, checkpoints):
    """Compute per-route miles by risk, average risk, and durations."""
    miles_by_risk = {level: 0.0 for level in ["Low", "Moderate", "High", "Severe", "No Travel"]}
    weighted_score = 0.0
    weighted_miles = 0.0
    for cp, nxt in zip(checkpoints, checkpoints[1:] + [None]):
        seg = (nxt["miles_from_start"] - cp["miles_from_start"]) if nxt else 0.0
        if cp["risk"] in miles_by_risk:
            miles_by_risk[cp["risk"]] += seg
            weighted_score += SCORE[cp["risk"]] * seg
            weighted_miles += seg
    avg = round(weighted_score / weighted_miles, 3) if weighted_miles else None
    return {
        "index": index,
        "alternative_method": route.get("alternative_method", "osrm"),
        "distance_miles": round(route["distance_m"] / 1609.344, 2),
        "duration_seconds": round(route["duration_s"]),
        "duration_minutes": round(route["duration_s"] / 60),
        "geometry": route["geometry"],
        "checkpoints": checkpoints,
        "miles_by_risk": {k: round(v, 2) for k, v in miles_by_risk.items()},
        "severe_miles": round(miles_by_risk["Severe"], 2),
        "high_miles": round(miles_by_risk["High"], 2),
        "no_travel_miles": round(miles_by_risk["No Travel"], 2),
        "avg_risk": avg,
    }
