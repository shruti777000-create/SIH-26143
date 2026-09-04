"""
Module 3 Tests - Edge Cases and Robustness
Tests edge cases and boundary conditions for the vessel attribution pipeline:
- zero AIS records
- one vessel
- two vessels
- vessel with one AIS point
- duplicate AIS points
- missing MMSI
- invalid coordinates
- invalid timestamps
- negative speed
- vessel outside 50 km
- vessel outside ±12 hours
- missing optional vessel name
- missing optional vessel type
- missing numeric features
- all vessels behaving similarly (zero variance)
- multiple vessels with identical scores (tie handling)
"""

import io
import unittest
import pandas as pd
import numpy as np

from module3_ais.config import AISConfig, DEFAULT_CONFIG
from module3_ais.preprocessor import (
    load_ais_data,
    clean_ais_data,
    filter_by_spatiotemporal,
)
from module3_ais.features import extract_all_vessel_features
from module3_ais.anomaly_model import AISAnomalyDetector, BEHAVIORAL_FEATURE_COLUMNS
from module3_ais.attribution_engine import (
    VesselAttributionEngine,
    compute_composite_threat_score,
)
from module3_ais.validate_schema import validate_contract_c


class TestMember3EdgeCases(unittest.TestCase):

    def setUp(self):
        self.config = AISConfig()
        self.origin_point = [72.8000, 18.9000]  # [lon, lat] off Mumbai
        self.origin_time = "2026-09-04T12:00:00Z"
        self.backtrack_coords = [
            [72.7000, 18.8500],
            [72.7500, 18.8750],
            [72.8000, 18.9000]
        ]
        self.contract_b_dummy = {
            "slick_id": "TEST-EDGE-001",
            "estimated_origin": {
                "point": self.origin_point,
                "time_utc": self.origin_time
            },
            "backtrack_track": {
                "type": "LineString",
                "coordinates": self.backtrack_coords
            }
        }

    def test_edge_zero_ais_records(self):
        """Zero AIS records handled safely without crashing."""
        empty_df = pd.DataFrame(columns=["timestamp", "mmsi", "latitude", "longitude", "sog", "cog"])
        cleaned = clean_ais_data(empty_df, self.config)
        self.assertEqual(len(cleaned), 0)

        # Anomaly detector with empty features
        detector = AISAnomalyDetector()
        scores, flags = detector.score(pd.DataFrame(columns=BEHAVIORAL_FEATURE_COLUMNS))
        self.assertEqual(len(scores), 0)
        self.assertEqual(len(flags), 0)

    def test_edge_one_vessel_population(self):
        """Pipeline safely executes when exactly one candidate vessel is present."""
        df_one = pd.DataFrame([
            {
                "timestamp": "2026-09-04T12:10:00Z",
                "mmsi": 419111111,
                "latitude": 18.9050,
                "longitude": 72.8050,
                "sog": 10.5,
                "cog": 45.0,
                "vessel_name": "SINGLE RUNNER",
                "vessel_type": "Tanker"
            },
            {
                "timestamp": "2026-09-04T12:20:00Z",
                "mmsi": 419111111,
                "latitude": 18.9100,
                "longitude": 72.8100,
                "sog": 10.6,
                "cog": 45.0,
                "vessel_name": "SINGLE RUNNER",
                "vessel_type": "Tanker"
            }
        ])
        engine = VesselAttributionEngine(self.config)
        output = engine.attribute_spill(self.contract_b_dummy, df_one)

        self.assertEqual(output["suspect_summary"]["total_vessels_evaluated"], 1)
        self.assertEqual(len(output["ranked_suspects"]), 1)
        suspect = output["ranked_suspects"][0]
        self.assertEqual(suspect["rank"], 1)
        self.assertEqual(suspect["mmsi"], 419111111)
        self.assertTrue(0.0 <= suspect["composite_threat_score"] <= 1.0)
        is_valid, errors = validate_contract_c(output)
        self.assertTrue(is_valid, f"Contract C validation failed: {errors}")

    def test_edge_two_vessels_population(self):
        """Pipeline safely executes when exactly two candidate vessels are present."""
        df_two = pd.DataFrame([
            {
                "timestamp": "2026-09-04T12:10:00Z",
                "mmsi": 419111111,
                "latitude": 18.9050,
                "longitude": 72.8050,
                "sog": 10.5,
                "cog": 45.0
            },
            {
                "timestamp": "2026-09-04T12:20:00Z",
                "mmsi": 419111111,
                "latitude": 18.9100,
                "longitude": 72.8100,
                "sog": 10.6,
                "cog": 45.0
            },
            {
                "timestamp": "2026-09-04T12:15:00Z",
                "mmsi": 419222222,
                "latitude": 18.9200,
                "longitude": 72.8200,
                "sog": 14.0,
                "cog": 90.0
            },
            {
                "timestamp": "2026-09-04T12:25:00Z",
                "mmsi": 419222222,
                "latitude": 18.9200,
                "longitude": 72.8300,
                "sog": 14.2,
                "cog": 90.0
            }
        ])
        engine = VesselAttributionEngine(self.config)
        output = engine.attribute_spill(self.contract_b_dummy, df_two)

        self.assertEqual(output["suspect_summary"]["total_vessels_evaluated"], 2)
        self.assertEqual(len(output["ranked_suspects"]), 2)
        ranks = [s["rank"] for s in output["ranked_suspects"]]
        self.assertEqual(ranks, [1, 2])
        self.assertGreaterEqual(
            output["ranked_suspects"][0]["composite_threat_score"],
            output["ranked_suspects"][1]["composite_threat_score"]
        )

    def test_edge_vessel_with_one_ais_point(self):
        """Vessel with only 1 observation handled gracefully without trajectory crash."""
        df_one_pt = pd.DataFrame([{
            "timestamp": "2026-09-04T12:10:00Z",
            "mmsi": 419333333,
            "latitude": 18.9020,
            "longitude": 72.8020,
            "sog": 8.0,
            "cog": 180.0
        }])
        clean_df = clean_ais_data(df_one_pt, self.config)
        features = extract_all_vessel_features(
            clean_df,
            self.origin_point,
            self.origin_time,
            self.backtrack_coords
        )
        self.assertEqual(len(features), 1)
        row = features.iloc[0]
        self.assertEqual(row["total_track_distance_km"], 0.0)
        self.assertEqual(row["speed_std"], 0.0)
        self.assertEqual(row["avg_heading_change_deg"], 0.0)

    def test_edge_duplicate_ais_points(self):
        """Duplicate rows with identical (MMSI, timestamp) are de-duplicated."""
        df_dups = pd.DataFrame([
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419444444, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419444444, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:10:00Z", "mmsi": 419444444, "latitude": 18.91, "longitude": 72.81, "sog": 6.0, "cog": 90.0},
        ])
        cleaned = clean_ais_data(df_dups, self.config)
        self.assertEqual(len(cleaned), 2)

    def test_edge_missing_and_invalid_mmsi(self):
        """Missing, null, or zero MMSIs are dropped."""
        df_bad_mmsi = pd.DataFrame([
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": None, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:05:00Z", "mmsi": 0, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:10:00Z", "mmsi": -123, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:15:00Z", "mmsi": 419555555, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
        ])
        cleaned = clean_ais_data(df_bad_mmsi, self.config)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(int(cleaned.iloc[0]["mmsi"]), 419555555)

    def test_edge_invalid_coordinates(self):
        """Coordinates outside physical bounds are dropped."""
        df_bad_coords = pd.DataFrame([
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419666666, "latitude": 95.0, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:05:00Z", "mmsi": 419666666, "latitude": -91.0, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:10:00Z", "mmsi": 419666666, "latitude": 18.90, "longitude": 185.0, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:15:00Z", "mmsi": 419666666, "latitude": 18.90, "longitude": -190.0, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:20:00Z", "mmsi": 419666666, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
        ])
        cleaned = clean_ais_data(df_bad_coords, self.config)
        self.assertEqual(len(cleaned), 1)

    def test_edge_invalid_timestamps(self):
        """Unparseable timestamps become NaT and are dropped."""
        df_bad_ts = pd.DataFrame([
            {"timestamp": "invalid-datetime-string", "mmsi": 419777777, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": None, "mmsi": 419777777, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419777777, "latitude": 18.90, "longitude": 72.80, "sog": 5.0, "cog": 90.0},
        ])
        cleaned = clean_ais_data(df_bad_ts, self.config)
        self.assertEqual(len(cleaned), 1)

    def test_edge_negative_speed(self):
        """Negative SOG values are dropped."""
        df_bad_sog = pd.DataFrame([
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419888888, "latitude": 18.90, "longitude": 72.80, "sog": -1.5, "cog": 90.0},
            {"timestamp": "2026-09-04T12:05:00Z", "mmsi": 419888888, "latitude": 18.90, "longitude": 72.80, "sog": 8.0, "cog": 90.0},
        ])
        cleaned = clean_ais_data(df_bad_sog, self.config)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["sog"], 8.0)

    def test_edge_vessel_outside_50km_radius(self):
        """Vessels situated further than 50 km from origin are excluded by spatial filter."""
        # Origin is lat 18.9000, lon 72.8000. 1 degree lat is ~111 km. Lat 20.0 is > 120 km away.
        df_far = pd.DataFrame([{
            "timestamp": "2026-09-04T12:00:00Z",
            "mmsi": 419000001,
            "latitude": 20.0000,
            "longitude": 72.8000,
            "sog": 10.0,
            "cog": 90.0
        }])
        clean_df = clean_ais_data(df_far, self.config)
        filtered = filter_by_spatiotemporal(
            clean_df,
            origin_point=self.origin_point,
            origin_time_utc=self.origin_time,
            spatial_radius_km=50.0,
            temporal_window_hours=12.0
        )
        self.assertEqual(len(filtered), 0)

    def test_edge_vessel_outside_12_hours_window(self):
        """Observations more than 12 hours from estimated origin time are excluded."""
        # 14 hours after origin time
        df_late = pd.DataFrame([{
            "timestamp": "2026-09-05T02:00:00Z",
            "mmsi": 419000002,
            "latitude": 18.9010,
            "longitude": 72.8010,
            "sog": 10.0,
            "cog": 90.0
        }])
        clean_df = clean_ais_data(df_late, self.config)
        filtered = filter_by_spatiotemporal(
            clean_df,
            origin_point=self.origin_point,
            origin_time_utc=self.origin_time,
            spatial_radius_km=50.0,
            temporal_window_hours=12.0
        )
        self.assertEqual(len(filtered), 0)

    def test_edge_missing_optional_vessel_name_and_type(self):
        """Missing optional metadata does not cause NaN strings or fabricated values."""
        df_no_meta = pd.DataFrame([
            {
                "timestamp": "2026-09-04T12:05:00Z",
                "mmsi": 419000003,
                "latitude": 18.9020,
                "longitude": 72.8020,
                "sog": 10.0,
                "cog": 90.0,
                "vessel_name": None,
                "vessel_type": np.nan
            },
            {
                "timestamp": "2026-09-04T12:15:00Z",
                "mmsi": 419000003,
                "latitude": 18.9030,
                "longitude": 72.8030,
                "sog": 10.0,
                "cog": 90.0,
                "vessel_name": "",
                "vessel_type": "UNKNOWN"
            }
        ])
        engine = VesselAttributionEngine(self.config)
        output = engine.attribute_spill(self.contract_b_dummy, df_no_meta)

        suspect = output["ranked_suspects"][0]
        self.assertIsNone(suspect["vessel_name"])
        self.assertIsNone(suspect["vessel_type"])
        self.assertNotIn("None", suspect["evidence_package"]["summary"])
        self.assertNotIn("UNKNOWN", suspect["evidence_package"]["summary"])

    def test_edge_all_vessels_behaving_similarly_zero_variance(self):
        """Isolation forest handles uniform/zero-variance fleets without NaN crashes."""
        uniform_records = []
        for i in range(8):
            uniform_records.append({
                "mmsi": 419000010 + i,
                "avg_speed_knots": 10.0,
                "max_speed_knots": 10.0,
                "speed_std": 0.0,
                "stop_count": 0,
                "avg_heading_change_deg": 0.0,
                "max_heading_change_deg": 0.0,
                "total_track_distance_km": 10.0,
                "ais_observation_count": 5,
                "speed_change_avg_knots": 0.0,
                "speed_change_max_knots": 0.0,
            })
        df_uniform = pd.DataFrame(uniform_records)
        detector = AISAnomalyDetector(random_state=42)
        detector.fit(df_uniform)
        scores, flags = detector.score(df_uniform)

        self.assertEqual(len(scores), 8)
        self.assertFalse(np.isnan(scores).any(), "Scores must not be NaN under zero variance.")
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())

    def test_edge_multiple_vessels_with_identical_composite_scores(self):
        """Vessels with identical scores are ordered deterministically and assigned unique ranks."""
        engine = VesselAttributionEngine(self.config)
        # 3 vessels with identical pings and timing
        df_twins = pd.DataFrame([
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419000101, "latitude": 18.905, "longitude": 72.805, "sog": 10.0, "cog": 45.0},
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419000102, "latitude": 18.905, "longitude": 72.805, "sog": 10.0, "cog": 45.0},
            {"timestamp": "2026-09-04T12:00:00Z", "mmsi": 419000103, "latitude": 18.905, "longitude": 72.805, "sog": 10.0, "cog": 45.0},
        ])
        output = engine.attribute_spill(self.contract_b_dummy, df_twins)

        suspects = output["ranked_suspects"]
        self.assertEqual(len(suspects), 3)
        ranks = [s["rank"] for s in suspects]
        self.assertEqual(ranks, [1, 2, 3], "Ranks must be strictly contiguous integers [1, 2, 3].")
        # All three composite scores are identical
        self.assertEqual(suspects[0]["composite_threat_score"], suspects[1]["composite_threat_score"])
        self.assertEqual(suspects[1]["composite_threat_score"], suspects[2]["composite_threat_score"])


if __name__ == '__main__':
    unittest.main()
