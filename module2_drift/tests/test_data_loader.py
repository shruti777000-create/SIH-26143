"""
Module 2 Tests - Dynamic Data Loader Test Suite
Validates that load_environment_data(date, bbox=DEFAULT_BBOX):
  1. Auto-selects appropriate local NetCDF files matching requested date and bbox.
  2. Raises MetoceanDateOutOfRangeError detailing available date ranges when out of range.
  3. Raises MetoceanSpatialOutOfRangeError when bbox is outside local domain.
"""

import unittest
from datetime import datetime

from module2_drift.data_loader import (
    load_environment_data,
    discover_local_netcdf_catalog,
    DEFAULT_BBOX,
    DEFAULT_ARABIAN_SEA_BBOX,
    MetoceanDateOutOfRangeError,
    MetoceanSpatialOutOfRangeError
)
from module2_drift.drift_model import forecast_drift


class TestDynamicDataLoader(unittest.TestCase):

    def setUp(self):
        self.valid_date_str = "2026-09-04T12:00:00Z"
        self.valid_datetime = datetime(2026, 9, 4, 18, 0, 0)
        self.out_of_range_past = "2020-01-01T00:00:00Z"
        self.out_of_range_future = "2029-12-31T23:59:59Z"

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

    def test_catalog_discovery(self):
        catalog = discover_local_netcdf_catalog(["."])
        self.assertGreater(len(catalog), 0)
        file_types = {c["var_type"] for c in catalog}
        self.assertTrue("currents" in file_types or "both" in file_types)
        self.assertTrue("winds" in file_types or "both" in file_types)

    def test_load_environment_data_success_with_defaults(self):
        # Default bbox [71.0, 18.0, 73.5, 20.0]
        env = load_environment_data(self.valid_date_str)
        self.assertIn("readers", env)
        self.assertEqual(len(env["readers"]), 2)
        self.assertIn("current_reader", env)
        self.assertIn("wind_reader", env)
        self.assertIn("arabian_sea_currents.nc", env["current_file"])
        self.assertIn("arabian_sea_winds.nc", env["wind_file"])
        self.assertEqual(env["bbox"], DEFAULT_BBOX)

    def test_load_environment_data_with_datetime_object(self):
        env = load_environment_data(self.valid_datetime, bbox=[72.0, 18.5, 73.0, 19.5])
        self.assertIsNotNone(env["current_reader"])
        self.assertIsNotNone(env["wind_reader"])
        self.assertEqual(env["bbox"], [72.0, 18.5, 73.0, 19.5])

    def test_date_out_of_range_raises_clear_error(self):
        # Must raise MetoceanDateOutOfRangeError, NOT fail silently or crash
        with self.assertRaises(MetoceanDateOutOfRangeError) as ctx:
            load_environment_data(self.out_of_range_past)

        err_msg = str(ctx.exception)
        self.assertIn("Requested date", err_msg)
        self.assertIn("Available local dataset ranges", err_msg)
        # Verify the exception object retains structured information
        self.assertTrue(len(ctx.exception.available_ranges) > 0)
        first_range = ctx.exception.available_ranges[0]
        self.assertIn("filename", first_range)
        self.assertIn("start_str", first_range)
        self.assertIn("end_str", first_range)

    def test_spatial_out_of_range_raises_clear_error(self):
        # Request bounding box in Bay of Bengal outside Arabian Sea local data
        bob_bbox = [88.0, 14.0, 90.0, 16.0]
        with self.assertRaises(MetoceanSpatialOutOfRangeError) as ctx:
            load_environment_data(self.valid_date_str, bbox=bob_bbox)

        err_msg = str(ctx.exception)
        self.assertIn("Requested bounding box [88.0, 14.0, 90.0, 16.0] falls outside", err_msg)
        self.assertIn("Available local bounds", err_msg)

    def test_forecast_drift_auto_picks_local_files_and_handles_out_of_range(self):
        # 1. Valid date without passing NetCDF paths should succeed
        res_valid = forecast_drift(
            slick_polygon=self.valid_poly,
            timestamp="2026-09-04T12:00:00Z",
            num_particles=5,
            backtrack_hours=1,
            forecast_hours=[1]
        )
        self.assertFalse(res_valid.get("error", False))
        self.assertIn("estimated_origin", res_valid)
        self.assertIn("forecast_polygons", res_valid)

        # 2. Out-of-range date without passing NetCDF paths should return clean error
        res_out = forecast_drift(
            slick_polygon=self.valid_poly,
            timestamp=self.out_of_range_past
        )
        self.assertTrue(res_out.get("error"))
        self.assertEqual(res_out.get("error_type"), "TEMPORAL_OUT_OF_BOUNDS")
        self.assertIn("Available local dataset ranges", res_out.get("reason", ""))
        self.assertIn("available_ranges", res_out.get("details", {}))


if __name__ == "__main__":
    unittest.main()
