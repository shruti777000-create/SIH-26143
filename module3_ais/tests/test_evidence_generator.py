"""
Module 3 Tests - Forensic Evidence Generator
Tests verifiable narrative generation, non-fabrication of metadata, and non-accusatory language.
"""

import unittest
import numpy as np
import pandas as pd

from module3_ais.config import AISConfig
from module3_ais.evidence_generator import generate_vessel_evidence_package


class TestEvidenceGenerator(unittest.TestCase):

    def setUp(self):
        self.config = AISConfig()

    def test_evidence_generated_from_actual_metrics(self):
        """Factual statements accurately reflect input distances, timestamps, and anomalies."""
        row = {
            "mmsi": 419001234,
            "vessel_name": "PACIFIC GLORY",
            "vessel_type": "Tanker",
            "threat_level": "HIGH",
            "composite_threat_score": 0.885,
            "min_distance_to_origin_km": 1.82,
            "time_difference_minutes": 5.0,
            "closest_point_time_utc": "2026-09-04T00:05:00Z",
            "cross_track_distance_km": 0.45,
            "trajectory_alignment_score": 0.92,
            "speed_change_max_knots": 9.5,  # sudden deceleration
            "stop_count": 2,                # loitering
            "max_heading_change_deg": 65.0, # sharp turn
            "is_behavioral_anomaly": True,
            "behavioral_anomaly_score": 0.82
        }

        evidence = generate_vessel_evidence_package(row, self.config)

        summary = evidence["summary"]
        self.assertIn("1.82 km", summary)
        self.assertIn("5.0 minutes", summary)
        self.assertIn("PACIFIC GLORY", summary)
        self.assertIn("419001234", summary)
        self.assertIn("HIGH", summary)

        # Anomaly indicators list must include all 4 triggered anomalies
        indicators = evidence["anomaly_indicators"]
        self.assertTrue(any("speed reduction" in ind.lower() for ind in indicators))
        self.assertTrue(any("loitering" in ind.lower() for ind in indicators))
        self.assertTrue(any("course alteration" in ind.lower() for ind in indicators))
        self.assertTrue(any("anomalous by isolation forest" in ind.lower() for ind in indicators))

    def test_no_fabrication_when_metadata_is_missing(self):
        """Does not invent vessel names, types, IMOs, or flags when missing/null."""
        row = {
            "mmsi": 419999000,
            "vessel_name": None,      # missing
            "vessel_type": np.nan,    # missing
            "threat_level": "LOW",
            "composite_threat_score": 0.250,
            "min_distance_to_origin_km": 35.0,
            "time_difference_minutes": 320.0,
            "cross_track_distance_km": 28.0,
            "trajectory_alignment_score": 0.35,
            "speed_change_max_knots": 0.5,
            "stop_count": 0,
            "max_heading_change_deg": 3.0,
            "is_behavioral_anomaly": False,
            "behavioral_anomaly_score": 0.20
        }

        evidence = generate_vessel_evidence_package(row, self.config)

        # Vessel metadata must remain None
        meta = evidence["vessel_metadata"]
        self.assertIsNone(meta["vessel_name"])
        self.assertIsNone(meta["vessel_type"])

        # Summary refers cleanly to MMSI without placeholder garbage
        self.assertIn("Candidate vessel MMSI 419999000", evidence["summary"])
        self.assertNotIn("UNKNOWN", evidence["summary"])
        self.assertNotIn("None", evidence["summary"])

        # No false anomaly indicators generated for normal vessel
        self.assertEqual(len(evidence["anomaly_indicators"]), 0)

    def test_non_accusatory_legal_language(self):
        """Verifies language uses 'potential suspect' or 'candidate vessel', never 'guilty' or 'responsible'."""
        row = {
            "mmsi": 419001001,
            "threat_level": "HIGH",
            "composite_threat_score": 0.95,
            "min_distance_to_origin_km": 0.2,
            "time_difference_minutes": 0.0,
        }
        evidence = generate_vessel_evidence_package(row, self.config)
        summary_lower = evidence["summary"].lower()

        # Forbidden accusatory terms
        forbidden = ["guilty", "perpetrator", "culprit", "proven responsible", "lawbreaker", "criminal"]
        for word in forbidden:
            self.assertNotIn(word, summary_lower)

        # Expected objective terms
        self.assertTrue(
            "potential suspect" in summary_lower or "candidate vessel" in summary_lower
        )

    def test_recommended_action_varies_by_threat_level(self):
        """Recommended enforcement action differs between HIGH, MEDIUM, and LOW threat tiers."""
        row_high = {"mmsi": 1, "threat_level": "HIGH", "composite_threat_score": 0.85}
        row_med = {"mmsi": 2, "threat_level": "MEDIUM", "composite_threat_score": 0.55}
        row_low = {"mmsi": 3, "threat_level": "LOW", "composite_threat_score": 0.20}

        ev_high = generate_vessel_evidence_package(row_high, self.config)
        ev_med = generate_vessel_evidence_package(row_med, self.config)
        ev_low = generate_vessel_evidence_package(row_low, self.config)

        self.assertIn("inspection", ev_high["recommended_action"].lower())
        self.assertIn("review", ev_med["recommended_action"].lower())
        self.assertIn("situational awareness", ev_low["recommended_action"].lower())


if __name__ == '__main__':
    unittest.main()
