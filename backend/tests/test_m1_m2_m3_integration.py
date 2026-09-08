"""
Phase 1D: Full End-to-End Integration Test
SIH Problem Statement 26143

Pipeline:
Synthetic Member 1 Contract A (backend/fixtures/demo_contract_a.json)
        |
        v
Real Member 2 OpenDrift Lagrangian Drift Model (module2_drift.drift_model.forecast_drift)
        |
        v
Real Contract B (module3_ais.schemas.ContractBInput)
        |
        v
Real Member 3 AIS Attribution Engine (module3_ais.attribution_engine.VesselAttributionEngine)
        |
        v
Real Contract C Intelligence Package (module3_ais.validate_schema.validate_contract_c)

IMPORTANT NOTICE:
- Member 1 input is synthetic demonstration data because trained U-Net .pth weights
  and raw Sentinel-1 SAR imagery are unavailable in the repository.
- Member 2 processing is 100% REAL physics-based OpenDrift Lagrangian particle tracking.
- Member 3 processing is 100% REAL spatio-temporal corridor extraction, anomaly scoring,
  and AIS vessel attribution.
- Zero mock objects or fake outputs are used.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import unittest
import pytest

# Member 1 components
from backend.demo_fixture import FIXTURE_PATH, load_demo_contract_a_from_file

# Member 2 real components
from module2_drift.api import ContractARequest
from module2_drift.drift_model import forecast_drift

# Member 3 real components
from module3_ais.schemas import ContractBInput
from module3_ais.config import DEFAULT_CONFIG
from module3_ais.attribution_engine import VesselAttributionEngine
from module3_ais.validate_schema import validate_contract_c


class TestFullM1M2M3Integration(unittest.TestCase):
    """
    End-to-end integration test validating that Member 1's Contract A fixture
    drives the real Member 2 drift model to produce real Contract B, which
    subsequently drives the real Member 3 attribution engine to produce real Contract C.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent.parent
        cls.synthetic_ais_path = str(cls.repo_root / "module3_ais" / "data" / "synthetic_ais.csv")
        assert os.path.exists(cls.synthetic_ais_path), f"AIS dataset not found: {cls.synthetic_ais_path}"

    def test_full_m1_m2_m3_pipeline(self):
        """
        Executes:
        Synthetic Contract A -> Real Member 2 -> Real Contract B -> Real Member 3 -> Real Contract C.
        """
        # -------------------------------------------------------------------
        # 1. MEMBER 1: Load and Validate Contract A Demo Fixture
        # -------------------------------------------------------------------
        self.assertTrue(FIXTURE_PATH.exists(), f"Demo Contract A fixture not found at {FIXTURE_PATH}")
        raw_contract_a = load_demo_contract_a_from_file(FIXTURE_PATH)

        self.assertIsInstance(raw_contract_a, dict)
        self.assertEqual(raw_contract_a.get("slick_id"), "DEMO-SLICK-001")
        self.assertEqual(raw_contract_a.get("timestamp_utc"), "2026-09-04T12:00:00Z")

        # Validate with Member 2 official schema
        contract_a_req = ContractARequest(**raw_contract_a)
        self.assertEqual(contract_a_req.slick_id, "DEMO-SLICK-001")
        self.assertEqual(contract_a_req.timestamp_utc, "2026-09-04T12:00:00Z")
        self.assertIsNotNone(contract_a_req.geometry)
        self.assertEqual(contract_a_req.geometry.type, "Polygon")

        # -------------------------------------------------------------------
        # 2. MEMBER 2: Execute REAL OpenDrift Drift Simulation
        # -------------------------------------------------------------------
        # Note: Seed mode 'centroid', 12h backtrack, +6h/+24h forward forecast
        real_contract_b = forecast_drift(
            slick_polygon=raw_contract_a,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=25,
        )

        self.assertIsInstance(real_contract_b, dict, "Member 2 must return a dict")
        self.assertNotIn(
            "error",
            real_contract_b,
            f"Member 2 drift model returned error: {real_contract_b.get('reason')}"
        )

        # -------------------------------------------------------------------
        # 3. Verify and Validate REAL Contract B
        # -------------------------------------------------------------------
        # Slick ID propagation
        self.assertIn("slick_id", real_contract_b)
        self.assertEqual(real_contract_b["slick_id"], "DEMO-SLICK-001")

        # Estimated Origin verification
        self.assertIn("estimated_origin", real_contract_b)
        origin = real_contract_b["estimated_origin"]
        self.assertIn("point", origin)
        self.assertIn("time_utc", origin)

        origin_pt = origin["point"]
        self.assertEqual(len(origin_pt), 2, "Origin point must be [lon, lat]")
        origin_lon, origin_lat = float(origin_pt[0]), float(origin_pt[1])
        self.assertTrue(70.0 <= origin_lon <= 73.0, f"Origin lon {origin_lon} out of Arabian Sea bounds")
        self.assertTrue(18.0 <= origin_lat <= 20.0, f"Origin lat {origin_lat} out of Arabian Sea bounds")

        origin_time_str = origin["time_utc"]
        self.assertTrue(
            origin_time_str.endswith("Z") or "+00:00" in origin_time_str,
            f"Origin time must be UTC ISO-8601: {origin_time_str}"
        )
        parsed_origin_time = datetime.fromisoformat(origin_time_str.replace("Z", "+00:00"))
        self.assertIsNotNone(parsed_origin_time)

        # Backtrack Track LineString verification
        self.assertIn("backtrack_track", real_contract_b)
        backtrack = real_contract_b["backtrack_track"]
        self.assertEqual(backtrack.get("type"), "LineString")
        bt_coords = backtrack.get("coordinates")
        self.assertIsInstance(bt_coords, list)
        self.assertGreaterEqual(len(bt_coords), 1, "Backtrack line must have >= 1 point")
        for pt in bt_coords:
            self.assertEqual(len(pt), 2)
            self.assertTrue(-180.0 <= pt[0] <= 180.0)
            self.assertTrue(-90.0 <= pt[1] <= 90.0)

        # Forward Forecast Polygons verification
        self.assertIn("forecast_polygons", real_contract_b)
        polygons = real_contract_b["forecast_polygons"]
        self.assertIsInstance(polygons, list)
        self.assertGreaterEqual(len(polygons), 1, "Forecast polygons must have >= 1 item")
        for poly_entry in polygons:
            self.assertIn("hours_ahead", poly_entry)
            self.assertIn("geometry", poly_entry)
            self.assertEqual(poly_entry["geometry"].get("type"), "Polygon")

        # Validate with Member 3 official input schema
        validated_contract_b = ContractBInput(**real_contract_b)
        self.assertEqual(validated_contract_b.slick_id, "DEMO-SLICK-001")
        self.assertEqual(validated_contract_b.estimated_origin.point, origin_pt)

        # -------------------------------------------------------------------
        # 4. MEMBER 3: Execute REAL AIS Attribution Engine
        # -------------------------------------------------------------------
        engine = VesselAttributionEngine(DEFAULT_CONFIG)
        real_contract_c = engine.attribute_spill(
            contract_b=real_contract_b,
            ais_source=self.synthetic_ais_path
        )

        self.assertIsInstance(real_contract_c, dict, "Member 3 must return a dict")

        # -------------------------------------------------------------------
        # 5. Verify and Validate REAL Contract C
        # -------------------------------------------------------------------
        # Validate with Member 3 official validator
        is_valid_c, errors_c = validate_contract_c(real_contract_c)
        self.assertTrue(is_valid_c, f"Contract C validation failed: {errors_c}")

        # Slick ID propagation from M1 -> M2 -> M3
        self.assertIn("slick_id", real_contract_c)
        self.assertEqual(real_contract_c["slick_id"], "DEMO-SLICK-001")

        # Ranked suspects verification
        self.assertIn("ranked_suspects", real_contract_c)
        suspects = real_contract_c["ranked_suspects"]
        self.assertIsInstance(suspects, list)
        self.assertGreater(len(suspects), 0, "Expected ranked suspects from synthetic AIS data")

        for suspect in suspects:
            # Identifier
            self.assertIn("mmsi", suspect)
            self.assertIsInstance(suspect["mmsi"], int)

            # Scores and Threat Level
            score = suspect.get("composite_threat_score")
            self.assertIsInstance(score, (int, float))
            self.assertTrue(0.0 <= score <= 1.0, f"Threat score {score} out of bounds [0, 1]")

            threat_level = suspect.get("threat_level")
            self.assertIn(threat_level, ["HIGH", "MEDIUM", "LOW"])

            # Closest Encounter
            self.assertIn("closest_encounter", suspect)
            cpa = suspect["closest_encounter"]
            self.assertIn("min_distance_to_origin_km", cpa)
            self.assertIn("closest_point_time_utc", cpa)
            self.assertIn("vessel_point_at_cpa", cpa)
            self.assertGreaterEqual(cpa["min_distance_to_origin_km"], 0.0)

            # Trajectory GeoJSON
            self.assertIn("trajectory_geojson", suspect)
            traj = suspect["trajectory_geojson"]
            self.assertIsInstance(traj, dict)
            self.assertIn("type", traj)
            if traj.get("type") == "Feature":
                self.assertIn("geometry", traj)
                self.assertIn("coordinates", traj["geometry"])
            else:
                self.assertIn("coordinates", traj)

            # Score Breakdown
            self.assertIn("score_breakdown", suspect)
            self.assertIn("spatial_proximity_score", suspect["score_breakdown"])

            # Evidence Package
            self.assertIn("evidence_package", suspect)
            evidence = suspect["evidence_package"]
            self.assertIn("summary", evidence)
            self.assertIn("factual_observations", evidence)
            self.assertIn("recommended_action", evidence)

        # -------------------------------------------------------------------
        # 6. Pipeline Integrity Confirmation
        # -------------------------------------------------------------------
        # Verify that the pipeline passed data forward without mutation of slick_id
        self.assertEqual(raw_contract_a["slick_id"], real_contract_b["slick_id"])
        self.assertEqual(real_contract_b["slick_id"], real_contract_c["slick_id"])


if __name__ == "__main__":
    unittest.main()
