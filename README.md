# Weather-Aware Truck Routing — Spotter Coding Assessment

A React + Django web app that helps a truck driver choose the safest route
based on weather, load weight, and travel time.

> Built locally only. Nothing in this repo has been submitted to Spotter,
> pushed to GitHub, hosted, or recorded. Those are separate steps for the
> applicant to decide.

## What it does

The user enters origin, destination, departure date/time, and load weight
(lb), and picks a weather-sampling interval (every 10, 25, or 50 miles).
The app then:

1. Geocodes both places (Nominatim) and fetches up to 3 route options
   (OSRM public demo server — see "3 routes" note below).
2. Samples weather at each checkpoint along every route (Open-Meteo
   hourly forecast: wind speed, precipitation, snowfall), using the
   truck's **estimated arrival time** at that checkpoint (departure time
   + cumulative travel time at the route's average speed).
3. Classifies each checkpoint's risk with the assessment's exact rules
   (below) and applies the load rules.
4. Recommends the best route in the assessment's exact priority order:
   fewest Severe miles → fewest High miles → lowest average risk →
   shortest travel time.
5. Shows all routes on a Leaflet map (OpenStreetMap tiles) with
   risk-colored corridor segments, checkpoint markers (ETA + weather +
   risk on click), and route summary cards.
6. A **0–48 hour forecast slider** shifts the trip start time and
   recomputes checkpoint risks for the shifted start, so the driver can
   see how leaving later changes the weather risk.

## Run locally

Backend (Django, port 8000):

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py runserver 127.0.0.1:8000
```

Frontend (React + Vite, port 5173; proxies `/api` to the backend):

```bash
cd frontend
npm install
npm run dev        # dev server at http://localhost:5173
npm run build      # production build (verified clean)
```

To serve the built frontend against a backend on another host, set
`VITE_API_BASE` at build time, e.g. `VITE_API_BASE=http://localhost:8000
npm run build`.

## API contract

`GET /api/health/` → `{"status": "ok"}`

`POST /api/plan/` — request:

```json
{
  "origin": "Dallas, TX",
  "destination": "Houston, TX",
  "departure": "2026-11-02T08:00:00-06:00",
  "load_weight_lb": 35000,
  "interval_miles": 25,
  "time_shift_hours": 0
}
```

`interval_miles` must be 10, 25, or 50; `time_shift_hours` is optional,
0–48. Response: origin/destination geocoding, `effective_departure`
(departure + shift), `routes[]` — each with `distance_miles`,
`duration_minutes`, `geometry` ([lon, lat] pairs),
`checkpoints[]` (`lat`, `lon`, `miles_from_start`, `eta`, `wind_mph`,
`rain_in_hr`, `snow_in_hr`, `risk`), `miles_by_risk`, `severe_miles`,
`high_miles`, `no_travel_miles`, `avg_risk` (distance-weighted mean
risk score, Low=0 … No Travel=4), plus `recommended_route_index`,
`recommendation_reason`, `route_count`, and `note` (if any).

## Risk rules (exactly as specified)

| Condition  | Low     | Moderate   | High      | Severe    | No Travel |
|------------|---------|------------|-----------|-----------|-----------|
| Wind mph   | <25     | 25–34      | 35–44     | 45–54     | ≥55       |
| Rain in/hr | <0.10   | 0.10–0.25  | 0.25–0.50 | 0.50–1.00 | >1.00     |
| Snow in/hr | <0.5    | 0.5–1.0    | 1.0–2.0   | 2.0–3.0   | >3.0      |

Load rules: wind ≥55 mph → No Travel for any load; wind 45–54 mph with
load >30,000 lb → No Travel; wind 35–44 mph with load >40,000 lb →
Severe. Checkpoint risk = worst of wind/rain/snow risk after load rules.

Boundary note: the printed ranges overlap at the joints (e.g. rain 0.25
is listed under both Moderate and High). This build resolves joints to
the higher band (rain 0.25 = High, 0.50 = Severe), except the top of
Severe, which is inclusive (rain 1.00 = Severe, snow 3.0 = Severe, since
No Travel starts strictly above). See `backend/routing/risk.py`.

## Honest notes on data sources and limits

- **3 routes:** the OSRM public demo server commonly returns only 1–2
  alternatives per corridor (Dallas→Houston returns 1). To still offer 3
  genuinely routed options, the backend tops up with OSRM routes via
  lateral waypoints (±25/50 miles from the main route's midpoint).
  Those routes are labelled `alternative_method: "via_waypoint"` in the
  API (and "via detour" in the UI); their geometry, distance, and
  duration all come from OSRM. If even that yields fewer than 3, the
  response says so in `note` — no route is ever invented.
- **Weather horizon:** Open-Meteo forecasts extend ~16 days. A departure
  beyond that range yields checkpoints with null weather and risk
  `"Unknown"`, excluded from averages — never guessed values.
- **ETAs:** checkpoint ETAs assume the route's average speed (total
  distance ÷ total duration); real traffic and stops are not modelled.
- **OSRM demo server:** shared, rate-limited, and not for production;
  a routing failure returns an HTTP 502 with a clear error instead of
  a fake route.
- **Heatmap:** the "weather heatmap along the trip corridor" is drawn
  as risk-colored translucent corridor segments plus checkpoint
  markers; it is not a raster heat layer.
- **No database models:** the Django app is API-only (SQLite default
  config, unused); no user data is stored.
- **Tests:** `backend/routing/tests.py` covers every risk threshold
  (including boundary values), all three load rules, and the full
  recommendation priority order — 14 tests, all passing. The live
  `/api/plan/` response was verified against real OSRM/Open-Meteo data
  (see "Verification" in the delivery report).

## Layout

```
spotter-assessment/
├── README.md
├── backend/                 # Django project + routing app
│   ├── manage.py
│   ├── requirements.txt     # Django==5.1.4, requests==2.32.3
│   ├── spotter/             # project settings/urls, minimal CORS middleware
│   └── routing/             # risk.py (rules), services.py (OSRM/Nominatim/
│                            #   Open-Meteo), views.py (/api/plan/), tests.py
└── frontend/                # React + Vite + Leaflet
    ├── src/App.jsx          # form, route cards, map, forecast slider
    ├── src/App.css
    └── vite.config.js       # dev proxy /api -> localhost:8000
```
