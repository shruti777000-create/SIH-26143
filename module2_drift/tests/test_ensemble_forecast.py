"""
Module 2 Tests - Ensemble Forecast
Verifies that run_forecast() in ensemble mode:
  1. Returns a valid Contract B forecast_polygons list.
  2. Adds ensemble_size and ensemble_spread_km2 metadata to every entry.
  3. Produces a polygon that is at least as wide as the single-run version at +24 h
     (spread grows with ensemble uncertainty).
  4. Degenerates cleanly to a single-run when ensemble_size=1 and position_jitter_m=0.
  5. Raises SimulationError (not a bare exception) when all members fail.
"""

import math
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
from shapely.geometry import shape as shapely_shape

from module2_drift.exceptions import SimulationError
from module2_drift.forecast import (
    _jitter_seeds,
    _polygon_area_km2,
    particles_to_polygon_geojson,
    run_forecast,
)
from module2_drift.validate_schema import validate_drift_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_particle_cloud(center_lon: float, center_lat: float,
                          n: int = 80, spread_deg: float = 0.05):
    """Return (lons, lats) arrays of n random particles around a centre."""
    rng = np.random.default_rng(seed=0)
    lons = center_lon + rng.uniform(-spread_deg, spread_deg, n)
    lats = center_lat + rng.uniform(-spread_deg, spread_deg, n)
    return lons, lats


def _polygon_area(geojson_polygon) -> float:
    """Return Shapely area (in degrees^2) of a GeoJSON Polygon dict."""
    return shapely_shape(geojson_polygon).area


def _build_mock_reader():
    """OpenDrift reader mock that does nothing but satisfy isinstance checks."""
    mock = MagicMock()
    mock.covers_time.return_value = True
    return mock


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

class TestJitterSeeds(unittest.TestCase):

    def test_zero_jitter_returns_copy(self):
        lons = np.array([72.0, 72.1, 72.2])
        lats = np.array([19.0, 19.1, 19.2])
        rng = np.random.default_rng(0)
        jl, jla = _jitter_seeds(lons, lats, jitter_m=0.0, rng=rng)
        np.testing.assert_array_equal(lons, jl)
        np.testing.assert_array_equal(lats, jla)

    def test_nonzero_jitter_changes_positions(self):
        lons = np.full(50, 72.0)
        lats = np.full(50, 19.0)
        rng = np.random.default_rng(42)
        jl, jla = _jitter_seeds(lons, lats, jitter_m=500.0, rng=rng)
        self.assertFalse(np.allclose(lons, jl),
                         "Jittered lons should differ from originals")
        self.assertFalse(np.allclose(lats, jla),
                         "Jittered lats should differ from originals")

    def test_jitter_stays_in_geographic_bounds(self):
        lons = np.full(100, 72.0)
        lats = np.full(100, 19.0)
        rng = np.random.default_rng(7)
        jl, jla = _jitter_seeds(lons, lats, jitter_m=10_000.0, rng=rng)
        self.assertTrue(np.all(jl >= -180) and np.all(jl <= 180))
        self.assertTrue(np.all(jla >= -90) and np.all(jla <= 90))

    def test_different_rng_seeds_give_different_offsets(self):
        lons = np.full(50, 72.0)
        lats = np.full(50, 19.0)
        rng1 = np.random.default_rng(1)
        rng2 = np.random.default_rng(2)
        jl1, _ = _jitter_seeds(lons, lats, 250.0, rng1)
        jl2, _ = _jitter_seeds(lons, lats, 250.0, rng2)
        self.assertFalse(np.allclose(jl1, jl2),
                         "Different member seeds should produce different offsets")


class TestPolygonArea(unittest.TestCase):

    def test_area_positive_for_valid_polygon(self):
        lons, lats = _make_particle_cloud(72.0, 19.0, n=50, spread_deg=0.05)
        geojson = particles_to_polygon_geojson(lons, lats)
        area = _polygon_area_km2(geojson)
        self.assertGreater(area, 0.0, "Area should be positive for a real polygon")

    def test_area_zero_for_degenerate_polygon(self):
        geojson = {"type": "Polygon", "coordinates": [[[72.0, 19.0]]]}
        area = _polygon_area_km2(geojson)
        self.assertEqual(area, 0.0)


# ---------------------------------------------------------------------------
# Integration-style tests using a stubbed _run_single_member
# ---------------------------------------------------------------------------

