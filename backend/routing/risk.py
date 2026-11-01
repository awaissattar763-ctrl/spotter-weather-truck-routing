"""Weather-risk classification and route recommendation.

Implements EXACTLY the thresholds from the Spotter assessment PDF.

Wind (mph):        Low <25 | Moderate 25-34 | High 35-44 | Severe 45-54 | No Travel >=55
Rain (in/hr):      Low <0.10 | Moderate 0.10-0.25 | High 0.25-0.50 | Severe 0.50-1.00 | No Travel >1.00
Snow (in/hr):      Low <0.5 | Moderate 0.5-1.0 | High 1.0-2.0 | Severe 2.0-3.0 | No Travel >3.0

Boundary convention (the PDF's printed ranges overlap at the joints, e.g.
rain 0.25 appears in both Moderate and High): the LOWER band is exclusive at
its top edge, i.e. a value exactly on a joint belongs to the HIGHER band,
except the top of Severe, which is inclusive (rain 1.00 = Severe, snow 3.0 =
Severe, since No Travel starts strictly above). Wind joints are unambiguous
in the PDF (35 = High, 45 = Severe, 55 = No Travel) and are handled the same
way. This is documented here and in the README so the choice is visible.

Load rules (applied after the per-condition classification):
- wind >= 55 mph            -> No Travel for any load (already No Travel)
- wind 45-54 mph + load > 30,000 lb -> No Travel
- wind 35-44 mph + load > 40,000 lb -> Severe
Checkpoint risk = worst of (wind risk, rain risk, snow risk) after load rules.
"""

LEVELS = ["Low", "Moderate", "High", "Severe", "No Travel"]
SCORE = {level: i for i, level in enumerate(LEVELS)}
UNKNOWN = "Unknown"


def classify_wind(mph):
    if mph is None:
        return UNKNOWN
    if mph < 25:
        return "Low"
    if mph < 35:
        return "Moderate"
    if mph < 45:
        return "High"
    if mph < 55:
        return "Severe"
    return "No Travel"


def classify_rain(in_per_hr):
    if in_per_hr is None:
        return UNKNOWN
    if in_per_hr < 0.10:
        return "Low"
    if in_per_hr < 0.25:
        return "Moderate"
    if in_per_hr < 0.50:
        return "High"
    if in_per_hr <= 1.00:
        return "Severe"
    return "No Travel"


def classify_snow(in_per_hr):
    if in_per_hr is None:
        return UNKNOWN
    if in_per_hr < 0.5:
        return "Low"
    if in_per_hr < 1.0:
        return "Moderate"
    if in_per_hr < 2.0:
        return "High"
    if in_per_hr <= 3.0:
        return "Severe"
    return "No Travel"


def _worst(*levels):
    known = [lv for lv in levels if lv != UNKNOWN]
    if not known:
        return UNKNOWN
    return max(known, key=lambda lv: SCORE[lv])


def classify_checkpoint(wind_mph, rain_in_hr, snow_in_hr, load_weight_lb):
    """Return the checkpoint risk level after wind/rain/snow + load rules."""
    base = _worst(
        classify_wind(wind_mph),
        classify_rain(rain_in_hr),
        classify_snow(snow_in_hr),
    )
    if base == UNKNOWN:
        return UNKNOWN
    if wind_mph is not None and wind_mph >= 55:
        return "No Travel"
    if (
        wind_mph is not None
        and 45 <= wind_mph < 55
        and load_weight_lb is not None
        and load_weight_lb > 30000
    ):
        return "No Travel"
    if (
        wind_mph is not None
        and 35 <= wind_mph < 45
        and load_weight_lb is not None
        and load_weight_lb > 40000
    ):
        return _worst(base, "Severe")
    return base


def recommendation_order_key(route_summary):
    """Sort key implementing the PDF's exact priority order:
    (1) fewest Severe miles, (2) fewest High miles,
    (3) lowest average risk, (4) shortest travel time.
    Routes with unknown average risk sort after known ones on key (3).
    """
    avg = route_summary.get("avg_risk")
    avg_key = avg if avg is not None else 99.0
    return (
        route_summary.get("severe_miles", 0.0),
        route_summary.get("high_miles", 0.0),
        avg_key,
        route_summary.get("duration_seconds", 0.0),
    )


def recommend(routes):
    """routes: list of summary dicts (each with an 'index' key).
    Returns (recommended_index, reason_string)."""
    if not routes:
        return None, "No routes available."
    ordered = sorted(routes, key=recommendation_order_key)
    best = ordered[0]
    reason = (
        f"Route {best['index'] + 1} wins: {best['severe_miles']:.1f} Severe miles, "
        f"{best['high_miles']:.1f} High miles, average risk "
        f"{best['avg_risk'] if best['avg_risk'] is not None else 'unknown'}, "
        f"{best['duration_seconds'] / 60:.0f} min travel time — "
        "best on the priority order (Severe miles, then High miles, "
        "then average risk, then travel time)."
    )
    return best["index"], reason
