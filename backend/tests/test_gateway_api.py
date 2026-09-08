"""
Tests for the MARIS Unified API Gateway (backend/main.py).

Verifies:
- GET / health check
- POST /api/detect (demo mode, real mode 503/400 error handling)
- GET /api/detect (backwards compatibility)
- POST /api/drift (real OpenDrift simulation from Contract A -> Contract B)
- GET /api/drift (backwards compatibility)
- POST /api/attribute (real AIS attribution from Contract B -> Contract C)
- GET /api/attribute (backwards compatibility)
- POST /api/pipeline (end-to-end M1 -> M2 -> M3 orchestration)
- GET /api/pipeline (backwards compatibility)
"""

import io
import unittest
from fastapi.testclient import TestClient

from backend.main import app
from backend.demo_fixture import get_demo_contract_a
from module3_ais.validate_schema import validate_contract_c


class TestMARISGatewayAPI(unittest.TestCase):
    """Smoke and integration tests for the unified FastAPI backend gateway."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    # -----------------------------------------------------------------------
    # 0. Health Check
    # -----------------------------------------------------------------------
    def test_root_health_check(self):
        """GET / returns system status, name MARIS, and available endpoints."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("system"), "MARIS")
        self.assertEqual(data.get("version"), "2.0.0")
        self.assertIn("/api/pipeline", data.get("endpoints", []))

    # -----------------------------------------------------------------------
    # 1. Detection Endpoint (POST & GET /api/detect)
    # -----------------------------------------------------------------------
    def test_detect_demo_mode_query_param(self):
        """POST /api/detect?demo=true returns deterministic Contract A fixture."""
        response = self.client.post("/api/detect?demo=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("demo_mode"))
        self.assertEqual(data.get("slick_id"), "DEMO-SLICK-001")
        self.assertIn("timestamp_utc", data)
        self.assertIn("geometry", data)
        self.assertEqual(data["geometry"].get("type"), "Polygon")

    def test_detect_demo_mode_json_body(self):
        """POST /api/detect with JSON {"demo": true} returns demo Contract A."""
        response = self.client.post("/api/detect", json={"demo": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("demo_mode"))
        self.assertEqual(data.get("slick_id"), "DEMO-SLICK-001")

    def test_detect_get_backwards_compatible(self):
        """GET /api/detect returns demo Contract A fixture."""
        response = self.client.get("/api/detect")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("demo_mode"))
        self.assertEqual(data.get("slick_id"), "DEMO-SLICK-001")

    def test_detect_real_mode_missing_file_returns_400(self):
        """POST /api/detect without demo=true and no file upload returns HTTP 400."""
        response = self.client.post("/api/detect", json={"demo": False})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing SAR GeoTIFF", response.json().get("detail", ""))

    def test_detect_real_mode_missing_weights_returns_503(self):
        """POST /api/detect with uploaded GeoTIFF returns HTTP 503 when model weights are missing."""
        dummy_tif = io.BytesIO(b"FAKE_GEOTIFF_DATA")
        files = {"sar_file": ("test_sar.tif", dummy_tif, "image/tiff")}
        response = self.client.post("/api/detect", files=files, data={"demo": "false"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("model weights", response.json().get("detail", "").lower())

    # -----------------------------------------------------------------------
    # 2. Drift Endpoint (POST & GET /api/drift)
    # -----------------------------------------------------------------------
    def test_drift_post_valid_contract_a(self):
        """POST /api/drift with Contract A runs real Member 2 OpenDrift simulation."""
        demo_a = get_demo_contract_a()
        response = self.client.post("/api/drift", json=demo_a)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify Contract B fields
        self.assertEqual(data.get("slick_id"), demo_a["slick_id"])
        self.assertIn("estimated_origin", data)
        self.assertIn("forecast_polygons", data)

        origin = data["estimated_origin"]
        self.assertIn("point", origin)
        self.assertIn("time_utc", origin)
        lon, lat = origin["point"]
        self.assertTrue(70.0 <= lon <= 74.0, f"Origin lon {lon} not in Arabian Sea bounds")
        self.assertTrue(17.0 <= lat <= 20.0, f"Origin lat {lat} not in Arabian Sea bounds")

    def test_drift_post_malformed_payload_returns_400(self):
        """POST /api/drift with invalid payload returns HTTP 400."""
        bad_payload = {"slick_id": "TEST", "geometry": {"type": "Point", "coordinates": [0, 0]}}
        response = self.client.post("/api/drift", json=bad_payload)
        self.assertEqual(response.status_code, 400)

    def test_drift_get_backwards_compatible(self):
        """GET /api/drift runs real drift model on demo Contract A fixture."""
        response = self.client.get("/api/drift")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("slick_id"), "DEMO-SLICK-001")
        self.assertIn("estimated_origin", data)

    # -----------------------------------------------------------------------
    # 3. Vessel Attribution Endpoint (POST & GET /api/attribute)
    # -----------------------------------------------------------------------
    def test_attribute_post_valid_contract_b(self):
        """POST /api/attribute with Contract B runs real Member 3 VesselAttributionEngine."""
        # First obtain a real Contract B
        demo_a = get_demo_contract_a()
        drift_resp = self.client.post("/api/drift", json=demo_a)
        self.assertEqual(drift_resp.status_code, 200)
        contract_b = drift_resp.json()

        # Attribute with default synthetic AIS
        attr_resp = self.client.post("/api/attribute", json=contract_b)
        self.assertEqual(attr_resp.status_code, 200)
        contract_c = attr_resp.json()

        # Validate Contract C schema
        is_valid, errors = validate_contract_c(contract_c)
        self.assertTrue(is_valid, f"Contract C validation failed: {errors}")
        self.assertEqual(contract_c.get("slick_id"), demo_a["slick_id"])
        self.assertGreater(len(contract_c.get("ranked_suspects", [])), 0)

        # Check non-destructive frontend aliases
        self.assertIn("suspects", contract_c)
        first_suspect = contract_c["ranked_suspects"][0]
        self.assertIn("score", first_suspect)
        self.assertIn("proximity_km", first_suspect)
        self.assertIn("evidence_text", first_suspect)

    def test_attribute_post_malformed_contract_b_returns_400(self):
        """POST /api/attribute with malformed Contract B returns HTTP 400."""
        response = self.client.post("/api/attribute", json={"invalid": "payload"})
        self.assertEqual(response.status_code, 400)

    def test_attribute_get_backwards_compatible(self):
        """GET /api/attribute executes real drift + attribution on demo fixtures."""
        response = self.client.get("/api/attribute")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("slick_id"), "DEMO-SLICK-001")
        self.assertIn("ranked_suspects", data)
        self.assertIn("suspects", data)

    # -----------------------------------------------------------------------
    # 4. Pipeline Endpoint (POST & GET /api/pipeline)
    # -----------------------------------------------------------------------
    def test_pipeline_post_demo_mode(self):
        """
        POST /api/pipeline?demo=true executes end-to-end M1 -> M2 -> M3:
        - Contract A exists
        - Contract B exists
        - Contract C exists
        - slick_id propagates
        - pipeline_status == "SUCCESS"
        - Member 2 actually executes (origin coordinates computed)
        - Member 3 actually executes (suspect vessels scored and ranked)
        """
        response = self.client.post("/api/pipeline?demo=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Top-level pipeline envelope
        self.assertEqual(data.get("pipeline_status"), "SUCCESS")
        self.assertTrue(data.get("demo_mode"))
        self.assertIn("contract_a", data)
        self.assertIn("contract_b", data)
        self.assertIn("contract_c", data)

        ca = data["contract_a"]
        cb = data["contract_b"]
        cc = data["contract_c"]

        # Slick ID propagation
        self.assertEqual(ca.get("slick_id"), "DEMO-SLICK-001")
        self.assertEqual(cb.get("slick_id"), "DEMO-SLICK-001")
        self.assertEqual(cc.get("slick_id"), "DEMO-SLICK-001")

        # Member 2 execution verification
        self.assertIn("estimated_origin", cb)
        origin_pt = cb["estimated_origin"]["point"]
        self.assertTrue(70.0 <= origin_pt[0] <= 74.0)
        self.assertTrue(17.0 <= origin_pt[1] <= 20.0)

        # Member 3 execution verification
        is_valid_c, c_errs = validate_contract_c(cc)
        self.assertTrue(is_valid_c, f"Pipeline Contract C schema invalid: {c_errs}")
        ranked = cc.get("ranked_suspects", [])
        self.assertGreater(len(ranked), 0)
        self.assertGreater(ranked[0]["composite_threat_score"], 0.0)

    def test_pipeline_post_real_mode_missing_file_returns_400(self):
        """POST /api/pipeline with demo=false and no file upload returns HTTP 400."""
        response = self.client.post("/api/pipeline?demo=false")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing required SAR GeoTIFF", response.json().get("detail", ""))

    def test_pipeline_post_real_mode_missing_weights_returns_503(self):
        """POST /api/pipeline with dummy SAR upload returns HTTP 503 when weights missing."""
        dummy_tif = io.BytesIO(b"FAKE_SAR_DATA")
        files = {"sar_file": ("sar.tif", dummy_tif, "image/tiff")}
        response = self.client.post("/api/pipeline", files=files, data={"demo": "false"})
        self.assertEqual(response.status_code, 503)

    def test_pipeline_get_backwards_compatible(self):
        """GET /api/pipeline executes the full demo pipeline returning 200 SUCCESS."""
        response = self.client.get("/api/pipeline")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("pipeline_status"), "SUCCESS")
        self.assertTrue(data.get("demo_mode"))
        self.assertIn("contract_a", data)
        self.assertIn("contract_b", data)
        self.assertIn("contract_c", data)


if __name__ == "__main__":
    unittest.main()
