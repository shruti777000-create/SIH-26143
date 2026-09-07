"""
Module 2 Tests - Pipeline Error Handling Test Suite
Validates that invalid polygons, temporal out-of-bounds, spatial/land violations,
and simulation failures return clean, structured error responses without raw tracebacks.
"""

import unittest
from unittest.mock import patch

from module2_drift.drift_model import forecast_drift
from module2_drift.exceptions import SimulationError


class TestPipelineErrorHandling(unittest.TestCase):

    def setUp(self):
        self.curr_nc = "arabian_sea_currents.nc"
        self.wind_nc = "arabian_sea_winds.nc"
        self.valid_poly = {
            "type": "Polygon",
            "coordinates": [
                [
                    [72.748, 18.848],
                    [72.752, 18.848],
                    [72.752, 18.852],
                    [72.748, 18.852],
                    [72.748, 18.848]
                ]
            ]
        }

    def test_malformed_unclosed_polygon(self):
        bad_poly = {
            "type": "Polygon",
            "coordinates": [[[72.747, 18.847], [72.753, 18.847], [72.753, 18.853], [72.747, 18.853]]]
        }
        res = forecast_drift(bad_poly, "2026-09-04T12:00:00Z")
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "INVALID_POLYGON")
        self.assertIn("not closed", res.get("reason", "").lower())

    def test_malformed_self_intersecting_polygon(self):
        bowtie = {
            "type": "Polygon",
            "coordinates": [
                [[72.74, 18.84], [72.76, 18.86], [72.74, 18.86], [72.76, 18.84], [72.74, 18.84]]
            ]
        }
        res = forecast_drift(bowtie, "2026-09-04T12:00:00Z")
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "INVALID_POLYGON")
        self.assertIn("self-intersection", res.get("reason", "").lower())

    def test_flipped_lat_lon_coordinates(self):
        flipped = {
            "type": "Polygon",
            "coordinates": [
                [[18.85, 72.75], [18.86, 72.75], [18.86, 72.76], [18.85, 72.76], [18.85, 72.75]]
            ]
        }
        res = forecast_drift(flipped, "2026-09-04T12:00:00Z")
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "INVALID_POLYGON")
        self.assertIn("inverted", res.get("reason", "").lower())

    def test_temporal_out_of_bounds_past(self):
        res = forecast_drift(
            self.valid_poly,
            timestamp="2020-01-01T12:00:00Z",
            current_nc_path=self.curr_nc,
            wind_nc_path=self.wind_nc
        )
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "TEMPORAL_OUT_OF_BOUNDS")
        self.assertIn("outside available metocean dataset range", res.get("reason", ""))

    def test_spatial_out_of_bounds(self):
        bay_of_bengal_poly = {
            "type": "Polygon",
            "coordinates": [
                [[88.48, 15.18], [88.52, 15.18], [88.52, 15.22], [88.48, 15.22], [88.48, 15.18]]
            ]
        }
        res = forecast_drift(
            bay_of_bengal_poly,
            timestamp="2026-09-04T12:00:00Z",
            current_nc_path=self.curr_nc,
            wind_nc_path=self.wind_nc
        )
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "SPATIAL_OUT_OF_BOUNDS")
        self.assertIn("falls outside the dataset spatial coverage", res.get("reason", ""))

    def test_land_intersection(self):
        inland_maharashtra_poly = {
            "type": "Polygon",
            "coordinates": [
                [[73.18, 19.08], [73.22, 19.08], [73.22, 19.12], [73.18, 19.12], [73.18, 19.08]]
            ]
        }
        res = forecast_drift(
            inland_maharashtra_poly,
            timestamp="2026-09-04T12:00:00Z",
            current_nc_path=self.curr_nc,
            wind_nc_path=self.wind_nc
        )
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "LAND_INTERSECTION")
        self.assertIn("on land", res.get("reason", "").lower())

    def test_simulation_failure_coastal_boundary(self):
        with patch("module2_drift.drift_model.run_backtrack") as mock_back:
            mock_back.side_effect = SimulationError(
                stage="backtrack",
                message="All particles stranded on rocky coastline within 30 minutes of reverse advection.",
                details={"beached": 60}
            )
            res = forecast_drift(
                self.valid_poly,
                timestamp="2026-09-04T12:00:00Z",
                current_nc_path=self.curr_nc,
                wind_nc_path=self.wind_nc
            )
        self.assertTrue(res.get("error"))
        self.assertEqual(res.get("error_type"), "SIMULATION_FAILURE")
        self.assertIn("stranded on rocky coastline", res.get("reason", "").lower())


if __name__ == '__main__':
    unittest.main()
