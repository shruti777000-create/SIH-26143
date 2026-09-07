"""
Module 2: Geospatial & Drift Modeling - FastAPI REST Service
Exposes POST /api/drift accepting Contract A (ML slick detection)
and producing Contract B (Lagrangian backtrack origin + forward dispersion envelopes).

Startup::

    uvicorn module2_drift.api:app --reload --port 8000

or via the root entrypoint::

    python api.py
"""

import json
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .drift_model import forecast_drift
from .validate_schema import validate_drift_output

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Oil Spill Drift Modeling API",
    description=(
        "MARIS Module 2 API - Reverse Lagrangian trajectory backtracking (-12 h) "
        "to pinpoint spill origins and forward dispersion polygon forecasting "
        "(+6 h, +24 h) for vessel AIS attribution and incident response."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Exception Handlers - guarantee no raw 500 reaches the client
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    """
    Transforms Pydantic v2 validation errors into a structured HTTP 400
    with field-level detail so callers know exactly what to fix.
    """
    formatted = []
    for err in exc.errors():
        loc = " -> ".join(str(part) for part in err.get("loc", []))
        formatted.append({
            "field": loc,
            "message": err.get("msg"),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": True,
            "error_type": "MALFORMED_REQUEST",
            "reason": "Request body failed validation against Contract A schema.",
            "details": {"validation_errors": formatted},
        },
    )


@app.exception_handler(json.JSONDecodeError)
async def _json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    """Handles raw unparseable JSON payloads with HTTP 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": True,
            "error_type": "INVALID_JSON",
            "reason": f"Malformed JSON in request body: {exc}",
        },
    )


@app.exception_handler(Exception)
async def _catch_all_handler(request: Request, exc: Exception):
    """
    Last-resort guard: converts any unhandled exception into a 500 with a
    descriptive message instead of an empty or framework-default error body.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "error_type": "INTERNAL_SERVER_ERROR",
            "reason": f"An unexpected server error occurred: {type(exc).__name__}: {exc}",
            "details": {"traceback_hint": traceback.format_exc(limit=5)},
        },
    )


# ---------------------------------------------------------------------------
# Contract A - Input Schemas (Pydantic v2)
# ---------------------------------------------------------------------------

class PolygonGeometry(BaseModel):
    """GeoJSON Polygon geometry as defined in RFC 7946."""

    type: Literal["Polygon"] = Field(
        ..., description="GeoJSON geometry type. Must be 'Polygon'."
    )
    coordinates: List[List[List[float]]] = Field(
        ...,
        description=(
            "Linear rings: [[[lon, lat], ...]] with a closed boundary "
            "(first coordinate == last coordinate)."
        ),
    )

    @field_validator("coordinates")
    @classmethod
    def _validate_rings(cls, rings: List[List[List[float]]]) -> List[List[List[float]]]:
        if not rings:
            raise ValueError("Polygon coordinates must contain at least one linear ring.")
        for i, ring in enumerate(rings):
            if len(ring) < 4:
                raise ValueError(
                    f"Ring {i} must have at least 4 coordinate pairs (3 unique + 1 closing); "
                    f"got {len(ring)}."
                )
            if ring[0] != ring[-1]:
                raise ValueError(
                    f"Ring {i} is not closed: first coordinate {ring[0]} "
                    f"!= last coordinate {ring[-1]}."
                )
            for j, pt in enumerate(ring):
                if len(pt) < 2:
                    raise ValueError(f"Ring {i}, vertex {j} must be [lon, lat]; got {pt}.")
                lon, lat = pt[0], pt[1]
                if not (-180.0 <= lon <= 180.0):
                    raise ValueError(
                        f"Ring {i}, vertex {j}: longitude {lon} is outside [-180, 180]."
                    )
                if not (-90.0 <= lat <= 90.0):
                    raise ValueError(
                        f"Ring {i}, vertex {j}: latitude {lat} is outside [-90, 90]."
                    )
        return rings


