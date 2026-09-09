"""
MARIS Unified API Gateway (SIH-26143)

Orchestrates the Marine Accident Response & Intelligence System analytical pipeline:
Member 1: Oil Spill Detection (SAR U-Net / Deterministic Demo Fixture)
Member 2: Lagrangian Drift Simulation (OpenDrift Hindcast & Forecast)
Member 3: AIS Vessel Attribution & Anomaly Intelligence

Exposes:
- GET  /              Health check
- POST /api/detect    Detect oil spill from SAR GeoTIFF or return demo Contract A
- GET  /api/detect    Backwards-compatible demo detection endpoint
- POST /api/drift     Execute OpenDrift simulation from Contract A -> Contract B
- GET  /api/drift     Backwards-compatible demo drift endpoint
- POST /api/attribute Execute AIS attribution from Contract B -> Contract C
- GET  /api/attribute Backwards-compatible demo attribution endpoint
- POST /api/pipeline  End-to-end orchestration (M1 -> M2 -> M3)
"""

from email.mime import image
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional
import io
import cv2
import numpy as np
import rasterio
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

# Member 1
from backend.demo_fixture import get_demo_contract_a
from backend.oil_spill_detector import (
    MODEL_PATH,
    detect_spill,
    format_contract_a,
    predict_probability_map,
    clean_mask,
    extract_main_spill,
)

# Member 2
from module2_drift.api import ContractARequest
from module2_drift.drift_model import forecast_drift

# Member 3
from module3_ais.attribution_engine import VesselAttributionEngine
from module3_ais.config import DEFAULT_CONFIG
from module3_ais.schemas import ContractBInput

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AIS_PATH = REPO_ROOT / "module3_ais" / "data" / "synthetic_ais.csv"

app = FastAPI(
    title="MARIS API Gateway",
    description="Maritime Accident Response & Intelligence System Unified Gateway",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _enrich_contract_c_for_frontend(contract_c: Dict[str, Any]) -> None:
    """Non-destructive enrichment with legacy aliases so existing frontend widgets render."""
    if not isinstance(contract_c, dict):
        return
    ranked = contract_c.get("ranked_suspects", [])
    if isinstance(ranked, list):
        for s in ranked:
            if isinstance(s, dict):
                if "score" not in s and "composite_threat_score" in s:
                    s["score"] = s["composite_threat_score"]
                if "proximity_km" not in s and "closest_encounter" in s:
                    cpa = s["closest_encounter"]
                    if isinstance(cpa, dict) and "min_distance_to_origin_km" in cpa:
                        s["proximity_km"] = cpa["min_distance_to_origin_km"]
                if "evidence_text" not in s and "evidence_package" in s:
                    pkg = s["evidence_package"]
                    if isinstance(pkg, dict) and "summary" in pkg:
                        s["evidence_text"] = pkg["summary"]
                if "anomaly_flags" not in s and "anomaly_indicators" in s:
                    s["anomaly_flags"] = s["anomaly_indicators"]
        if "suspects" not in contract_c:
            contract_c["suspects"] = ranked


# ---------------------------------------------------------------------------
# 0. Health Check
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "online",
        "system": "MARIS",
        "version": "2.0.0",
        "message": "MARIS Unified Gateway is running",
        "endpoints": [
            "/api/detect",
            "/api/drift",
            "/api/attribute",
            "/api/pipeline",
        ],
    }


# ---------------------------------------------------------------------------
# 1. Contract A — Detection
# ---------------------------------------------------------------------------

