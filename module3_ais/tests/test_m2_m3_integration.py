"""
Phase 5A Integration Test: Member 2 (Drift Model) -> Member 3 (AIS Attribution)
SIH Problem Statement 26143

Tests the end-to-end Python interface pipeline:
Contract A / Member 2 fixture
       |
module2_drift.drift_model.forecast_drift()
       |
REAL Contract B
       |
Member 3 ContractBInput schema validation
       |
Member 3 VesselAttributionEngine
       |
Contract C intelligence output
"""

import os
from datetime import datetime
import unittest

from module3_ais.schemas import ContractBInput
from module3_ais.config import DEFAULT_CONFIG
from module3_ais.attribution_engine import VesselAttributionEngine
from module3_ais.validate_schema import validate_contract_c

# Import Member 2 real entrypoint - do NOT replace with fake implementation
try:
    from module2_drift.drift_model import forecast_drift
    M2_IMPORT_ERROR = None
except ImportError as err:
    forecast_drift = None
    M2_IMPORT_ERROR = err


class TestMember2ToMember3Integration(unittest.TestCase):
    """
    Phase 5A Integration Test verifying that REAL Member 2 Contract B output
    can be consumed directly by the REAL Member 3 attribution engine.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.abspath(__file__))
        cls.synthetic_ais_path = os.path.join(cls.base_dir, "..", "data", "synthetic_ais.csv")

        # Smallest deterministic Member 2 Contract A detection fixture (Bombay High / Arabian Sea corridor)
        cls.contract_a_fixture = {
            "slick_id": "SLICK-INTEG-M2-M3-001",
            "timestamp_utc": "2026-09-04T12:00:00Z",
            "confidence": 0.95,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [71.850, 19.270],
                    [71.870, 19.270],
                    [71.870, 19.290],
                    [71.850, 19.290],
                    [71.850, 19.270]
                ]]
            }
        }

    def test_real_m2_to_m3_pipeline(self):
        """
        Executes REAL Member 2 forecast_drift() -> REAL Contract B -> Member 3 Attribution -> Contract C.
        """
        # Requirement 7: If Member 2 dependencies are missing, report exact blocker; do NOT mock or silently skip.
        if M2_IMPORT_ERROR is not None:
            self.fail(
                f"Member 2 (module2_drift.drift_model.forecast_drift) cannot be executed due to missing environment dependency: "
                f"{type(M2_IMPORT_ERROR).__name__}: {str(M2_IMPORT_ERROR)}. "
                f"Missing geospatial/OpenDrift libraries (e.g., shapely, opendrift, xarray, netCDF4). "
                f"Per Phase 5A rules: DO NOT mock Member 2, DO NOT silently skip, report environment blocker."
            )

        # 1. Execute REAL Member 2 simulation with smallest deterministic parameters
        real_contract_b = forecast_drift(
            slick_polygon=self.contract_a_fixture,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=15,
        )

        # 2. Verify Member 2 actually returns a dictionary
        self.assertIsInstance(real_contract_b, dict, "Member 2 must return a dictionary payload")
        self.assertNotIn(
            "error",
            real_contract_b,
            f"Member 2 simulation returned an error: {real_contract_b.get('reason')}"
        )

        # 3. Verify slick_id
        self.assertIn("slick_id", real_contract_b, "Contract B must contain 'slick_id'")
        self.assertEqual(real_contract_b["slick_id"], self.contract_a_fixture["slick_id"])

        # 4. Verify estimated_origin structure and coordinates
        self.assertIn("estimated_origin", real_contract_b, "Contract B must contain 'estimated_origin'")
        est_origin = real_contract_b["estimated_origin"]
        self.assertIsInstance(est_origin, dict)
        self.assertIn("point", est_origin)
        self.assertIn("time_utc", est_origin)

        # Verify point is 2-element [longitude, latitude]
        origin_pt = est_origin["point"]
        self.assertIsInstance(origin_pt, (list, tuple))
        self.assertEqual(len(origin_pt), 2, "estimated_origin.point must be 2 elements [lon, lat]")
        origin_lon, origin_lat = float(origin_pt[0]), float(origin_pt[1])
        self.assertTrue(-180.0 <= origin_lon <= 180.0, f"Origin longitude {origin_lon} out of bounds")
        self.assertTrue(-90.0 <= origin_lat <= 90.0, f"Origin latitude {origin_lat} out of bounds")

        # Verify time_utc is valid UTC ISO-8601
        origin_t = est_origin["time_utc"]
        self.assertIsInstance(origin_t, str)
        self.assertTrue(
            origin_t.endswith("Z") or "+00:00" in origin_t,
            f"estimated_origin.time_utc must explicitly state UTC ('Z' or '+00:00'), got: {origin_t}"
        )
        parsed_origin_time = datetime.fromisoformat(origin_t.replace("Z", "+00:00"))
        self.assertIsNotNone(parsed_origin_time)

        # 5. Verify backtrack_track
        self.assertIn("backtrack_track", real_contract_b, "Contract B must contain 'backtrack_track'")
        backtrack = real_contract_b["backtrack_track"]
        self.assertIsInstance(backtrack, dict)
        self.assertEqual(backtrack.get("type"), "LineString", "backtrack_track.type must be 'LineString'")
        coords = backtrack.get("coordinates")
        self.assertIsInstance(coords, list, "backtrack coordinates must be a list")
        self.assertGreaterEqual(len(coords), 1, "backtrack coordinates must have >= 1 waypoint")

        for idx, pt in enumerate(coords):
            self.assertIsInstance(pt, (list, tuple))
            self.assertEqual(len(pt), 2, f"Waypoint {idx} must be [lon, lat]")
            w_lon, w_lat = float(pt[0]), float(pt[1])
            self.assertTrue(-180.0 <= w_lon <= 180.0, f"Waypoint {idx} lon {w_lon} out of bounds")
            self.assertTrue(-90.0 <= w_lat <= 90.0, f"Waypoint {idx} lat {w_lat} out of bounds")

        # 6. Verify forecast_polygons exist in Contract B
        self.assertIn("forecast_polygons", real_contract_b, "Contract B must contain 'forecast_polygons'")
        polygons = real_contract_b["forecast_polygons"]
        self.assertIsInstance(polygons, list)
        self.assertGreaterEqual(len(polygons), 1, "forecast_polygons must contain at least 1 entry")
        for poly_entry in polygons:
            self.assertIn("hours_ahead", poly_entry)
            self.assertIn("geometry", poly_entry)
            self.assertEqual(poly_entry["geometry"].get("type"), "Polygon")

        # 7. Verify Member 3 accepts Contract B without any transformation
        validated_contract_b = ContractBInput(**real_contract_b)
        self.assertEqual(validated_contract_b.slick_id, real_contract_b["slick_id"])

        # 8. Execute Member 3 Attribution Engine directly with real Contract B
        engine = VesselAttributionEngine(DEFAULT_CONFIG)
        contract_c = engine.attribute_spill(
            contract_b=real_contract_b,
            ais_source=self.synthetic_ais_path
        )

        # 9. Verify Member 3 produces valid Contract C
        self.assertIsInstance(contract_c, dict, "Attribution engine must return Contract C dict")
        is_valid_c, errors_c = validate_contract_c(contract_c)
        self.assertTrue(is_valid_c, f"Contract C validation failed: {errors_c}")

        # 10. Verify Contract C contains ranked_suspects, closest_encounter, trajectory_geojson, evidence_package
        self.assertIn("ranked_suspects", contract_c)
        suspects = contract_c["ranked_suspects"]
        self.assertIsInstance(suspects, list)
        self.assertGreater(len(suspects), 0, "Expected at least 1 candidate suspect from synthetic AIS corridor")

        for s in suspects:
            score = s.get("composite_threat_score")
            self.assertIsInstance(score, (int, float))
            self.assertTrue(0.0 <= score <= 1.0, f"Suspect threat score {score} out of bounds [0, 1]")
            self.assertIn(s.get("threat_level"), ["HIGH", "MEDIUM", "LOW"])

            # Verify closest_encounter
            self.assertIn("closest_encounter", s, "Suspect must contain 'closest_encounter'")
            self.assertIn("min_distance_to_origin_km", s["closest_encounter"])
            self.assertIn("closest_point_time_utc", s["closest_encounter"])
            self.assertIn("vessel_point_at_cpa", s["closest_encounter"])

            # Verify trajectory_geojson
            self.assertIn("trajectory_geojson", s, "Suspect must contain 'trajectory_geojson'")

            # Verify evidence_package
            self.assertIn("evidence_package", s, "Suspect must contain 'evidence_package'")


if __name__ == "__main__":
    unittest.main()
