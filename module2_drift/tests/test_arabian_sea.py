"""
Module 2 Tests - Arabian Sea / Maharashtra Coast (3-Point Test Suite)
Tests forecast_drift() across Bombay High, Mumbai Harbour Entrance, and JNPT Approach.
"""

import os
import time
import unittest
from shapely.geometry import Point

from module2_drift.drift_model import forecast_drift
from module2_drift.data_loader import generate_arabian_sea_sample_netcdf
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


class TestArabianSeaDrift(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.curr_nc = "arabian_sea_currents.nc"
        cls.wind_nc = "arabian_sea_winds.nc"
        if not os.path.exists(cls.curr_nc) or not os.path.exists(cls.wind_nc):
            generate_arabian_sea_sample_netcdf(cls.curr_nc, cls.wind_nc)

    def test_bombay_high_offshore(self):
        slick = make_slick_geojson("TEST-AS-BOMBAY-HIGH-01", 71.50, 19.50, "2026-09-04T04:00:00Z", 0.020)
        res = forecast_drift(slick, self.curr_nc, self.wind_nc, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")

    def test_mumbai_harbour_entrance(self):
        slick = make_slick_geojson("TEST-AS-MUMBAI-ENTRANCE-02", 72.75, 18.85, "2026-09-04T10:00:00Z", 0.012)
        res = forecast_drift(slick, self.curr_nc, self.wind_nc, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")

    def test_jnpt_approach_channel(self):
        slick = make_slick_geojson("TEST-AS-JNPT-APPROACH-03", 72.90, 18.85, "2026-09-04T16:00:00Z", 0.008)
        res = forecast_drift(slick, self.curr_nc, self.wind_nc, backtrack_hours=12, forecast_hours=[6, 24], num_particles=60)
        is_valid, errors = validate_drift_output(res)
        self.assertTrue(is_valid, f"Schema validation failed: {errors}")


if __name__ == '__main__':
    unittest.main()