@app.post("/api/detect")
async def detect_spill_post(
    request: Request,
    demo: bool = Query(False),
):
    """
    POST /api/detect:
    - If demo=true or requested: returns deterministic Contract A demo fixture.
    - If SAR GeoTIFF uploaded: executes real detect_spill() and format_contract_a().
      If weights are missing, returns HTTP 503.
    """
    content_type = request.headers.get("content-type", "")
    is_demo = demo
    uploaded_file = None
    slick_id = None
    timestamp_utc = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        if "demo" in form:
            demo_val = str(form.get("demo")).lower()
            is_demo = demo_val in ("true", "1", "yes")
        uploaded_file = form.get("file") or form.get("sar_file")
        slick_id = form.get("slick_id")
        timestamp_utc = form.get("timestamp_utc")
    elif "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                is_demo = body.get("demo", is_demo)
                slick_id = body.get("slick_id")
                timestamp_utc = body.get("timestamp_utc")
        except Exception:
            pass

    # A. Demo Mode
    if is_demo:
        contract_a = get_demo_contract_a()
        contract_a["demo_mode"] = True
        return contract_a

    # B. Real Mode
    if uploaded_file is None or not hasattr(uploaded_file, "read") or not getattr(uploaded_file, "filename", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing SAR GeoTIFF image file upload. Set demo=true for synthetic demonstration mode.",
        )

    model_file = Path(MODEL_PATH)
    if not model_file.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Real U-Net detection model weights ({MODEL_PATH}) are not available on this server. "
                "Set demo=true to use the deterministic demonstration fixture."
            ),
        )

    # Save uploaded file to temp file for rasterio reading
    file_bytes = await uploaded_file.read()
    temp_tif = tempfile.NamedTemporaryFile(delete=False, suffix=".tif")
    try:
        temp_tif.write(file_bytes)
        temp_tif.flush()
        temp_tif.close()

        raw_detection = detect_spill(temp_tif.name)
        contract_a = format_contract_a(
            detection_result=raw_detection,
            slick_id=slick_id or "SLICK-SAR-001",
            timestamp_utc=timestamp_utc,
            image_path=temp_tif.name,
        )
        contract_a["demo_mode"] = False
        return contract_a
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection processing failed: {exc}",
        )
    finally:
        if os.path.exists(temp_tif.name):
            try:
                os.remove(temp_tif.name)
            except Exception:
                pass


@app.get("/api/detect")
def detect_spill_get():
    """
    GET /api/detect:
    Runs the real U-Net detector on the local demo SAR GeoTIFF.
    Used by Investigation.jsx.
    """
    demo_image = Path(
        r"C:\Users\HEMACHANDRU R\Downloads\00204.tif"
    )

    if not demo_image.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demo SAR image not found: {demo_image}",
        )

    model_file = Path(MODEL_PATH)

    if not model_file.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model weights not found: {MODEL_PATH}",
        )

    try:
        raw_detection = detect_spill(str(demo_image))

        contract_a = format_contract_a(
            detection_result=raw_detection,
            slick_id="SLICK-SAR-00204",
            timestamp_utc="2026-09-04T12:00:00Z",
            image_path=str(demo_image),
        )

        contract_a["demo_mode"] = False

        return contract_a

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection processing failed: {exc}",
        )
@app.get("/api/detect/segmentation-overlay")
def segmentation_overlay():
    """
    Returns the real U-Net segmentation visualization for the local demo SAR image.
    """

    demo_image = Path(
        r"C:\Users\HEMACHANDRU R\Downloads\00204.tif"
    )

    if not demo_image.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demo SAR image not found: {demo_image}",
        )

    try:
        from backend.oil_spill_detector import (
            predict_probability_map,
            clean_mask,
            extract_main_spill,
            normalize_band,
        )

        if cv2 is None:
            raise RuntimeError("OpenCV is not available")

        # Read Sentinel-1 image
        with rasterio.open(demo_image) as src:
            image = src.read([1, 2]).astype(np.float32)

# IMPORTANT: use the exact same preprocessing as detect_spill()
        image[0] = normalize_band(image[0])
        image[1] = normalize_band(image[1])

        probability_map = predict_probability_map(image)

        # Threshold + morphological cleanup
        mask = clean_mask(probability_map)

        # Keep only largest connected spill region
        main_spill = extract_main_spill(mask)


        # Transparent background + red oil-spill segmentation
        overlay = np.zeros(
             (image.shape[1], image.shape[2], 4),
             dtype=np.uint8,
)

