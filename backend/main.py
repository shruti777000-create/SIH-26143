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

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

# Member 1
from backend.demo_fixture import get_demo_contract_a
from backend.oil_spill_detector import MODEL_PATH, detect_spill, format_contract_a

# Member 2
from module2_drift.api import ContractARequest
from module2_drift.drift_model import forecast_drift

# Member 3
from module3_ais.attribution_engine import VesselAttributionEngine
from module3_ais.config import DEFAULT_CONFIG
from module3_ais.schemas import ContractBInput
from module3_ais.validate_schema import validate_contract_c

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
    """Backwards-compatible GET endpoint returning the deterministic demo Contract A."""
    contract_a = get_demo_contract_a()
    contract_a["demo_mode"] = True
    return contract_a


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


@app.get("/api/drift")
def drift_forecast_get():
    """Backwards-compatible GET endpoint executing real drift model on the demo Contract A fixture."""
    demo_a = get_demo_contract_a()
    contract_b = forecast_drift(
        slick_polygon=demo_a,
        seed_mode="centroid",
        backtrack_hours=12,
        forecast_hours=[6, 24],
        num_particles=25,
    )
    if isinstance(contract_b, dict) and not contract_b.get("error"):
        contract_b["slick_id"] = demo_a["slick_id"]
    return contract_b


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

    # Validate Contract C
    is_valid_c, errors_c = validate_contract_c(contract_c)
    if not is_valid_c:
        raise HTTPException(status_code=500, detail=f"Generated Contract C schema error: {errors_c}")

    _enrich_contract_c_for_frontend(contract_c)
    return contract_c


@app.get("/api/attribute")
def vessel_attribution_get():
    """Backwards-compatible GET endpoint executing real drift + attribution on demo fixtures."""
    demo_a = get_demo_contract_a()
    contract_b = forecast_drift(
        slick_polygon=demo_a,
        seed_mode="centroid",
        backtrack_hours=12,
        forecast_hours=[6, 24],
        num_particles=25,
    )
    contract_b["slick_id"] = demo_a["slick_id"]
    engine = VesselAttributionEngine(DEFAULT_CONFIG)
    contract_c = engine.attribute_spill(
        contract_b=contract_b,
        ais_source=str(DEFAULT_AIS_PATH),
    )
    is_valid_c, errors_c = validate_contract_c(contract_c)
    if not is_valid_c:
        raise HTTPException(status_code=500, detail=f"Generated Contract C schema error: {errors_c}")
    _enrich_contract_c_for_frontend(contract_c)
    return contract_c


# ---------------------------------------------------------------------------
# 4. Pipeline — End-to-End Orchestration (M1 -> M2 -> M3)
# ---------------------------------------------------------------------------