class ContractARequest(BaseModel):
    """
    Contract A - Detection payload from the SAR / optical ML pipeline (Module 1).

    Required fields
    ---------------
    slick_id        Unique detection identifier.
    timestamp_utc   ISO 8601 UTC timestamp of detection (e.g. '2026-09-04T12:00:00Z').
    geometry        GeoJSON Polygon defining the slick boundary.

    Optional fields (sensible defaults provided)
    --------------------------------------------
    area_km2        Surface area in km2. Informational; not used by the physics model.
    confidence      ML confidence score in [0.0, 1.0]. Informational.
    seed_mode       'distributed' (default) | 'centroid'.
    backtrack_hours Reverse-tracking window in hours [1-72]. Default 12.
    forecast_hours  Forward forecast horizons. Default [6, 24].
    num_particles   Lagrangian particle count [5-1000]. Default 100.
    oil_type        Oil product label for weathering model. Default 'GENERIC MEDIUM CRUDE'.
    """

    slick_id: str = Field(
        ...,
        min_length=1,
        examples=["SLICK-AS-MUMBAI-20260904-001"],
        description="Unique slick detection identifier.",
    )
    timestamp_utc: str = Field(
        ...,
        examples=["2026-09-04T12:00:00Z"],
        description="ISO 8601 UTC timestamp of detection.",
    )
    geometry: PolygonGeometry = Field(
        ..., description="GeoJSON Polygon defining the slick boundary."
    )
    area_km2: Optional[float] = Field(
        None,
        ge=0.0,
        examples=[0.25],
        description="Surface area in square kilometres (informational).",
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        examples=[0.94],
        description="ML detection confidence score (0.0-1.0).",
    )

    # Drift tuning parameters - all optional with sensible defaults
    seed_mode: Optional[Literal["distributed", "centroid"]] = Field(
        "distributed",
        description="Particle seeding strategy.",
    )
    backtrack_hours: Optional[int] = Field(
        12,
        ge=1,
        le=72,
        description="Reverse-tracking window in hours (1-72).",
    )
    forecast_hours: Optional[List[int]] = Field(
        [6, 24],
        description="Forward forecast horizons in hours. Default [6, 24].",
    )
    num_particles: Optional[int] = Field(
        100,
        ge=5,
        le=1000,
        description="Lagrangian simulation particle count (5-1000).",
    )
    oil_type: Optional[str] = Field(
        "GENERIC MEDIUM CRUDE",
        min_length=1,
        description="Oil type label for weathering and transport modelling.",
    )

    # Ensemble parameters
    ensemble_size: Optional[int] = Field(
        5,
        ge=1,
        le=20,
        description="Number of independent ensemble members (1 = deterministic, default 5).",
    )
    position_jitter_m: Optional[float] = Field(
        250.0,
        ge=0.0,
        le=5000.0,
        description=(
            "Gaussian 1-sigma position offset in metres applied to ensemble "
            "members 1..N to sample initial-position uncertainty (default 250 m)."
        ),
    )
    horizontal_diffusivity: Optional[float] = Field(
        50.0,
        ge=0.0,
        le=500.0,
        description=(
            "Within-run turbulent diffusion coefficient in m^2/s "
            "(default 50; set 0 to disable stochastic spread)."
        ),
    )

    @field_validator("timestamp_utc")
    @classmethod
    def _validate_timestamp(cls, v: str) -> str:
        """Reject timestamps that cannot be parsed as ISO 8601."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"'{v}' is not a valid ISO 8601 timestamp. "
                "Expected format: '2026-09-04T12:00:00Z' or '2026-09-04T12:00:00+00:00'."
            )
        return v

    @field_validator("forecast_hours")
    @classmethod
    def _validate_forecast_hours(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("forecast_hours must contain at least one hour value.")
        for h in v:
            if h < 1 or h > 120:
                raise ValueError(
                    f"Each forecast horizon must be between 1 and 120 hours; got {h}."
                )
        return v


# ---------------------------------------------------------------------------
# Pipeline error_type -> HTTP status mapping
# ---------------------------------------------------------------------------

_ERROR_STATUS_MAP: Dict[str, int] = {
    # 400 - caller is responsible
    "INVALID_POLYGON": status.HTTP_400_BAD_REQUEST,
    "INVALID_TIMESTAMP": status.HTTP_400_BAD_REQUEST,
    "INVALID_PARAMETER": status.HTTP_400_BAD_REQUEST,
    "SPATIAL_OUT_OF_BOUNDS": status.HTTP_400_BAD_REQUEST,
    "TEMPORAL_OUT_OF_BOUNDS": status.HTTP_400_BAD_REQUEST,
    "LAND_INTERSECTION": status.HTTP_400_BAD_REQUEST,
    # 502 - upstream data / OpenDrift failure
    "DATASET_NOT_FOUND": status.HTTP_502_BAD_GATEWAY,
    "READER_INITIALIZATION_ERROR": status.HTTP_502_BAD_GATEWAY,
    "SIMULATION_FAILURE": status.HTTP_502_BAD_GATEWAY,
}


def _pipeline_error_response(result: Dict[str, Any]) -> JSONResponse:
    """Convert a forecast_drift() error dict into the right HTTP response."""
    err_type = result.get("error_type", "PIPELINE_ERROR")
    http_code = _ERROR_STATUS_MAP.get(err_type, status.HTTP_400_BAD_REQUEST)
    return JSONResponse(status_code=http_code, content=result)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    """Health-check confirming the service is live and its operational domain."""
    return {
        "status": "HEALTHY",
        "service": "MARIS Module 2 Drift Modeling Engine",
        "version": "1.0.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "default_region": "Arabian Sea (Maharashtra / Mumbai)",
        "default_bounding_box": [71.0, 18.0, 73.5, 20.0],
    }


@app.post(
    "/api/drift",
    tags=["Drift Modeling"],
    summary="Run Lagrangian drift pipeline for a detected oil slick",
    response_description="Contract B: estimated origin point, backtrack track, and forecast polygons.",
)
def run_drift_pipeline(payload: ContractARequest) -> JSONResponse:
    """
    POST /api/drift - Unified Drift Engine

    Accepts a Contract A detection payload and executes:

    1. Input validation - geometry topology, coordinate bounds, timestamp format.
    2. Reverse Lagrangian backtracking - traces the slick back backtrack_hours
       (default 12 h) to pinpoint the probable spill origin point and time.
    3. Forward dispersion forecasting - projects the slick envelope forward
       at each forecast_hours horizon (default +6 h and +24 h).
    4. Output schema validation - confirms the result matches Contract B exactly.

    Error mapping
    -------------
    Missing / malformed JSON fields     -> 400 MALFORMED_REQUEST
    Invalid polygon geometry            -> 400 INVALID_POLYGON
    Timestamp outside data coverage     -> 400 TEMPORAL_OUT_OF_BOUNDS
    Coordinates outside model domain    -> 400 SPATIAL_OUT_OF_BOUNDS
    Slick intersects land               -> 400 LAND_INTERSECTION
    NetCDF reader / OpenDrift crash     -> 502 SIMULATION_FAILURE
    Output fails Contract B schema      -> 500 SCHEMA_VALIDATION_ERROR
    """
    # -- 1. Call forecast_drift() -------------------------------------------
    result: Dict[str, Any] = forecast_drift(
        slick_polygon=payload.geometry.model_dump(),
        timestamp=payload.timestamp_utc,
        seed_mode=payload.seed_mode or "distributed",
        backtrack_hours=payload.backtrack_hours or 12,
        forecast_hours=payload.forecast_hours or [6, 24],
        num_particles=payload.num_particles or 100,
        oil_type=payload.oil_type or "GENERIC MEDIUM CRUDE",
        ensemble_size=payload.ensemble_size if payload.ensemble_size is not None else 5,
        position_jitter_m=payload.position_jitter_m if payload.position_jitter_m is not None else 250.0,
        horizontal_diffusivity=payload.horizontal_diffusivity if payload.horizontal_diffusivity is not None else 50.0,
    )

    # -- 2. Propagate pipeline errors as structured HTTP responses -----------
    if result.get("error"):
        return _pipeline_error_response(result)

    # -- 3. Stamp slick_id from Contract A so the caller can correlate -------
    result["slick_id"] = payload.slick_id

    # -- 4. Validate output against Contract B schema -----------------------
    is_valid, schema_errors = validate_drift_output(result)
    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "error_type": "SCHEMA_VALIDATION_ERROR",
                "reason": (
                    "The simulation completed but its output failed Contract B schema "
                    "validation. This is an internal pipeline bug - please report it."
                ),
                "details": {
                    "slick_id": payload.slick_id,
                    "schema_errors": schema_errors,
                },
            },
        )

    # -- 5. Return Contract B -----------------------------------------------
    return JSONResponse(status_code=status.HTTP_200_OK, content=result)