# Red oil-spill segmentation with transparency
        overlay[main_spill > 0] = (0, 0, 255, 180)
        # Encode as PNG
        success, encoded = cv2.imencode(".png", overlay)

        if not success:
            raise RuntimeError("Failed to encode segmentation overlay")

        return StreamingResponse(
            io.BytesIO(encoded.tobytes()),
            media_type="image/png",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Segmentation overlay generation failed: {exc}",
        )


# ---------------------------------------------------------------------------
# 2. Contract B — Drift / Hindcast / Forecast
# ---------------------------------------------------------------------------

@app.post("/api/drift")
async def drift_forecast_post(request: Request):
    """
    POST /api/drift:
    Accepts Contract A payload, validates via ContractARequest,
    and runs real Member 2 forecast_drift() simulation.
    """
    content_type = request.headers.get("content-type", "")
    payload_data = None

    if "application/json" in content_type:
        try:
            payload_data = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        if "contract_a" in form:
            try:
                payload_data = json.loads(form["contract_a"])
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid contract_a JSON in form: {e}")
        else:
            payload_data = dict(form)
    else:
        try:
            payload_data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Expected JSON or multipart Contract A payload.")

    # Validate Contract A
    try:
        req_a = ContractARequest(**payload_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Contract A validation error: {e}")

    # Run real Member 2 simulation using validated parameters proven in integration:
    # seed_mode="centroid", backtrack_hours=12, forecast_hours=[6, 24], num_particles=25
    try:
        contract_b = forecast_drift(
            slick_polygon=payload_data,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=25,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenDrift simulation failed: {e}")

    if not isinstance(contract_b, dict) or contract_b.get("error"):
        reason = contract_b.get("reason", "Simulation failed") if isinstance(contract_b, dict) else "Unknown"
        raise HTTPException(status_code=400, detail=f"Drift simulation error: {reason}")

    contract_b["slick_id"] = req_a.slick_id

    # Validate output schema
    try:
        ContractBInput(**contract_b)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generated Contract B schema error: {e}")

    return contract_b


# ---------------------------------------------------------------------------
# 2. Contract B — Drift / Hindcast / Forecast
# ---------------------------------------------------------------------------

def build_demo_drift_contract(contract_a: Dict[str, Any]) -> Dict[str, Any]:
    """
    Demo-safe Contract B.

    Used when Member 2 cannot access local metocean/OpenDrift data.
    The structure is intentionally compatible with Investigation.jsx.
    """

    geometry = contract_a.get("geometry", {})

    # Use the actual detected/demo polygon centroid when possible.
    try:
        ring = geometry["coordinates"][0]
        lng = sum(point[0] for point in ring[:-1]) / len(ring[:-1])
        lat = sum(point[1] for point in ring[:-1]) / len(ring[:-1])
    except Exception:
        lng = 30.306115133946207
        lat = 33.16366307453298

    return {
        "slick_id": contract_a.get("slick_id", "DEMO-SLICK-001"),
        "demo_mode": True,
        "status": "DEMO_FALLBACK",

        "message": (
            "Real drift simulation unavailable because local "
            "metocean/OpenDrift environmental data is unavailable."
        ),

        "estimated_origin": {
            "point": [lng, lat],
            "time_utc": contract_a.get(
                "timestamp_utc",
                "2026-09-04T12:00:00Z"
            ),
        },

        "backtrack_track": {
            "type": "LineString",
            "coordinates": [
                [lng, lat],
                [lng - 0.006, lat + 0.003],
                [lng - 0.012, lat + 0.006],
                [lng - 0.018, lat + 0.009],
            ],
        },

        "forecast_polygons": [
            {
                "hours_ahead": 6,
                "demo_mode": True,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lng - 0.006, lat - 0.004],
                        [lng + 0.006, lat - 0.004],
                        [lng + 0.009, lat + 0.004],
                        [lng,        lat + 0.008],
                        [lng - 0.006, lat - 0.004],
                    ]],
                },
            },
            {
                "hours_ahead": 24,
                "demo_mode": True,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lng - 0.014, lat - 0.010],
                        [lng + 0.014, lat - 0.010],
                        [lng + 0.020, lat + 0.010],
                        [lng,        lat + 0.018],
                        [lng - 0.014, lat - 0.010],
                    ]],
                },
            },
        ],
    }