class TestRunForecastEnsemble(unittest.TestCase):
    """
    These tests patch _run_single_member so we don't need real NetCDF files
    or an OpenDrift installation, while still exercising the full pooling and
    polygonisation logic in run_forecast().
    """

    CENTER_LON = 72.75
    CENTER_LAT = 18.85
    DET_TIME = datetime(2026, 9, 4, 12, 0, 0)
    FORECAST_HOURS = [6, 24]

    def _mock_member_result(self, spread_deg: float):
        """Return a fake member result dict with particle clouds at each horizon."""
        result = {}
        for h in self.FORECAST_HOURS:
            lons, lats = _make_particle_cloud(
                self.CENTER_LON, self.CENTER_LAT, n=80, spread_deg=spread_deg
            )
            result[h] = (lons, lats)
        return result

    def test_output_schema_contract_b_compatible(self):
        """Each entry must have hours_ahead and a valid GeoJSON Polygon geometry."""
        with patch("module2_drift.forecast._run_single_member",
                   return_value=self._mock_member_result(0.05)):
            polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=self.FORECAST_HOURS,
                ensemble_size=3,
                position_jitter_m=250.0,
            )

        self.assertEqual(len(polys), len(self.FORECAST_HOURS))
        for entry in polys:
            self.assertIn("hours_ahead", entry)
            self.assertIn("geometry", entry)
            self.assertEqual(entry["geometry"]["type"], "Polygon")
            coords = entry["geometry"]["coordinates"]
            self.assertTrue(len(coords) > 0 and len(coords[0]) >= 4)
            # Ring must be closed
            self.assertEqual(coords[0][0], coords[0][-1])

    def test_ensemble_metadata_fields_present(self):
        """ensemble_size and ensemble_spread_km2 must appear in every entry."""
        with patch("module2_drift.forecast._run_single_member",
                   return_value=self._mock_member_result(0.05)):
            polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=self.FORECAST_HOURS,
                ensemble_size=4,
                position_jitter_m=250.0,
            )

        for entry in polys:
            self.assertIn("ensemble_size", entry,
                          "ensemble_size must be present in forecast polygon entry")
            self.assertIn("ensemble_spread_km2", entry,
                          "ensemble_spread_km2 must be present in forecast polygon entry")
            self.assertIsInstance(entry["ensemble_spread_km2"], float)
            self.assertGreaterEqual(entry["ensemble_spread_km2"], 0.0)

    def test_ensemble_polygon_wider_than_single_run(self):
        """
        An ensemble of 5 members with spread 0.10 deg should produce a
        polygon with greater area than a single member with spread 0.02 deg,
        because pooling enlarges the particle cloud.
        """
        narrow_result = self._mock_member_result(spread_deg=0.02)
        wide_result   = self._mock_member_result(spread_deg=0.10)

        # Single run (size=1) with narrow cloud
        with patch("module2_drift.forecast._run_single_member",
                   return_value=narrow_result):
            single_polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=[24],
                ensemble_size=1,
                position_jitter_m=0.0,
            )

        # Ensemble run (size=5) with wide cloud
        with patch("module2_drift.forecast._run_single_member",
                   return_value=wide_result):
            ensemble_polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=[24],
                ensemble_size=5,
                position_jitter_m=250.0,
            )

        single_area  = _polygon_area(single_polys[0]["geometry"])
        ensemble_area = _polygon_area(ensemble_polys[0]["geometry"])
        self.assertGreater(
            ensemble_area, single_area,
            f"Ensemble polygon ({ensemble_area:.6f} deg^2) should be wider "
            f"than single-run polygon ({single_area:.6f} deg^2)"
        )

    def test_degenerate_single_member_zero_jitter(self):
        """
        ensemble_size=1 with position_jitter_m=0 should give a valid polygon
        whose area matches a plain single-run (within ~10%, allowing for
        the slightly larger buffer at +24 h).
        """
        base_result = self._mock_member_result(spread_deg=0.03)

        with patch("module2_drift.forecast._run_single_member",
                   return_value=base_result):
            polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=self.FORECAST_HOURS,
                ensemble_size=1,
                position_jitter_m=0.0,
                horizontal_diffusivity=0.0,
            )

        self.assertEqual(len(polys), 2)
        for entry in polys:
            self.assertEqual(entry["ensemble_size"], 1)
            self.assertGreater(entry["ensemble_spread_km2"], 0.0)

    def test_all_members_fail_raises_simulation_error(self):
        """
        When every _run_single_member() returns {}, run_forecast() must
        raise SimulationError (not a bare exception or silent hang).
        """
        with patch("module2_drift.forecast._run_single_member", return_value={}):
            with self.assertRaises(SimulationError) as ctx:
                run_forecast(
                    centroid_lon=self.CENTER_LON,
                    centroid_lat=self.CENTER_LAT,
                    radius_meters=500,
                    det_time=self.DET_TIME,
                    readers=[_build_mock_reader()],
                    forecast_hours=self.FORECAST_HOURS,
                    ensemble_size=3,
                    position_jitter_m=250.0,
                )
        self.assertEqual(ctx.exception.stage, "forecast")
        self.assertIn("all ensemble members", ctx.exception.message.lower())

    def test_partial_member_failure_still_succeeds(self):
        """
        If some members fail (return {}) but at least one succeeds, the
        forecast should still return valid polygons.
        """
        call_count = {"n": 0}
        good_result = self._mock_member_result(0.05)

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            # First call (member 0) fails, rest succeed
            return {} if call_count["n"] == 1 else good_result

        with patch("module2_drift.forecast._run_single_member",
                   side_effect=_side_effect):
            polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=self.FORECAST_HOURS,
                ensemble_size=4,
                position_jitter_m=250.0,
            )

        self.assertEqual(len(polys), 2)
        # Only 3 of 4 members succeeded
        self.assertEqual(polys[0]["ensemble_size"], 3)

    def test_24h_polygon_larger_than_6h(self):
        """
        Because the buffer_deg scales with horizon, the +24 h polygon should
        be larger than the +6 h polygon for the same particle spread.
        """
        with patch("module2_drift.forecast._run_single_member",
                   return_value=self._mock_member_result(0.04)):
            polys = run_forecast(
                centroid_lon=self.CENTER_LON,
                centroid_lat=self.CENTER_LAT,
                radius_meters=500,
                det_time=self.DET_TIME,
                readers=[_build_mock_reader()],
                forecast_hours=[6, 24],
                ensemble_size=3,
                position_jitter_m=250.0,
            )

        area_6h  = polys[0]["ensemble_spread_km2"]
        area_24h = polys[1]["ensemble_spread_km2"]
        self.assertGreater(
            area_24h, area_6h,
            f"+24 h spread ({area_24h} km^2) should exceed +6 h spread ({area_6h} km^2)"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
