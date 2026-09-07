"""
Module 3 Tests - Preprocessor, Cleaning, Haversine, and Spatiotemporal Filtering
SIH Problem Statement 26143 - Phase 1 Test Suite
"""

import os
import json
import unittest
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from module3_ais.config import AISConfig, DEFAULT_CONFIG
from module3_ais.preprocessor import (
    haversine_distance_km,
    haversine_vectorized_km,
    load_ais_data,
    clean_ais_data,
    filter_by_spatiotemporal,
    filter_from_contract_b,
)
from module3_ais.trajectory import trajectory_to_geojson_feature, build_vessel_trajectories


class TestAISPreprocessor(unittest.TestCase):

    def setUp(self):
        # Locate sample synthetic dataset and sample Contract B
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.synthetic_csv = os.path.join(self.base_dir, "..", "data", "synthetic_ais.csv")
        self.contract_b_path = os.path.join(self.base_dir, "..", "..", "contracts", "sample_drift_output.json")

    # -------------------------------------------------------------------------
    # 1. Haversine Distance Tests
    # -------------------------------------------------------------------------
    def test_haversine_distance_zero(self):
        """Distance between identical coordinates should be 0.0."""
        dist = haversine_distance_km(19.2849, 71.86696, 19.2849, 71.86696)
        self.assertAlmostEqual(dist, 0.0, places=5)

    def test_haversine_distance_known(self):
        """
        Known great-circle distance test:
        Mumbai (18.922, 72.834) to JNPT (18.950, 72.950) is ~12.6 km.
        """
        dist = haversine_distance_km(18.922, 72.834, 18.950, 72.950)
        self.assertGreater(dist, 11.0)
        self.assertLess(dist, 14.0)

    def test_haversine_vectorized(self):
        """Vectorized Haversine should match scalar results element-wise."""
        lats = np.array([19.2849, 18.922, 17.500])
        lons = np.array([71.86696, 72.834, 70.200])
        target_lat, target_lon = 19.2849, 71.86696

        vec_dists = haversine_vectorized_km(lats, lons, target_lat, target_lon)

        self.assertEqual(len(vec_dists), 3)
        self.assertAlmostEqual(vec_dists[0], 0.0, places=4)
        scalar_dist_1 = haversine_distance_km(lats[1], lons[1], target_lat, target_lon)
        self.assertAlmostEqual(vec_dists[1], scalar_dist_1, places=3)

    # -------------------------------------------------------------------------
    # 2. AIS Loading Tests
    # -------------------------------------------------------------------------
    def test_ais_loading_success(self):
        """Loads synthetic CSV and normalizes column headers."""
        self.assertTrue(os.path.exists(self.synthetic_csv), f"Missing: {self.synthetic_csv}")
        df = load_ais_data(self.synthetic_csv)
        self.assertIsInstance(df, pd.DataFrame)
        for col in ["timestamp", "mmsi", "latitude", "longitude", "sog", "cog"]:
            self.assertIn(col, df.columns)

    def test_ais_loading_missing_mandatory_columns(self):
        """Raises ValueError if required column is absent."""
        bad_df = pd.DataFrame({
            "timestamp": ["2026-09-04T00:00:00Z"],
            "mmsi": [419001001],
            "latitude": [19.28]
            # missing longitude, sog, cog
        })
        with self.assertRaises(ValueError):
            load_ais_data(bad_df)

    # -------------------------------------------------------------------------
    # 3. Timestamp Normalization Tests
    # -------------------------------------------------------------------------
    def test_timestamp_normalization(self):
        """Ensures all timestamps become timezone-aware UTC datetime."""
        raw_data = pd.DataFrame({
            "timestamp": [
                "2026-09-04T00:00:00Z",
                "2026-09-04 02:00:00+00:00",
                "2026-09-04 04:30:00",  # naive string assumes UTC when utc=True
            ],
            "mmsi": [419001001, 419001001, 419001001],
            "latitude": [19.0, 19.1, 19.2],
            "longitude": [72.0, 72.1, 72.2],
            "sog": [10.0, 10.0, 10.0],
            "cog": [90.0, 90.0, 90.0]
        })
        cleaned = clean_ais_data(raw_data)
        self.assertEqual(len(cleaned), 3)
        for ts in cleaned["timestamp"]:
            self.assertIsNotNone(ts.tzinfo)
            self.assertEqual(ts.tzinfo, timezone.utc)

    # -------------------------------------------------------------------------
    # 4. Data Cleaning & Invalid Record Removal Tests
    # -------------------------------------------------------------------------
    def test_invalid_coordinate_removal(self):
        """Records with latitude outside [-90, 90] or longitude outside [-180, 180] are removed."""
        dirty = pd.DataFrame({
            "timestamp": ["2026-09-04T00:00:00Z"] * 4,
            "mmsi": [100, 200, 300, 400],
            "latitude": [19.0, 95.5, -92.0, 19.0],      # Row 1, 2 invalid lat
            "longitude": [72.0, 72.0, 72.0, 195.0],     # Row 3 invalid lon
            "sog": [10.0] * 4,
            "cog": [0.0] * 4
        })
        cleaned = clean_ais_data(dirty)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["mmsi"], 100)

    def test_missing_mmsi_and_timestamp_removal(self):
        """Null or invalid MMSI (<=0) and null timestamps are dropped."""
        dirty = pd.DataFrame({
            "timestamp": ["2026-09-04T00:00:00Z", None, "2026-09-04T00:00:00Z", "2026-09-04T00:00:00Z"],
            "mmsi": [None, 200, -1, 400],
            "latitude": [19.0] * 4,
            "longitude": [72.0] * 4,
            "sog": [10.0] * 4,
            "cog": [0.0] * 4
        })
        cleaned = clean_ais_data(dirty)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["mmsi"], 400)

    def test_negative_sog_removal(self):
        """Records with SOG < 0 are dropped."""
        dirty = pd.DataFrame({
            "timestamp": ["2026-09-04T00:00:00Z"] * 3,
            "mmsi": [100, 200, 300],
            "latitude": [19.0] * 3,
            "longitude": [72.0] * 3,
            "sog": [12.5, -2.0, 0.0],  # -2.0 is invalid, 0.0 (moored/anchored) is valid
            "cog": [90.0] * 3
        })
        cleaned = clean_ais_data(dirty)
        self.assertEqual(len(cleaned), 2)
        self.assertListEqual(list(cleaned["mmsi"]), [100, 300])

    def test_duplicate_removal(self):
        """Duplicates on (MMSI, timestamp) are dropped."""
        duplicates = pd.DataFrame({
            "timestamp": ["2026-09-04T00:00:00Z", "2026-09-04T00:00:00Z", "2026-09-04T00:15:00Z"],
            "mmsi": [419001001, 419001001, 419001001],
            "latitude": [19.2840, 19.2840, 19.2870],
            "longitude": [71.8665, 71.8665, 71.8700],
            "sog": [11.7, 11.7, 11.8],
            "cog": [136.0, 136.0, 135.0]
        })
        cleaned = clean_ais_data(duplicates)
        self.assertEqual(len(cleaned), 2)

    # -------------------------------------------------------------------------
    # 5. Spatial and Temporal Filtering Tests
    # -------------------------------------------------------------------------
    def test_synthetic_dataset_cleaning_and_filtering(self):
        """Tests end-to-end cleaning and filtering on the provided synthetic dataset."""
        df_raw = load_ais_data(self.synthetic_csv)
        self.assertGreater(len(df_raw), 15)  # includes dirty records

        df_cleaned = clean_ais_data(df_raw)
        # All dirty rows (invalid lat, invalid lon, missing mmsi, missing timestamp, neg sog, duplicate) must be pruned
        dirty_mmsis = [419005005, 419006006, 419008008, 419009009]
        for bad_mmsi in dirty_mmsis:
            self.assertNotIn(bad_mmsi, df_cleaned["mmsi"].values)

        # Origin from Contract B: [lon=71.86696, lat=19.2849] at 2026-09-04T00:00:00Z
        origin_pt = [71.86696, 19.2849]
        origin_t = "2026-09-04T00:00:00Z"

        filtered = filter_by_spatiotemporal(
            df=df_cleaned,
            origin_point=origin_pt,
            origin_time_utc=origin_t,
            spatial_radius_km=50.0,
            temporal_window_hours=12.0
        )

        filtered_mmsis = set(filtered["mmsi"].unique())

        # MMSI 419001001 (Near, right time) -> MUST BE INCLUDED
        self.assertIn(419001001, filtered_mmsis)

        # MMSI 419004004 (Near, right time, anomalous) -> MUST BE INCLUDED
        self.assertIn(419004004, filtered_mmsis)

        # MMSI 419002002 (Far away > 150 km) -> MUST BE EXCLUDED by spatial filter
        self.assertNotIn(419002002, filtered_mmsis)

        # MMSI 419003003 (Wrong time > 36 hours prior) -> MUST BE EXCLUDED by temporal filter
        self.assertNotIn(419003003, filtered_mmsis)

        # Check that distance_to_origin_km was added and is <= 50 km
        self.assertTrue((filtered["distance_to_origin_km"] <= 50.0).all())

    def test_filter_from_contract_b_file(self):
        """Verifies direct ingestion of Contract B JSON file payload."""
        if not os.path.exists(self.contract_b_path):
            self.skipTest("Contract B sample file not found in repo.")

        with open(self.contract_b_path, "r", encoding="utf-8") as f:
            contract_b = json.load(f)

        df_cleaned = clean_ais_data(load_ais_data(self.synthetic_csv))
        res = filter_from_contract_b(df_cleaned, contract_b, spatial_radius_km=50.0, temporal_window_hours=12.0)

        self.assertFalse(res.empty)
        self.assertIn("distance_to_origin_km", res.columns)
        self.assertIn("time_diff_hours", res.columns)
        # Suspect 419001001 and 419004004 should be present
        self.assertIn(419001001, res["mmsi"].values)
        self.assertIn(419004004, res["mmsi"].values)

    # -------------------------------------------------------------------------
    # 6. Coordinate Rule Verification ([lon, lat] for GeoJSON / Contract C)
    # -------------------------------------------------------------------------
    def test_coordinate_rule_geojson(self):
        """
        Validates the strict coordinate rule:
        - Internal DataFrame has 'latitude' and 'longitude'
        - Generated GeoJSON coordinates MUST be [longitude, latitude]
        """
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-04T00:00:00Z"), pd.Timestamp("2026-09-04T00:15:00Z")],
            "mmsi": [419001001, 419001001],
            "latitude": [19.2840, 19.2870],
            "longitude": [71.8665, 71.8700],
            "sog": [11.7, 11.8],
            "cog": [136.0, 135.0],
            "vessel_name": ["MT OCEAN TRADER", "MT OCEAN TRADER"]
        })

        # Check internal columns
        self.assertIn("latitude", df.columns)
        self.assertIn("longitude", df.columns)

        trajectories = build_vessel_trajectories(df)
        vessel_df = trajectories[419001001]
        geojson_feat = trajectory_to_geojson_feature(vessel_df)

        coords = geojson_feat["geometry"]["coordinates"]
        self.assertEqual(len(coords), 2)

        # Coordinate must be [lon, lat] -> [71.8665, 19.284] NOT [19.284, 71.8665]
        first_pt = coords[0]
        self.assertAlmostEqual(first_pt[0], 71.8665, places=3)
        self.assertAlmostEqual(first_pt[1], 19.2840, places=3)

        # Check flipped coordinate violation
        self.assertGreater(first_pt[0], 50.0, "Longitude must be first coordinate (>50°E for India)")
        self.assertLess(first_pt[1], 35.0, "Latitude must be second coordinate (<35°N for India)")


if __name__ == '__main__':
    unittest.main()
