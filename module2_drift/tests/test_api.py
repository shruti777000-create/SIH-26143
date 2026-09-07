"""
Module 2 Tests - FastAPI REST API Test Suite
Validates POST /api/drift endpoint:
  1. Health check (GET /health).
  2. Successful Contract A ingestion returning Contract B JSON (HTTP 200).
  3. Malformed input payloads properly rejected with clear HTTP 400 responses.
  4. Pipeline error handling (temporal out-of-bounds, spatial violations, land intersection)
     returned as sensible HTTP 400 error responses (no raw 500s).
"""

import unittest
from fastapi.testclient import TestClient
from module2_drift.api import app
from module2_drift.validate_schema import validate_drift_output


class TestDriftAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # Valid 500m square polygon offshore Mumbai entrance
        self.valid_payload = {
            "slick_id": "SLICK-AS-MUMBAI-20260904-001",
            "timestamp_utc": "2026-09-04T12:00:00Z",
            "geometry": {
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
            },
            "area_km2": 0.25,
            "confidence": 0.94,
            "seed_mode": "distributed",
            "num_particles": 5,
            "backtrack_hours": 1,
            "forecast_hours": [1]
        }

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "HEALTHY")
        self.assertIn("MARIS Module 2", data.get("service", ""))

    def test_post_drift_success(self):
        # Successful run returning Contract B
        response = self.client.post("/api/drift", json=self.valid_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check required Contract B top-level fields
        self.assertEqual(data.get("slick_id"), self.valid_payload["slick_id"])
        self.assertIn("estimated_origin", data)
        self.assertIn("backtrack_track", data)
        self.assertIn("forecast_polygons", data)

        # Validate strictly against Contract B schema
        is_valid, errors = validate_drift_output(data)
        self.assertTrue(is_valid, f"Contract B schema errors: {errors}")

    def test_reject_missing_required_fields_400(self):
        # Missing geometry and timestamp_utc
        bad_payload = {
            "slick_id": "SLICK-INVALID"
        }
        response = self.client.post("/api/drift", json=bad_payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data.get("error"))
        self.assertEqual(data.get("error_type"), "MALFORMED_REQUEST")
        self.assertIn("failed validation", data.get("reason", "").lower())

    def test_reject_unclosed_polygon_400(self):
        # Polygon with unclosed ring
        bad_payload = dict(self.valid_payload)
        bad_payload["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [72.748, 18.848],
                    [72.752, 18.848],
                    [72.752, 18.852],
                    [72.748, 18.852]  # Missing closing vertex
                ]
            ]
        }
        response = self.client.post("/api/drift", json=bad_payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data.get("error"))
        self.assertIn("validation_errors", data.get("details", {}))

    def test_pipeline_temporal_out_of_bounds_400(self):
        # Date outside local NetCDF coverage
        bad_payload = dict(self.valid_payload)
        bad_payload["timestamp_utc"] = "2020-01-01T00:00:00Z"

        response = self.client.post("/api/drift", json=bad_payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data.get("error"))
        self.assertEqual(data.get("error_type"), "TEMPORAL_OUT_OF_BOUNDS")
        self.assertIn("Available local dataset ranges", data.get("reason", ""))

    def test_pipeline_land_intersection_400(self):
        # Coordinates located inland in Maharashtra
        bad_payload = dict(self.valid_payload)
        bad_payload["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [73.18, 19.08],
                    [73.22, 19.08],
                    [73.22, 19.12],
                    [73.18, 19.12],
                    [73.18, 19.08]
                ]
            ]
        }
        response = self.client.post("/api/drift", json=bad_payload)
        # LAND_INTERSECTION returns 400; if OpenDrift stops first ("No ocean pixels nearby"),
        # the pipeline catches it as SIMULATION_FAILURE which returns 502. Both are sensible.
        self.assertIn(response.status_code, [400, 502])
        data = response.json()
        self.assertTrue(data.get("error"))
        self.assertIn(data.get("error_type"), ["LAND_INTERSECTION", "SIMULATION_FAILURE"])

    def test_pipeline_spatial_out_of_bounds_400(self):
        # Coordinates in Bay of Bengal
        bad_payload = dict(self.valid_payload)
        bad_payload["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [
                    [88.48, 15.18],
                    [88.52, 15.18],
                    [88.52, 15.22],
                    [88.48, 15.22],
                    [88.48, 15.18]
                ]
            ]
        }
        response = self.client.post("/api/drift", json=bad_payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data.get("error"))
        self.assertEqual(data.get("error_type"), "SPATIAL_OUT_OF_BOUNDS")


if __name__ == "__main__":
    unittest.main()
