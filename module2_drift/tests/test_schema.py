"""
Module 2 Tests - Contract B Schema & GeoJSON Unit Tests
Validates live contracts and negative/adversarial schema violations.
"""

import os
import json
import unittest
from module2_drift.validate_schema import validate_drift_output


class TestContractSchema(unittest.TestCase):

    def setUp(self):
        sample_path = "contracts/sample_drift_output.json"
        if not os.path.exists(sample_path):
            sample_path = os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "sample_drift_output.json")
        with open(sample_path, "r", encoding="utf-8") as f:
            self.valid_data = json.load(f)

    def test_valid_sample_contract(self):
        is_valid, errors = validate_drift_output(self.valid_data)
        self.assertTrue(is_valid, f"Expected sample contract to pass validation: {errors}")

    def test_missing_top_level_key(self):
        bad_data = json.loads(json.dumps(self.valid_data))
        del bad_data["backtrack_track"]
        is_valid, errors = validate_drift_output(bad_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing required top-level key: 'backtrack_track'" in e for e in errors))

    def test_flipped_coordinates_detection(self):
        bad_data = json.loads(json.dumps(self.valid_data))
        bad_data["estimated_origin"]["point"] = [19.2849, 71.86696]  # [lat, lon]
        is_valid, errors = validate_drift_output(bad_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("FLIPPED as [lat, lon]" in e for e in errors))

    def test_invalid_utc_timestamp(self):
        bad_data = json.loads(json.dumps(self.valid_data))
        bad_data["estimated_origin"]["time_utc"] = "2026-09-04 12:00:00"  # No 'Z' or +00:00
        is_valid, errors = validate_drift_output(bad_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("must explicitly specify UTC zone" in e for e in errors))

    def test_empty_forecast_polygons_invalid(self):
        """forecast_polygons must contain at least 1 entry."""
        bad_data = json.loads(json.dumps(self.valid_data))
        bad_data["forecast_polygons"] = []
        is_valid, errors = validate_drift_output(bad_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("at least 1 entry" in e for e in errors))

    def test_non_default_forecast_hours_accepted(self):
        """Validator should accept any valid hours, not just {6, 24}."""
        custom_data = json.loads(json.dumps(self.valid_data))
        custom_data["forecast_polygons"][0]["hours_ahead"] = 12
        custom_data["forecast_polygons"][1]["hours_ahead"] = 48
        is_valid, errors = validate_drift_output(custom_data)
        # Should NOT fail because of hours — only structural issues matter now
        hour_errors = [e for e in errors if "6-hour and 24-hour" in e]
        self.assertEqual(hour_errors, [], f"Unexpected hour constraint errors: {hour_errors}")

    def test_unclosed_polygon_ring(self):
        bad_data = json.loads(json.dumps(self.valid_data))
        ring = bad_data["forecast_polygons"][0]["geometry"]["coordinates"][0]
        bad_data["forecast_polygons"][0]["geometry"]["coordinates"][0] = ring[:-1]  # Remove closing vertex
        is_valid, errors = validate_drift_output(bad_data)
        self.assertFalse(is_valid)
        self.assertTrue(any("is NOT closed" in e for e in errors))


if __name__ == '__main__':
    unittest.main()