@app.get("/api/drift")
def drift_forecast_get():
    """
    GET /api/drift.

    Uses the same real Contract A produced by the
    satellite oil-spill detector for 00204.tif.
    """

    demo_image = Path(
        r"C:\Users\HEMACHANDRU R\Downloads\00204.tif"
    )

    if not demo_image.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Demo Sentinel-1 image not found: {demo_image}"
        )

    try:
        # Run the SAME real satellite detector used by /api/detect.
        raw_detection = detect_spill(str(demo_image))

        contract_a = format_contract_a(
            detection_result=raw_detection,
            slick_id="SLICK-SAR-00204",
            timestamp_utc="2026-09-04T12:00:00Z",
            image_path=str(demo_image),
        )

        # Build demo-safe drift around the REAL detected slick.
        return build_demo_drift_contract(contract_a)

    except Exception as exc:
        print(
            "[MARIS] GET /api/drift failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Unable to generate drift contract: {exc}"
        )
@app.post("/api/drift")
async def drift_forecast_post(request: Request):
    """
    POST /api/drift.

    Executes the real Member 2 OpenDrift model when available.
    If the environmental data/model is unavailable, returns
    a clearly labelled demo fallback instead of HTTP 500.
    """

    content_type = request.headers.get("content-type", "")
    payload_data = None

    if "application/json" in content_type:
        try:
            payload_data = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON payload: {exc}",
            )

    elif (
        "multipart/form-data" in content_type
        or "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()

        if "contract_a" in form:
            try:
                payload_data = json.loads(form["contract_a"])
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid contract_a JSON in form: {exc}",
                )
        else:
            payload_data = dict(form)

    else:
        try:
            payload_data = await request.json()
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Expected JSON or multipart Contract A payload.",
            )

    if not isinstance(payload_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Contract A payload must be a JSON object.",
        )

    # Validate Contract A.
    try:
        req_a = ContractARequest(**payload_data)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Contract A validation error: {exc}",
        )

    # Try the real Member 2 engine.
    try:
        contract_b = forecast_drift(
            slick_polygon=payload_data,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=25,
        )

        if (
            isinstance(contract_b, dict)
            and not contract_b.get("error")
        ):
            contract_b["slick_id"] = req_a.slick_id
            contract_b["demo_mode"] = False
            return contract_b

    except Exception as exc:
        print(
            "[MARIS] Real drift simulation unavailable. "
            f"Using fallback. "
            f"{type(exc).__name__}: {exc}"
        )

    # Demo fallback.
    return build_demo_drift_contract(payload_data)

# ---------------------------------------------------------------------------
# 3. Contract C — Vessel Attribution
# ---------------------------------------------------------------------------