@app.post("/api/pipeline")
async def run_pipeline_post(
    request: Request,
    demo: bool = Query(False),
):
    """
    POST /api/pipeline:
    Chains Member 1 -> Member 2 -> Member 3:
    1. Obtains Contract A (from demo fixture or real SAR detection).
    2. Runs real Member 2 OpenDrift drift model -> Contract B.
    3. Runs real Member 3 attribution engine -> Contract C.
    Returns:
        {
            "pipeline_status": "SUCCESS",
            "demo_mode": bool,
            "contract_a": {...},
            "contract_b": {...},
            "contract_c": {...}
        }
    """
    content_type = request.headers.get("content-type", "")
    is_demo = demo
    uploaded_sar = None
    uploaded_ais = None
    slick_id = None
    timestamp_utc = None
    temp_ais_file = None
    temp_sar_file = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        if "demo" in form:
            demo_val = str(form.get("demo")).lower()
            is_demo = demo_val in ("true", "1", "yes")
        uploaded_sar = form.get("sar_file") or form.get("file")
        uploaded_ais = form.get("ais_file")
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

    # --- Stage 1: Member 1 Detection (Contract A) ---
    if is_demo:
        contract_a = get_demo_contract_a()
        demo_mode = True
    elif uploaded_sar is not None and hasattr(uploaded_sar, "read") and getattr(uploaded_sar, "filename", None):
        # Real SAR mode
        model_file = Path(MODEL_PATH)
        if not model_file.exists():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Real U-Net detection model weights ({MODEL_PATH}) are not available on this server. "
                    "Set demo=true to use the deterministic demonstration fixture."
                ),
            )
        sar_bytes = await uploaded_sar.read()
        tmp_s = tempfile.NamedTemporaryFile(delete=False, suffix=".tif")
        tmp_s.write(sar_bytes)
        tmp_s.flush()
        tmp_s.close()
        temp_sar_file = tmp_s.name

        try:
            raw_detection = detect_spill(temp_sar_file)
            contract_a = format_contract_a(
                detection_result=raw_detection,
                slick_id=slick_id or "SLICK-SAR-001",
                timestamp_utc=timestamp_utc,
                image_path=temp_sar_file,
            )
            demo_mode = False
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Member 1 detection failed: {e}")
        finally:
            if temp_sar_file and os.path.exists(temp_sar_file):
                try:
                    os.remove(temp_sar_file)
                except Exception:
                    pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required SAR GeoTIFF file upload for real pipeline mode. Set demo=true to use demonstration fixture.",
        )

    # Validate Contract A
    try:
        req_a = ContractARequest(**contract_a)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Contract A validation error: {e}")

    # --- Stage 2: Member 2 Drift Simulation (Contract B) ---
    try:
        contract_b = forecast_drift(
            slick_polygon=contract_a,
            seed_mode="centroid",
            backtrack_hours=12,
            forecast_hours=[6, 24],
            num_particles=25,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Member 2 simulation failed: {e}")

    if not isinstance(contract_b, dict) or contract_b.get("error"):
        reason = contract_b.get("reason", "Drift simulation failed") if isinstance(contract_b, dict) else "Unknown"
        raise HTTPException(status_code=400, detail=f"Member 2 drift error: {reason}")

    contract_b["slick_id"] = contract_a["slick_id"]

    # Validate Contract B
    try:
        ContractBInput(**contract_b)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Contract B schema error: {e}")

    # --- Stage 3: Member 3 AIS Attribution (Contract C) ---
    ais_path = str(DEFAULT_AIS_PATH)
    if uploaded_ais and hasattr(uploaded_ais, "read") and getattr(uploaded_ais, "filename", None):
        content = await uploaded_ais.read()
        if content:
            tmp_a = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            tmp_a.write(content)
            tmp_a.flush()
            tmp_a.close()
            ais_path = tmp_a.name
            temp_ais_file = tmp_a.name

    try:
        engine = VesselAttributionEngine(DEFAULT_CONFIG)
        contract_c = engine.attribute_spill(
            contract_b=contract_b,
            ais_source=ais_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Member 3 attribution failed: {e}")
    finally:
        if temp_ais_file and os.path.exists(temp_ais_file):
            try:
                os.remove(temp_ais_file)
            except Exception:
                pass

    # Validate Contract C
    is_valid_c, errors_c = validate_contract_c(contract_c)
    if not is_valid_c:
        raise HTTPException(status_code=500, detail=f"Member 3 Contract C schema error: {errors_c}")

    _enrich_contract_c_for_frontend(contract_c)

    return {
        "pipeline_status": "SUCCESS",
        "demo_mode": demo_mode,
        "contract_a": contract_a,
        "contract_b": contract_b,
        "contract_c": contract_c,
    }


@app.get("/api/pipeline")
def run_pipeline_get():
    """Backwards-compatible GET endpoint executing the complete pipeline in demo mode."""
    demo_a = get_demo_contract_a()
    contract_b = forecast_drift(
        slick_polygon=demo_a,
        seed_mode="centroid",
        backtrack_hours=12,
        forecast_hours=[6, 24],
        num_particles=25,
    )
    if isinstance(contract_b, dict) and not contract_b.get("error"):
        contract_b["slick_id"] = demo_a["slick_id"]
    engine = VesselAttributionEngine(DEFAULT_CONFIG)
    contract_c = engine.attribute_spill(
        contract_b=contract_b,
        ais_source=str(DEFAULT_AIS_PATH),
    )
    is_valid_c, errors_c = validate_contract_c(contract_c)
    if not is_valid_c:
        raise HTTPException(status_code=500, detail=f"Contract C schema error: {errors_c}")
    _enrich_contract_c_for_frontend(contract_c)
    return {
        "pipeline_status": "SUCCESS",
        "demo_mode": True,
        "contract_a": demo_a,
        "contract_b": contract_b,
        "contract_c": contract_c,
    }


