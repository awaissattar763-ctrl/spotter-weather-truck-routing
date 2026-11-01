"""Unit tests for risk classification and recommendation ordering.

Run: python manage.py test
No network access is used here; the live API is verified separately
with a real /api/plan/ call (see README).
"""

from django.test import TestCase

from .risk import (
    classify_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
    recommend,
)


class WindThresholdTests(TestCase):
    def test_boundaries(self):
        cases = [
            (0, "Low"), (24.9, "Low"),
            (25, "Moderate"), (34.9, "Moderate"),
            (35, "High"), (44.9, "High"),
            (45, "Severe"), (54.9, "Severe"),
            (55, "No Travel"), (80, "No Travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(classify_wind(value), expected)


class RainThresholdTests(TestCase):
    def test_boundaries(self):
        cases = [
            (0, "Low"), (0.09, "Low"),
            (0.10, "Moderate"), (0.24, "Moderate"),
            (0.25, "High"), (0.49, "High"),
            (0.50, "Severe"), (1.00, "Severe"),
            (1.01, "No Travel"), (2.5, "No Travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(classify_rain(value), expected)


class SnowThresholdTests(TestCase):
    def test_boundaries(self):
        cases = [
            (0, "Low"), (0.49, "Low"),
            (0.5, "Moderate"), (0.99, "Moderate"),
            (1.0, "High"), (1.99, "High"),
            (2.0, "Severe"), (3.0, "Severe"),
            (3.01, "No Travel"), (5.0, "No Travel"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(classify_snow(value), expected)


class CheckpointAndLoadRuleTests(TestCase):
    def test_worst_condition_wins(self):
        # High rain beats Moderate wind.
        self.assertEqual(classify_checkpoint(30, 0.30, 0, 10000), "High")
        # Severe snow beats High wind.
        self.assertEqual(classify_checkpoint(40, 0, 2.5, 10000), "Severe")

    def test_load_rule_no_travel_45_54_over_30000(self):
        self.assertEqual(classify_checkpoint(50, 0, 0, 30001), "No Travel")
        # Exactly 30,000 lb is NOT over the limit: stays Severe.
        self.assertEqual(classify_checkpoint(50, 0, 0, 30000), "Severe")

    def test_load_rule_severe_35_44_over_40000(self):
        self.assertEqual(classify_checkpoint(40, 0, 0, 40001), "Severe")
        # Exactly 40,000 lb is NOT over the limit: stays High.
        self.assertEqual(classify_checkpoint(40, 0, 0, 40000), "High")

    def test_load_rule_55_plus_always_no_travel(self):
        self.assertEqual(classify_checkpoint(60, 0, 0, 0), "No Travel")
        self.assertEqual(classify_checkpoint(55, 0, 0, 1000), "No Travel")

    def test_heavy_load_does_not_raise_calm_wind(self):
        self.assertEqual(classify_checkpoint(20, 0, 0, 50000), "Low")

    def test_missing_weather_is_unknown(self):
        self.assertEqual(classify_checkpoint(None, None, None, 20000), "Unknown")


class RecommendationTests(TestCase):
    def _route(self, index, severe, high, avg, duration):
        return {
            "index": index, "severe_miles": severe, "high_miles": high,
            "avg_risk": avg, "duration_seconds": duration,
        }

    def test_fewest_severe_miles_wins_first(self):
        routes = [
            self._route(0, 5, 0, 0.1, 1000),
            self._route(1, 0, 50, 2.0, 9999),
        ]
        idx, _ = recommend(routes)
        self.assertEqual(idx, 1)

    def test_high_miles_breaks_severe_tie(self):
        routes = [
            self._route(0, 2, 30, 0.1, 1000),
            self._route(1, 2, 10, 2.0, 9999),
        ]
        idx, _ = recommend(routes)
        self.assertEqual(idx, 1)

    def test_avg_risk_breaks_next_tie(self):
        routes = [
            self._route(0, 0, 10, 1.5, 1000),
            self._route(1, 0, 10, 0.5, 9999),
        ]
        idx, _ = recommend(routes)
        self.assertEqual(idx, 1)

    def test_duration_breaks_final_tie(self):
        routes = [
            self._route(0, 0, 0, 0.5, 5000),
            self._route(1, 0, 0, 0.5, 4000),
        ]
        idx, _ = recommend(routes)
        self.assertEqual(idx, 1)

    def test_reason_names_winner(self):
        idx, reason = recommend([self._route(0, 0, 0, 0.0, 3600)])
        self.assertEqual(idx, 0)
        self.assertIn("Route 1", reason)
