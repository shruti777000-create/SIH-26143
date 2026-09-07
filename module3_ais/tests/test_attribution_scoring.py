"""
Module 3 Tests - Multi-Criteria Attribution Scoring & Ranking
Tests proximity, temporal, trajectory, composite scores, weight validation,
threat tiers, ranking, and Contract C validation.
"""

import os
import json
import unittest
import numpy as np
import pandas as pd

from module3_ais.config import AISConfig, DEFAULT_CONFIG
from module3_ais.attribution_engine import (
    compute_proximity_score,
    compute_temporal_score,
    compute_trajectory_score,
    compute_composite_threat_score,
    classify_threat_level,
    VesselAttributionEngine,
)
from module3_ais.validate_schema import validate_contract_c


class TestAttributionScoring(unittest.TestCase):

    def setUp(self):
        self.config = AISConfig()
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.sample_contract_b = os.path.join(self.base_dir, "..", "..", "contracts", "sample_drift_output.json")
        self.synthetic_csv = os.path.join(self.base_dir, "..", "data", "synthetic_ais.csv")

    # -------------------------------------------------------------------------
    # 1. Proximity Scoring Tests
    # -------------------------------------------------------------------------
    def test_proximity_score_decreases_with_distance(self):
        """Proximity score is 1.0 at origin and strictly decreases as distance increases."""
        s0 = compute_proximity_score(0.0, self.config)
        s5 = compute_proximity_score(5.0, self.config)
        s15 = compute_proximity_score(15.0, self.config)
        s30 = compute_proximity_score(30.0, self.config)
        s50 = compute_proximity_score(50.0, self.config)

        self.assertAlmostEqual(s0, 1.0, places=3)
        self.assertGreater(s0, s5)
        self.assertGreater(s5, s15)
        self.assertGreater(s15, s30)
        self.assertGreater(s30, s50)
        self.assertGreaterEqual(s50, 0.0)

    def test_proximity_score_linear_mode(self):
        """Linear proximity decay cleanly reaches 0.0 at spatial radius cutoff."""
        cfg = AISConfig(proximity_decay_mode="linear", spatial_radius_km=50.0)
        self.assertAlmostEqual(compute_proximity_score(0.0, cfg), 1.0, places=3)
        self.assertAlmostEqual(compute_proximity_score(25.0, cfg), 0.5, places=3)
        self.assertAlmostEqual(compute_proximity_score(50.0, cfg), 0.0, places=3)
        self.assertAlmostEqual(compute_proximity_score(60.0, cfg), 0.0, places=3)

    # -------------------------------------------------------------------------
    # 2. Temporal Scoring Tests
    # -------------------------------------------------------------------------
    def test_temporal_score_highest_at_zero(self):
        """Temporal score is 1.0 at delta_t = 0 and decays symmetrically for +/- delta_t."""
        t0 = compute_temporal_score(0.0, self.config)
        t_plus_30 = compute_temporal_score(30.0, self.config)
        t_minus_30 = compute_temporal_score(-30.0, self.config)
        t_plus_180 = compute_temporal_score(180.0, self.config)

        self.assertAlmostEqual(t0, 1.0, places=3)
        self.assertAlmostEqual(t_plus_30, t_minus_30, places=4, msg="Temporal scoring must be symmetric.")
        self.assertGreater(t0, t_plus_30)
        self.assertGreater(t_plus_30, t_plus_180)

    # -------------------------------------------------------------------------
    # 3. Trajectory Scoring Tests
    # -------------------------------------------------------------------------
    def test_trajectory_scoring(self):
        """Combines alignment and cross-track distance without confusing with origin proximity."""
        # Best case: perfect alignment (1.0) and on-centerline (0 km XTD)
        best = compute_trajectory_score(1.0, 0.0, self.config)
        self.assertAlmostEqual(best, 1.0, places=3)

        # Worst case: opposing alignment (0.0) and outside corridor (>= 25 km XTD)
        worst = compute_trajectory_score(0.0, 30.0, self.config)
        self.assertAlmostEqual(worst, 0.0, places=3)

        # Intermediate case: good alignment (0.9) but off-centerline (10 km XTD)
        mid = compute_trajectory_score(0.9, 10.0, self.config)
        self.assertGreater(mid, 0.4)
        self.assertLess(mid, 0.9)

    # -------------------------------------------------------------------------
    # 4. Weight Validation & Composite Scoring Tests
    # -------------------------------------------------------------------------
    def test_weight_validation_success(self):
        """Default weights (0.40, 0.25, 0.20, 0.15) sum to 1.0 and pass validation."""
        self.config.validate_weights()

    def test_weight_validation_failure(self):
        """Invalid weights that do not sum to 1.0 raise ValueError."""
        bad_cfg = AISConfig(
            weight_proximity=0.50,
            weight_temporal=0.50,
            weight_trajectory=0.50,
            weight_anomaly=0.50
        )
        with self.assertRaises(ValueError):
            bad_cfg.validate_weights()

    def test_composite_threat_score_calculation(self):
        """Composite score correctly weights the 4 sub-scores into [0.0, 1.0]."""
        # (0.40 * 1.0) + (0.25 * 1.0) + (0.20 * 1.0) + (0.15 * 1.0) = 1.0
        max_score = compute_composite_threat_score(1.0, 1.0, 1.0, 1.0, self.config)
        self.assertAlmostEqual(max_score, 1.0, places=4)

        # (0.40 * 0.0) + (0.25 * 0.0) + (0.20 * 0.0) + (0.15 * 0.0) = 0.0
        min_score = compute_composite_threat_score(0.0, 0.0, 0.0, 0.0, self.config)
        self.assertAlmostEqual(min_score, 0.0, places=4)

        # Intermediate: (0.40*0.8) + (0.25*0.6) + (0.20*0.5) + (0.15*0.4) = 0.32 + 0.15 + 0.10 + 0.06 = 0.63
        score = compute_composite_threat_score(0.8, 0.6, 0.5, 0.4, self.config)
        self.assertAlmostEqual(score, 0.63, places=2)

    # -------------------------------------------------------------------------
    # 5. Threat Level Classification Tests
    # -------------------------------------------------------------------------
    def test_classify_threat_level(self):
        """Properly categorizes threat scores into HIGH, MEDIUM, and LOW tiers."""
        self.assertEqual(classify_threat_level(0.85, self.config), "HIGH")
        self.assertEqual(classify_threat_level(0.70, self.config), "HIGH")
        self.assertEqual(classify_threat_level(0.69, self.config), "MEDIUM")
        self.assertEqual(classify_threat_level(0.40, self.config), "MEDIUM")
        self.assertEqual(classify_threat_level(0.39, self.config), "LOW")
        self.assertEqual(classify_threat_level(0.05, self.config), "LOW")

    # -------------------------------------------------------------------------
    # 6. End-to-End Ranking and Contract C Schema Validation
    # -------------------------------------------------------------------------
    def test_full_pipeline_ranking_and_contract_c(self):
        """End-to-end attribution generates valid Contract C with descending rank order."""
        if not os.path.exists(self.sample_contract_b):
            self.skipTest("Sample Contract B file not found.")

        with open(self.sample_contract_b, "r", encoding="utf-8") as f:
            contract_b = json.load(f)

        engine = VesselAttributionEngine(self.config)
        contract_c = engine.attribute_spill(
            contract_b=contract_b,
            ais_source=self.synthetic_csv,
            attribution_timestamp_utc="2026-09-04T12:00:00Z"
        )

        # 1. Strict Contract C Schema validation
        is_valid, errors = validate_contract_c(contract_c)
        self.assertTrue(is_valid, f"Contract C validation failed: {errors}")

        # 2. Ranking check: candidate list must be non-empty and strictly sorted descending
        suspects = contract_c["ranked_suspects"]
        self.assertGreaterEqual(len(suspects), 2)

        prev_score = 1.01
        for idx, s in enumerate(suspects, start=1):
            self.assertEqual(s["rank"], idx, "Rank index must start from 1 and be contiguous.")
            self.assertLessEqual(s["composite_threat_score"], prev_score, "Suspects must be sorted descending.")
            prev_score = s["composite_threat_score"]

            # Coordinate check: vessel_point_at_cpa must be [lon, lat]
            pt = s["closest_encounter"]["vessel_point_at_cpa"]
            self.assertEqual(len(pt), 2)
            self.assertGreater(pt[0], 50.0, "Longitude must be first in [lon, lat] coordinate.")
            self.assertLess(pt[1], 35.0, "Latitude must be second in [lon, lat] coordinate.")


if __name__ == '__main__':
    unittest.main()
