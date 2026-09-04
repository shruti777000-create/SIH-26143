"""
Module 3 Tests - FastAPI Endpoints & System Integration
SIH Problem Statement 26143 - Phase 4 Test Suite
Tests /health, /api/attribute, validation errors, CORS, and end-to-end pipeline.
"""

import os
import io
import json
import unittest
from fastapi.testclient import TestClient

from module3_ais import __version__
from module3_ais.api import app
from module3_ais.validate_schema import validate_contract_c


class TestAttributionAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.base_dir = os.path.dirname(os.path.abspath(__file__))
        cls.sample_contract_b_path = os.path.join(cls.base_dir, "..", "..", "contracts", "sample_drift_output.json")
        cls.synthetic_csv_path = os.path.join(cls.base_dir, "..", "data", "synthetic_ais.csv")

        with open(cls.sample_contract_b_path, "r", encoding="utf-8") as f:
            cls.valid_contract_b_dict = json.load(f)
        cls.valid_contract_b_str = json.dumps(cls.valid_contract_b_dict)

        with open(cls.synthetic_csv_path, "rb") as f:
            cls.valid_ais_bytes = f.read()

    # -------------------------------------------------------------------------
    # 1. Health Endpoint Tests
    # -------------------------------------------------------------------------
    def test_health_endpoint(self):
        """GET /health returns HTTP 200, status ok, module identifier, and dynamic version."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["module"], "member3_ais")
        self.assertEqual(data["version"], __version__)

    # -------------------------------------------------------------------------
    # 2. OpenAPI and Documentation Endpoints
    # -------------------------------------------------------------------------
    def test_openapi_and_docs_exposed(self):
        """FastAPI automatically exposes /openapi.json and /docs."""
        res_openapi = self.client.get("/openapi.json")
        self.assertEqual(res_openapi.status_code, 200)
        openapi_data = res_openapi.json()
        self.assertIn("paths", openapi_data)
        self.assertIn("/api/attribute", openapi_data["paths"])

        res_docs = self.client.get("/docs")
        self.assertEqual(res_docs.status_code, 200)

    # -------------------------------------------------------------------------
    # 3. End-to-End Valid Attribution Test (Contract B + Synthetic AIS -> Contract C)
    # -------------------------------------------------------------------------
    def test_valid_attribution_pipeline_returns_contract_c(self):
        """POST /api/attribute executes the complete pipeline and returns valid Contract C."""
        files = {
            "ais_file": ("synthetic_ais.csv", self.valid_ais_bytes, "text/csv")
        }
        data = {
            "contract_b": self.valid_contract_b_str
        }

        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 200)

        contract_c = response.json()

        # 1. Verify schema compliance using validate_contract_c
        is_valid, errors = validate_contract_c(contract_c)
        self.assertTrue(is_valid, f"Contract C validation failed: {errors}")

        # 2. Verify critical contract fields
        self.assertEqual(contract_c["slick_id"], self.valid_contract_b_dict["slick_id"])
        self.assertIn("spill_context", contract_c)
        self.assertIn("suspect_summary", contract_c)
        self.assertIn("ranked_suspects", contract_c)
        self.assertEqual(contract_c["status"], "COMPLETED")

        # 3. Verify suspect rankings are sorted descending
        suspects = contract_c["ranked_suspects"]
        self.assertGreater(len(suspects), 0)

        prev_score = 1.01
        for idx, s in enumerate(suspects, start=1):
            self.assertEqual(s["rank"], idx)
            score = s["composite_threat_score"]
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            self.assertLessEqual(score, prev_score)
            prev_score = score

            # Verify threat level tier
            self.assertIn(s["threat_level"], ["HIGH", "MEDIUM", "LOW"])

            # Verify evidence package exists
            self.assertIn("evidence_package", s)
            self.assertIn("summary", s["evidence_package"])

            # Verify trajectory GeoJSON format
            self.assertIn("trajectory_geojson", s)
            geom = s["trajectory_geojson"]["geometry"]
            self.assertIn(geom["type"], ["LineString", "Point"])
            # Coordinate check: [lon, lat]
            if geom["type"] == "LineString" and geom["coordinates"]:
                self.assertGreater(geom["coordinates"][0][0], 50.0, "Longitude must be first")
                self.assertLess(geom["coordinates"][0][1], 35.0, "Latitude must be second")

    # -------------------------------------------------------------------------
    # 4. Error Handling: Malformed / Invalid Contract B
    # -------------------------------------------------------------------------
    def test_malformed_contract_b_json(self):
        """Malformed JSON string returns HTTP 400."""
        files = {
            "ais_file": ("synthetic_ais.csv", self.valid_ais_bytes, "text/csv")
        }
        data = {
            "contract_b": "{invalid_json: true"  # Broken JSON
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Malformed Contract B JSON", response.json()["detail"])

    def test_contract_b_missing_required_fields(self):
        """Contract B missing estimated_origin returns HTTP 422 validation error."""
        bad_contract_b = {
            "slick_id": "SLICK-001"
            # Missing estimated_origin and backtrack_track
        }
        files = {
            "ais_file": ("synthetic_ais.csv", self.valid_ais_bytes, "text/csv")
        }
        data = {
            "contract_b": json.dumps(bad_contract_b)
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 422)
        self.assertIn("schema validation failed", response.json()["detail"].lower())

    def test_contract_b_invalid_coordinates(self):
        """Contract B with coordinates out of physical bounds returns HTTP 422."""
        bad_contract_b = json.loads(self.valid_contract_b_str)
        bad_contract_b["estimated_origin"]["point"] = [999.0, 999.0]  # Out of bounds
        files = {
            "ais_file": ("synthetic_ais.csv", self.valid_ais_bytes, "text/csv")
        }
        data = {
            "contract_b": json.dumps(bad_contract_b)
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 422)

    # -------------------------------------------------------------------------
    # 5. Error Handling: Missing / Invalid AIS Files & Columns
    # -------------------------------------------------------------------------
    def test_missing_ais_file(self):
        """Request omitting ais_file returns HTTP 422 (FastAPI required file parameter)."""
        data = {
            "contract_b": self.valid_contract_b_str
        }
        response = self.client.post("/api/attribute", data=data)
        self.assertIn(response.status_code, [400, 422])

    def test_empty_ais_file(self):
        """Uploading a 0-byte AIS file returns HTTP 400."""
        files = {
            "ais_file": ("empty.csv", b"", "text/csv")
        }
        data = {
            "contract_b": self.valid_contract_b_str
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", response.json()["detail"].lower())

    def test_invalid_ais_columns(self):
        """Uploading AIS CSV missing required columns returns HTTP 400."""
        bad_csv = b"timestamp,mmsi\n2026-09-04T00:00:00Z,419001001\n"
        files = {
            "ais_file": ("bad_cols.csv", bad_csv, "text/csv")
        }
        data = {
            "contract_b": self.valid_contract_b_str
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("missing mandatory columns", response.json()["detail"].lower())

    def test_ais_file_all_invalid_records(self):
        """AIS file where all rows are filtered out during cleaning returns HTTP 400."""
        dirty_csv = (
            b"timestamp,mmsi,latitude,longitude,sog,cog\n"
            b"2026-09-04T00:00:00Z,419001001,999.0,999.0,-5.0,999.0\n"  # all fields invalid
        )
        files = {
            "ais_file": ("dirty.csv", dirty_csv, "text/csv")
        }
        data = {
            "contract_b": self.valid_contract_b_str
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no valid records", response.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # 6. Error Handling: No Vessels in Corridor
    # -------------------------------------------------------------------------
    def test_no_vessels_in_search_corridor_returns_404(self):
        """Vessels that are all far outside the 50 km / 12h corridor return HTTP 404."""
        distant_csv = (
            b"timestamp,mmsi,latitude,longitude,sog,cog\n"
            b"2026-09-04T00:00:00Z,419999999,10.0,60.0,12.0,180.0\n"  # ~1500 km away
        )
        files = {
            "ais_file": ("distant.csv", distant_csv, "text/csv")
        }
        data = {
            "contract_b": self.valid_contract_b_str
        }
        response = self.client.post("/api/attribute", files=files, data=data)
        self.assertEqual(response.status_code, 404)
        self.assertIn("no vessels found", response.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # 7. CORS Headers Test
    # -------------------------------------------------------------------------
    def test_cors_headers_present(self):
        """CORS headers are correctly returned for cross-origin requests."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"
        }
        response = self.client.options("/api/attribute", headers=headers)
        self.assertIn(response.status_code, [200, 204])
        self.assertIn("access-control-allow-origin", response.headers)


if __name__ == '__main__':
    unittest.main()
