"""
Module 3 Tests - Trajectory Reconstruction and Feature Engineering
SIH Problem Statement 26143 - Phase 2 Test Suite
"""

import os
import json
import unittest
import math
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from module3_ais.trajectory import (
    build_vessel_trajectories,
    trajectory_to_geojson_feature,
    trajectories_to_feature_collection,
)
from module3_ais.features import (
    initial_bearing_deg,
    angular_difference_deg,
    compute_heading_changes_deg,
    point_to_segment_distance_km,
    point_to_backtrack_distance_km,
    interpolate_backtrack_timestamps,
    compute_trajectory_distance_km,
    compute_alignment_score,
    extract_vessel_features,
    extract_all_vessel_features,
    extract_features_from_contract_b,
)
from module3_ais.preprocessor import haversine_distance_km


class TestVesselFeaturesAndTrajectory(unittest.TestCase):

    def setUp(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.contract_b_path = os.path.join(self.base_dir, "..", "..", "contracts", "sample_drift_output.json")

    # -------------------------------------------------------------------------
    # 1. Heading Wraparound Tests (359° -> 1° = 2°)
    # -------------------------------------------------------------------------
    def test_heading_wraparound_scalar(self):
        """359° to 1° must be a 2° angular difference, NOT 358°."""
        diff1 = angular_difference_deg(359.0, 1.0)
        diff2 = angular_difference_deg(1.0, 359.0)
        self.assertAlmostEqual(diff1, 2.0, places=4)
        self.assertAlmostEqual(diff2, 2.0, places=4)

        # Standard non-wrapped cases
        self.assertAlmostEqual(angular_difference_deg(10.0, 25.0), 15.0, places=4)
        self.assertAlmostEqual(angular_difference_deg(350.0, 10.0), 20.0, places=4)
        self.assertAlmostEqual(angular_difference_deg(180.0, 0.0), 180.0, places=4)

    def test_heading_wraparound_vectorized(self):
        """Vectorized consecutive heading change handles multiple wraparounds."""
        cogs = pd.Series([359.0, 1.0, 358.0, 2.0])
        changes = compute_heading_changes_deg(cogs)
        # Expected: 359->1 (2°), 1->358 (3°), 358->2 (4°)
        expected = np.array([2.0, 3.0, 4.0])
        np.testing.assert_allclose(changes, expected, atol=1e-4)

    # -------------------------------------------------------------------------
    # 2. Straight-Line Vessel Trajectory Tests
    # -------------------------------------------------------------------------
    def test_straight_line_vessel_trajectory(self):
        """Vessel moving in a straight easterly line along constant latitude."""
        df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-04T00:00:00Z"),
                pd.Timestamp("2026-09-04T00:30:00Z"),
                pd.Timestamp("2026-09-04T01:00:00Z"),
            ],
            "mmsi": [419111001] * 3,
            "latitude": [19.0, 19.0, 19.0],
            "longitude": [72.0, 72.1, 72.2],
            "sog": [10.0, 10.0, 10.0],
            "cog": [90.0, 90.0, 90.0],
            "vessel_name": ["STRAIGHT LINER"] * 3
        })

        origin_pt = [72.1, 19.05]  # [lon, lat]
        origin_t = "2026-09-04T00:30:00Z"

        feat = extract_vessel_features(df, origin_point=origin_pt, origin_time_utc=origin_t)

        self.assertEqual(feat["mmsi"], 419111001)
        self.assertEqual(feat["ais_observation_count"], 3)
        self.assertAlmostEqual(feat["avg_heading_change_deg"], 0.0, places=2)
        self.assertAlmostEqual(feat["max_heading_change_deg"], 0.0, places=2)
        self.assertAlmostEqual(feat["speed_std"], 0.0, places=2)
        self.assertEqual(feat["stop_count"], 0)

        # Distance should be sum of 72.0->72.1 and 72.1->72.2 at lat 19
        expected_dist = (
            haversine_distance_km(19.0, 72.0, 19.0, 72.1) +
            haversine_distance_km(19.0, 72.1, 19.0, 72.2)
        )
        self.assertAlmostEqual(feat["total_track_distance_km"], expected_dist, places=2)

        # GeoJSON LineString check
        geojson = trajectory_to_geojson_feature(df)
        coords = geojson["geometry"]["coordinates"]
        self.assertEqual(len(coords), 3)
        # Verify strict [lon, lat] ordering
        self.assertEqual(coords[0], [72.0, 19.0])
        self.assertEqual(coords[1], [72.1, 19.0])
        self.assertEqual(coords[2], [72.2, 19.0])

    # -------------------------------------------------------------------------
    # 3. Speed Change & Total Distance Calculations
    # -------------------------------------------------------------------------
    def test_speed_change_calculations(self):
        """Tests acceleration/speed change statistics."""
        df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-04T00:00:00Z"),
                pd.Timestamp("2026-09-04T00:15:00Z"),
                pd.Timestamp("2026-09-04T00:30:00Z"),
            ],
            "mmsi": [419222002] * 3,
            "latitude": [19.28, 19.29, 19.30],
            "longitude": [71.86, 71.87, 71.88],
            "sog": [12.0, 15.0, 8.0],  # changes: |15-12|=3, |8-15|=7 -> avg=5, max=7
            "cog": [45.0, 45.0, 45.0]
        })
        feat = extract_vessel_features(df, origin_point=[71.86, 19.28], origin_time_utc="2026-09-04T00:00:00Z")

        self.assertAlmostEqual(feat["avg_speed_knots"], (12 + 15 + 8) / 3, places=2)
        self.assertAlmostEqual(feat["max_speed_knots"], 15.0, places=2)
        self.assertAlmostEqual(feat["speed_change_avg_knots"], 5.0, places=2)
        self.assertAlmostEqual(feat["speed_change_max_knots"], 7.0, places=2)
        self.assertGreater(feat["speed_std"], 0.0)

    # -------------------------------------------------------------------------
    # 4. Closest Point, Minimum Distance & Time Difference
    # -------------------------------------------------------------------------
    def test_closest_point_and_time_difference(self):
        """Verifies CPA minimum distance, timestamp, and time difference."""
        df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-04T00:00:00Z"),
                pd.Timestamp("2026-09-04T00:20:00Z"),  # closest point
                pd.Timestamp("2026-09-04T00:40:00Z"),
            ],
            "mmsi": [419333003] * 3,
            "latitude": [19.20, 19.2849, 19.35],
            "longitude": [71.80, 71.86696, 71.95],
            "sog": [10.0, 10.0, 10.0],
            "cog": [45.0, 45.0, 45.0]
        })
        origin_pt = [71.86696, 19.2849]  # exact match with point 2
        origin_t = "2026-09-04T00:00:00Z"

        feat = extract_vessel_features(df, origin_point=origin_pt, origin_time_utc=origin_t)

        self.assertAlmostEqual(feat["min_distance_to_origin_km"], 0.0, places=3)
        self.assertEqual(feat["closest_point_time_utc"], "2026-09-04T00:20:00+00:00")
        # 20 minutes after origin time
        self.assertAlmostEqual(feat["time_difference_minutes"], 20.0, places=2)

    # -------------------------------------------------------------------------
    # 5. Single-Point Vessel Trajectory (Edge Case)
    # -------------------------------------------------------------------------
    def test_one_point_vessel_trajectory(self):
        """Vessel with only 1 ping should not crash and return zeroed motion metrics."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-04T00:10:00Z")],
            "mmsi": [419444004],
            "latitude": [19.2849],
            "longitude": [71.86696],
            "sog": [5.0],
            "cog": [120.0],
            "vessel_name": ["LONE SHIP"]
        })
        origin_pt = [71.86696, 19.2849]
        origin_t = "2026-09-04T00:00:00Z"

        feat = extract_vessel_features(df, origin_point=origin_pt, origin_time_utc=origin_t)

        self.assertEqual(feat["mmsi"], 419444004)
        self.assertEqual(feat["ais_observation_count"], 1)
        self.assertAlmostEqual(feat["total_track_distance_km"], 0.0, places=3)
        self.assertAlmostEqual(feat["speed_std"], 0.0, places=3)
        self.assertAlmostEqual(feat["avg_heading_change_deg"], 0.0, places=3)
        self.assertAlmostEqual(feat["max_heading_change_deg"], 0.0, places=3)
        self.assertAlmostEqual(feat["time_difference_minutes"], 10.0, places=2)

        # GeoJSON single point format
        geojson = trajectory_to_geojson_feature(df)
        self.assertEqual(geojson["geometry"]["type"], "Point")
        self.assertEqual(geojson["geometry"]["coordinates"], [71.86696, 19.2849])
        self.assertTrue(geojson["properties"]["is_single_point"])

    # -------------------------------------------------------------------------
    # 6. Missing SOG and Missing COG Handling
    # -------------------------------------------------------------------------
    def test_missing_cog_and_sog(self):
        """Vessels with missing COG and SOG should be handled safely."""
        df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-04T00:00:00Z"),
                pd.Timestamp("2026-09-04T00:30:00Z")
            ],
            "mmsi": [419555005] * 2,
            "latitude": [19.20, 19.22],
            "longitude": [71.80, 71.82],
            "sog": [np.nan, np.nan],
            "cog": [np.nan, np.nan]
        })
        feat = extract_vessel_features(df, origin_point=[71.80, 19.20], origin_time_utc="2026-09-04T00:00:00Z")

        self.assertEqual(feat["avg_speed_knots"], 0.0)
        self.assertEqual(feat["max_speed_knots"], 0.0)
        self.assertEqual(feat["speed_std"], 0.0)
        self.assertEqual(feat["avg_heading_change_deg"], 0.0)
        self.assertEqual(feat["max_heading_change_deg"], 0.0)
        self.assertGreater(feat["total_track_distance_km"], 0.0)

    # -------------------------------------------------------------------------
    # 7. Backtrack Corridor & Cross-Track Distance Tests
    # -------------------------------------------------------------------------
    def test_point_to_segment_cross_track(self):
        """Tests spherical perpendicular distance to a line segment."""
        # Equator segment from (0, 72.0) to (0, 73.0)
        # Point P at (1.0, 72.5) -> exactly 1 degree North of midpoint
        dist = point_to_segment_distance_km(
            lat_p=1.0, lon_p=72.5,
            lat_a=0.0, lon_a=72.0,
            lat_b=0.0, lon_b=73.0
        )
        expected_1_deg_lat_km = 1.0 * (math.pi / 180.0) * 6371.0088
        self.assertAlmostEqual(dist, expected_1_deg_lat_km, delta=1.0)

        # Point P before segment start: projection falls at A
        dist_before = point_to_segment_distance_km(
            lat_p=0.0, lon_p=71.0,
            lat_a=0.0, lon_a=72.0,
            lat_b=0.0, lon_b=73.0
        )
        self.assertAlmostEqual(dist_before, haversine_distance_km(0.0, 71.0, 0.0, 72.0), places=3)

    def test_backtrack_interpolation_requirement(self):
        """
        Tests requirement 3: linear interpolation of waypoint times
        between origin_time_utc and detection_timestamp without inventing timestamps.
        """
        backtrack_coords = [
            [71.86696, 19.2849],  # Origin
            [72.1054, 19.1234],   # Midpoint
            [72.82, 18.95]        # Detection
        ]
        t_origin = "2026-09-04T00:00:00Z"
        t_det = "2026-09-04T12:00:00Z"

        interpolated = interpolate_backtrack_timestamps(backtrack_coords, t_origin, t_det)

        self.assertEqual(len(interpolated), 3)
        # Waypoint 0 must equal origin time
        self.assertEqual(interpolated[0][2], pd.Timestamp("2026-09-04T00:00:00Z"))
        # Waypoint 1 (fraction 1/2) must equal +6h
        self.assertEqual(interpolated[1][2], pd.Timestamp("2026-09-04T06:00:00Z"))
        # Waypoint 2 (fraction 2/2) must equal detection time (+12h)
        self.assertEqual(interpolated[2][2], pd.Timestamp("2026-09-04T12:00:00Z"))

    # -------------------------------------------------------------------------
    # 8. Trajectory Alignment Score Tests
    # -------------------------------------------------------------------------
    def test_trajectory_alignment_score(self):
        """Tests directional correlation between vessel track and backtrack line."""
        # Backtrack corridor going East: (19.0, 72.0) -> (19.0, 73.0) [Bearing ~90°]
        backtrack_coords = [[72.0, 19.0], [73.0, 19.0]]  # [lon, lat]

        # 1. Vessel also traveling East: (19.1, 72.0) -> (19.1, 73.0) -> Alignment should be ~1.0
        df_parallel = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-04T00:00:00Z"), pd.Timestamp("2026-09-04T01:00:00Z")],
            "mmsi": [1, 1],
            "latitude": [19.1, 19.1],
            "longitude": [72.0, 73.0],
            "sog": [10.0, 10.0],
            "cog": [90.0, 90.0]
        })
        score_parallel = compute_alignment_score(df_parallel, backtrack_coords)
        self.assertGreater(score_parallel, 0.95)

        # 2. Vessel traveling South (orthogonal): Bearing 180° vs 90° -> delta 90° -> Alignment ~0.5
        df_ortho = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-04T00:00:00Z"), pd.Timestamp("2026-09-04T01:00:00Z")],
            "mmsi": [2, 2],
            "latitude": [19.5, 18.5],
            "longitude": [72.5, 72.5],
            "sog": [10.0, 10.0],
            "cog": [180.0, 180.0]
        })
        score_ortho = compute_alignment_score(df_ortho, backtrack_coords)
        self.assertAlmostEqual(score_ortho, 0.5, delta=0.05)

        # 3. Vessel traveling West (opposing): Bearing 270° vs 90° -> delta 180° -> Alignment ~0.0
        df_opposing = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-04T00:00:00Z"), pd.Timestamp("2026-09-04T01:00:00Z")],
            "mmsi": [3, 3],
            "latitude": [19.1, 19.1],
            "longitude": [73.0, 72.0],
            "sog": [10.0, 10.0],
            "cog": [270.0, 270.0]
        })
        score_opposing = compute_alignment_score(df_opposing, backtrack_coords)
        self.assertLess(score_opposing, 0.05)

    # -------------------------------------------------------------------------
    # 9. End-to-End Extraction from Real Contract B Payload
    # -------------------------------------------------------------------------
    def test_extract_features_from_sample_contract_b(self):
        """Extracts features for all vessels in synthetic dataset using live sample Contract B."""
        if not os.path.exists(self.contract_b_path):
            self.skipTest("Sample Contract B file not found.")

        with open(self.contract_b_path, "r", encoding="utf-8") as f:
            contract_b = json.load(f)

        synthetic_csv = os.path.join(self.base_dir, "..", "data", "synthetic_ais.csv")
        from module3_ais.preprocessor import load_ais_data, clean_ais_data
        df_cleaned = clean_ais_data(load_ais_data(synthetic_csv))

        features_df = extract_features_from_contract_b(df_cleaned, contract_b)

        # Target columns check
        expected_cols = [
            "mmsi",
            "min_distance_to_origin_km",
            "avg_speed_knots",
            "max_speed_knots",
            "speed_std",
            "total_track_distance_km",
            "ais_observation_count",
            "stop_count",
            "avg_heading_change_deg",
            "max_heading_change_deg",
            "closest_point_time_utc",
            "time_difference_minutes",
            "cross_track_distance_km",
            "trajectory_alignment_score"
        ]
        for col in expected_cols:
            self.assertIn(col, features_df.columns, f"Missing target column: {col}")

        # Check suspect 419001001 (cruising near origin)
        s1 = features_df[features_df["mmsi"] == 419001001].iloc[0]
        self.assertLess(s1["min_distance_to_origin_km"], 2.0)
        self.assertLess(abs(s1["time_difference_minutes"]), 60.0)

        # Check suspect 419004004 (anomalous deceleration and turn near origin)
        s4 = features_df[features_df["mmsi"] == 419004004].iloc[0]
        self.assertLess(s4["min_distance_to_origin_km"], 1.5)
        self.assertGreater(s4["max_heading_change_deg"], 60.0)  # sharp heading change!
        self.assertGreater(s4["speed_change_max_knots"], 10.0)  # sudden deceleration!


if __name__ == '__main__':
    unittest.main()
