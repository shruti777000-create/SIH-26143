"""
Module 2 Tests - Bay of Bengal 3-Location Test Suite
Tests forecast_drift() across Central Offshore, Visakhapatnam Coastal, and Andaman Corridor.
"""

import unittest
from shapely.geometry import Point

from module2_drift.drift_model import forecast_drift
from module2_drift.validate_schema import validate_drift_output


def make_slick_geojson(slick_id: str, lon: float, lat: float, timestamp_utc: str, radius_deg: float = 0.015):
    pt = Point(lon, lat)
    poly = pt.buffer(radius_deg, resolution=8)
    return {
        "slick_id": slick_id,
        "timestamp_utc": timestamp_utc,
        "confidence": 0.94,
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(poly.exterior.coords)]
        }
    }


class TestBayOfBengalDrift(unittest.TestCase):

    def test_central_offshore(self):
        slick = make_slick_geojson("TEST-BOB-OFFSHORE-01", 88.50, 14.50, "2026-09-04T06:00:00Z", 0.020)
        res = forecast_drift(slick, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")

    def test_coastal_corridor(self):
        slick = make_slick_geojson("TEST-BOB-COASTAL-02", 83.45, 17.65, "2026-09-04T12:00:00Z", 0.015)
        res = forecast_drift(slick, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")

    def test_andaman_corridor(self):
        slick = make_slick_geojson("TEST-BOB-ANDAMAN-03", 91.80, 11.80, "2026-09-05T00:00:00Z", 0.018)
        res = forecast_drift(slick, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")


if __name__ == '__main__':
    unittest.main()