@app.post("/api/attribute")
async def vessel_attribution_post(request: Request):
    """
    POST /api/attribute:
    Accepts Contract B JSON and optional uploaded AIS CSV.
    Validates Contract B via ContractBInput and executes real VesselAttributionEngine.
    """
    content_type = request.headers.get("content-type", "")
    ais_path = str(DEFAULT_AIS_PATH)
    temp_ais_file = None
    contract_b_data = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_b = form.get("contract_b")
        if not raw_b:
            raise HTTPException(status_code=400, detail="Missing required 'contract_b' in form data.")
        if isinstance(raw_b, str):
            try:
                contract_b_data = json.loads(raw_b)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON string in 'contract_b': {e}")
        elif isinstance(raw_b, dict):
            contract_b_data = raw_b
        else:
            raise HTTPException(status_code=400, detail="Invalid 'contract_b' payload format.")

        ais_upload = form.get("ais_file")
        if ais_upload and hasattr(ais_upload, "read") and getattr(ais_upload, "filename", None):
            content = await ais_upload.read()
            if content:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                tmp.write(content)
                tmp.flush()
                tmp.close()
                ais_path = tmp.name
                temp_ais_file = tmp.name
    else:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
        if "contract_b" in body and isinstance(body["contract_b"], dict):
            contract_b_data = body["contract_b"]
        else:
            contract_b_data = body

    # Validate Contract B
    try:
        ContractBInput(**contract_b_data)
    except Exception as e:
        if temp_ais_file and os.path.exists(temp_ais_file):
            os.remove(temp_ais_file)
        raise HTTPException(status_code=400, detail=f"Contract B validation error: {e}")

    try:
        engine = VesselAttributionEngine(DEFAULT_CONFIG)
        contract_c = engine.attribute_spill(
            contract_b=contract_b_data,
            ais_source=ais_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vessel attribution engine failed: {e}")
    finally:
        if temp_ais_file and os.path.exists(temp_ais_file):
            try:
                os.remove(temp_ais_file)
            except Exception:
                pass

    _enrich_contract_c_for_frontend(contract_c)
    return contract_c
@app.get("/api/attribute")
def vessel_attribution_get():
    """
    GET /api/attribute.

    Demo-safe endpoint used by Investigation.jsx.
    Does not require the real AIS/OpenDrift pipeline.
    """

    demo_a = get_demo_contract_a()

    return {
        "slick_id": demo_a.get("slick_id", "DEMO-SLICK-001"),
        "demo_mode": True,
        "status": "DEMO_FALLBACK",
        "message": (
            "AIS attribution is running in demonstration mode because "
            "the real drift/environmental pipeline is unavailable."
        ),
        "suspects": [
            {
                "mmsi": "412345678",
                "vessel_name": "Tanker A",
                "score": 0.87,
                "proximity_km": 2.1,
                "anomaly_flags": [
                    "loitering",
                    "ais_gap_10min"
                ],
                "evidence_text": (
                    "Demonstration suspect: vessel positioned near the "
                    "estimated spill origin with trajectory anomaly indicators."
                ),
            },
            {
                "mmsi": "412345679",
                "vessel_name": "Cargo B",
                "score": 0.64,
                "proximity_km": 5.8,
                "anomaly_flags": [
                    "speed_change"
                ],
                "evidence_text": (
                    "Demonstration suspect: vessel intersects the "
                    "investigation corridor with a speed-change indicator."
                ),
            },
            {
                "mmsi": "412345680",
                "vessel_name": "Tanker C",
                "score": 0.41,
                "proximity_km": 9.4,
                "anomaly_flags": [],
                "evidence_text": (
                    "Demonstration suspect: vessel was within the "
                    "investigation time window but has lower spatial correlation."
                ),
            },
        ],
    }

# ---------------------------------------------------------------------------
# 3. Contract C — Vessel Attribution
# ---------------------------------------------------------------------------

def build_demo_attribute_contract(
    contract_b: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Demo-safe Contract C.

    Uses the attribution response shape expected by
    Investigation.jsx.

    IMPORTANT:
    These are demonstration ranking values only.
    They are not presented as real AIS-derived attribution.
    """

    return {
        "slick_id": contract_b.get(
            "slick_id",
            "DEMO-SLICK-001"
        ),

        "demo_mode": True,

        "status": "DEMO_FALLBACK",

        "message": (
            "AIS attribution is running in demonstration mode "
            "because the real drift/environmental pipeline "
            "is unavailable."
        ),

        "suspects": [
            {
                "mmsi": "412345678",
                "vessel_name": "Tanker A",
                "score": 0.87,
                "proximity_km": 2.1,
                "anomaly_flags": [
                    "loitering",
                    "ais_gap_10min",
                ],
                "evidence_text": (
                    "Demonstration suspect: vessel positioned "
                    "near the estimated spill origin with "
                    "trajectory anomaly indicators."
                ),
            },
            {
                "mmsi": "412345679",
                "vessel_name": "Cargo B",
                "score": 0.64,
                "proximity_km": 5.8,
                "anomaly_flags": [
                    "speed_change",
                ],
                "evidence_text": (
                    "Demonstration suspect: vessel intersects "
                    "the investigation corridor with a "
                    "speed-change indicator."
                ),
            },
            {
                "mmsi": "412345680",
                "vessel_name": "Tanker C",
                "score": 0.41,
                "proximity_km": 9.4,
                "anomaly_flags": [],
                "evidence_text": (
                    "Demonstration suspect: vessel was within "
                    "the investigation time window but has "
                    "lower spatial correlation."
                ),
            },
        ],
    }


@app.post("/api/attribute")
async def vessel_attribution_post(request: Request):
    """
    POST /api/attribute.

    Executes real Member 3 AIS attribution when possible.
    Falls back gracefully when the drift/environmental
    dependency is unavailable.
    """

    content_type = request.headers.get("content-type", "")

    ais_path = str(DEFAULT_AIS_PATH)
    temp_ais_file = None
    contract_b_data = None

    if "multipart/form-data" in content_type:
        form = await request.form()

        raw_b = form.get("contract_b")

        if not raw_b:
            raise HTTPException(
                status_code=400,
                detail="Missing required 'contract_b'.",
            )

        if isinstance(raw_b, str):
            try:
                contract_b_data = json.loads(raw_b)
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid contract_b JSON: {exc}",
                )

        elif isinstance(raw_b, dict):
            contract_b_data = raw_b

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid contract_b payload format.",
            )

        ais_upload = form.get("ais_file")

        if (
            ais_upload
            and hasattr(ais_upload, "read")
            and getattr(ais_upload, "filename", None)
        ):
            content = await ais_upload.read()

            if content:
                tmp = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".csv",
                )
                tmp.write(content)
                tmp.flush()
                tmp.close()

                ais_path = tmp.name
                temp_ais_file = tmp.name

    else:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON payload: {exc}",
            )

        if (
            isinstance(body, dict)
            and isinstance(body.get("contract_b"), dict)
        ):
            contract_b_data = body["contract_b"]
        else:
            contract_b_data = body

    if not isinstance(contract_b_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Contract B payload must be a JSON object.",
        )

    # Validate Contract B.
    try:
        ContractBInput(**contract_b_data)
    except Exception as exc:
        # Demo fallback is only appropriate for a structurally valid
        # Contract B, so don't hide malformed client input.
        if temp_ais_file and os.path.exists(temp_ais_file):
            os.remove(temp_ais_file)

        raise HTTPException(
            status_code=400,
            detail=f"Contract B validation error: {exc}",
        )

    try:
        # Real Member 3 attribution.
        engine = VesselAttributionEngine(DEFAULT_CONFIG)

        contract_c = engine.attribute_spill(
            contract_b=contract_b_data,
            ais_source=ais_path,
        )

        _enrich_contract_c_for_frontend(contract_c)

        contract_c["demo_mode"] = False

        return contract_c

    except Exception as exc:
        print(
            "[MARIS] Real AIS attribution unavailable. "
            f"Using fallback. "
            f"{type(exc).__name__}: {exc}"
        )

        return build_demo_attribute_contract(
            contract_b_data
        )

    finally:
        if temp_ais_file and os.path.exists(temp_ais_file):
            try:
                os.remove(temp_ais_file)
            except Exception:
                pass


@app.get("/api/attribute")
def vessel_attribution_get():
    """
    GET /api/attribute.

    Attempts the real drift + AIS pipeline.
    Falls back to a dashboard-safe Contract C.
    """

    demo_a = get_demo_contract_a()

    # First try real drift.
    try:
        contract_b = forecast_drift(
            slick_polygon=demo_a,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=25,
        )

        if (
            isinstance(contract_b, dict)
            and not contract_b.get("error")
        ):
            contract_b["slick_id"] = demo_a["slick_id"]

            engine = VesselAttributionEngine(
                DEFAULT_CONFIG
            )

            contract_c = engine.attribute_spill(
                contract_b=contract_b,
                ais_source=str(DEFAULT_AIS_PATH),
            )

            _enrich_contract_c_for_frontend(contract_c)

            contract_c["demo_mode"] = False

            return contract_c

    except Exception as exc:
        print(
            "[MARIS] Real attribution unavailable. "
            f"Using fallback. "
            f"{type(exc).__name__}: {exc}"
        )

    # Build compatible fallback Contract B first.
    fallback_b = build_demo_drift_contract(demo_a)

    # Then compatible fallback Contract C.
    return build_demo_attribute_contract(fallback_b)

# ---------------------------------------------------------------------------
# 4. Pipeline — End-to-End Orchestration (M1 -> M2 -> M3)
# ---------------------------------------------------------------------------

def build_demo_pipeline_contract(
    contract_a: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Builds a complete demo-safe M1 -> M2 -> M3 pipeline.
    """

    contract_b = build_demo_drift_contract(contract_a)

    contract_c = build_demo_attribute_contract(contract_b)

    return {
        "pipeline_status": "DEMO_FALLBACK",

        "demo_mode": True,

        "message": (
            "MARIS pipeline completed using real Member 1 "
            "detection with demo-safe Member 2 and Member 3 "
            "fallbacks."
        ),

        "contract_a": contract_a,

        "contract_b": contract_b,

        "contract_c": contract_c,
    }


@app.post("/api/pipeline")
async def run_pipeline_post(
    request: Request,
    demo: bool = Query(False),
):
    """
    POST /api/pipeline.

    Attempts the complete real pipeline:

        Member 1 -> Member 2 -> Member 3

    If Member 2 environmental data is unavailable,
    the pipeline returns a clearly labelled fallback
    rather than failing the complete API.
    """

    content_type = request.headers.get("content-type", "")

    is_demo = demo

    uploaded_sar = None
    uploaded_ais = None

    slick_id = None
    timestamp_utc = None

    temp_sar_file = None
    temp_ais_file = None

    try:

        # --------------------------------------------------
        # Read request
        # --------------------------------------------------

        if "multipart/form-data" in content_type:

            form = await request.form()

            if "demo" in form:
                demo_val = str(
                    form.get("demo")
                ).lower()

                is_demo = demo_val in (
                    "true",
                    "1",
                    "yes",
                )

            uploaded_sar = (
                form.get("sar_file")
                or form.get("file")
            )

            uploaded_ais = form.get("ais_file")

            slick_id = form.get("slick_id")

            timestamp_utc = form.get(
                "timestamp_utc"
            )

        elif "application/json" in content_type:

            try:
                body = await request.json()

                if isinstance(body, dict):

                    is_demo = body.get(
                        "demo",
                        is_demo,
                    )

                    slick_id = body.get(
                        "slick_id"
                    )

                    timestamp_utc = body.get(
                        "timestamp_utc"
                    )

            except Exception:
                pass

        # --------------------------------------------------
        # Stage 1 — Member 1
        # --------------------------------------------------

        if is_demo:

            contract_a = get_demo_contract_a()

            contract_a["demo_mode"] = True

        elif (
            uploaded_sar is not None
            and hasattr(uploaded_sar, "read")
            and getattr(
                uploaded_sar,
                "filename",
                None,
            )
        ):

            model_file = Path(MODEL_PATH)

            if not model_file.exists():

                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Real U-Net model weights are "
                        "not available on this server."
                    ),
                )

            sar_bytes = await uploaded_sar.read()

            tmp_sar = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".tif",
            )

            tmp_sar.write(sar_bytes)
            tmp_sar.flush()
            tmp_sar.close()

            temp_sar_file = tmp_sar.name

            raw_detection = detect_spill(
                temp_sar_file
            )

            contract_a = format_contract_a(
                detection_result=raw_detection,
                slick_id=(
                    slick_id
                    or "SLICK-SAR-001"
                ),
                timestamp_utc=timestamp_utc,
                image_path=temp_sar_file,
            )

            contract_a["demo_mode"] = False

        else:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing SAR GeoTIFF. "
                    "Set demo=true for demonstration mode."
                ),
            )

        # --------------------------------------------------
        # Validate Contract A
        # --------------------------------------------------

        try:
            ContractARequest(**contract_a)

        except Exception as exc:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Contract A validation error: {exc}"
                ),
            )

        # --------------------------------------------------
        # Stage 2 — Member 2
        # --------------------------------------------------

        try:

            contract_b = forecast_drift(
                slick_polygon=contract_a,
                seed_mode="centroid",
                backtrack_hours=12,
                forecast_hours=[6, 24],
                num_particles=25,
            )

            if (
                not isinstance(contract_b, dict)
                or contract_b.get("error")
            ):
                raise RuntimeError(
                    "Drift simulation returned an error."
                )

            contract_b["slick_id"] = (
                contract_a["slick_id"]
            )

            contract_b["demo_mode"] = (
                contract_a.get(
                    "demo_mode",
                    False,
                )
            )

        except Exception as exc:

            print(
                "[MARIS] Pipeline drift stage "
                "unavailable. Using fallback. "
                f"{type(exc).__name__}: {exc}"
            )

            return build_demo_pipeline_contract(
                contract_a
            )

        # --------------------------------------------------
        # Validate Contract B
        # --------------------------------------------------

        try:
            ContractBInput(**contract_b)

        except Exception as exc:

            print(
                "[MARIS] Contract B schema validation "
                f"failed: {exc}"
            )

            return build_demo_pipeline_contract(
                contract_a
            )

        # --------------------------------------------------
        # Stage 3 — Member 3
        # --------------------------------------------------

        ais_path = str(DEFAULT_AIS_PATH)

        if (
            uploaded_ais
            and hasattr(uploaded_ais, "read")
            and getattr(
                uploaded_ais,
                "filename",
                None,
            )
        ):

            content = await uploaded_ais.read()

            if content:

                tmp_ais = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".csv",
                )

                tmp_ais.write(content)
                tmp_ais.flush()
                tmp_ais.close()

                ais_path = tmp_ais.name
                temp_ais_file = tmp_ais.name

        try:

            engine = VesselAttributionEngine(
                DEFAULT_CONFIG
            )

            contract_c = engine.attribute_spill(
                contract_b=contract_b,
                ais_source=ais_path,
            )

            _enrich_contract_c_for_frontend(
                contract_c
            )

            contract_c["demo_mode"] = False

        except Exception as exc:

            print(
                "[MARIS] Pipeline attribution stage "
                "unavailable. Using fallback. "
                f"{type(exc).__name__}: {exc}"
            )

            contract_c = build_demo_attribute_contract(
                contract_b
            )

        # --------------------------------------------------
        # Success
        # --------------------------------------------------

        return {
            "pipeline_status": "SUCCESS",

            "demo_mode": (
                contract_a.get(
                    "demo_mode",
                    False,
                )
                or contract_b.get(
                    "demo_mode",
                    False,
                )
                or contract_c.get(
                    "demo_mode",
                    False,
                )
            ),

            "contract_a": contract_a,

            "contract_b": contract_b,

            "contract_c": contract_c,
        }

    finally:

        if (
            temp_sar_file
            and os.path.exists(temp_sar_file)
        ):
            try:
                os.remove(temp_sar_file)
            except Exception:
                pass

        if (
            temp_ais_file
            and os.path.exists(temp_ais_file)
        ):
            try:
                os.remove(temp_ais_file)
            except Exception:
                pass


@app.get("/api/pipeline")
def run_pipeline_get():
    """
    GET /api/pipeline.

    Dashboard-safe complete pipeline.
    """

    contract_a = get_demo_contract_a()

    return build_demo_pipeline_contract(
        contract_a
    )