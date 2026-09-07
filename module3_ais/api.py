"""
Module 3: AIS & Intelligence - FastAPI Service & Endpoints
Exposes RESTful endpoints for spill attribution queries, integrating Contract B drift models
with candidate AIS traffic to rank potential suspect vessels.
"""

import os
import io
import json
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from module3_ais import __version__
from .config import DEFAULT_CONFIG, AISConfig
from .schemas import ContractBInput, ContractCOutput
from .preprocessor import load_ais_data, clean_ais_data
from .attribution_engine import VesselAttributionEngine

logger = logging.getLogger("module3_ais.api")

app = FastAPI(
    title="SIH 26143 - Member 3: AIS & Intelligence Engine",
    description=(
        "Autonomous marine vessel attribution engine correlating reverse Lagrangian oil spill backtrack "
        "origins (Contract B) with terrestrial/satellite AIS feeds to identify, rank, and generate explainable "
        "evidence against potential suspect ships."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configurable CORS Middleware for frontend integration
cors_origins_env = os.environ.get("CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    summary="Service Health Check",
    description="Returns the operational status, module identifier, and semantic version of the attribution engine.",
    tags=["System"]
)
def health_check() -> Dict[str, str]:
    """Basic health check endpoint returning service status and module version."""
    return {
        "status": "ok",
        "module": "member3_ais",
        "version": __version__
    }


@app.post(
    "/api/attribute",
    response_model=ContractCOutput,
    summary="Correlate Spill and Attribute Potential Suspect Vessels",
    description=(
        "Ingests Contract B drift modeling output (JSON) and candidate AIS track observations (CSV upload), "
        "executes spatio-temporal filtering, per-vessel trajectory reconstruction, Isolation Forest behavioral "
        "anomaly detection, and multi-criteria weighted threat scoring, returning standardized Contract C intelligence."
    ),
    response_description="Contract C payload containing ranked potential suspect vessels, threat tiers, and evidence packages.",
    tags=["Attribution"]
)
async def attribute_spill_api(
    ais_file: UploadFile = File(
        ...,
        description="CSV file containing AIS messages (mandatory columns: timestamp, mmsi, latitude, longitude, sog, cog)"
    ),
    contract_b: str = Form(
        ...,
        description="Contract B JSON string containing slick_id, estimated_origin, and backtrack_track"
    )
) -> Dict[str, Any]:
    """
    Executes the end-to-end vessel attribution pipeline.
    """
    # 1. Validate AIS File Upload
    if not ais_file or not ais_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required AIS CSV file upload."
        )

    try:
        content_bytes = await ais_file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded AIS file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read uploaded AIS file content."
        )

    if not content_bytes or len(content_bytes.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded AIS file is empty."
        )

    # 2. Validate and Parse Contract B Input
    if not contract_b or not contract_b.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract B payload is required."
        )

    try:
        contract_b_dict = json.loads(contract_b)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed Contract B JSON: {str(e)}"
        )

    if not isinstance(contract_b_dict, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract B input must be a JSON object."
        )

    try:
        ContractBInput(**contract_b_dict)
    except ValidationError as ve:
        raise HTTPException(
            status_code=422,
            detail=f"Contract B schema validation failed: {ve.errors()}"
        )

    # 3. Ingest and Validate AIS Data
    try:
        text_stream = io.StringIO(content_bytes.decode("utf-8-sig"))
        raw_df = load_ais_data(text_stream)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to decode AIS file. Ensure it is UTF-8 encoded plain text."
        )
    except ValueError as ve:
        # e.g., missing mandatory canonical columns
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid AIS CSV format: {str(e)}"
        )

    if raw_df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AIS dataset contains no data rows."
        )

    # 4. Clean AIS Data
    clean_df = clean_ais_data(raw_df, DEFAULT_CONFIG)
    if clean_df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AIS dataset contains no valid records after coordinate, timestamp, and kinematic cleaning."
        )

    # 5. Execute Attribution Pipeline
    engine = VesselAttributionEngine(DEFAULT_CONFIG)
    try:
        contract_c_result = engine.attribute_spill(
            contract_b=contract_b_dict,
            ais_source=clean_df
        )
    except KeyError as ke:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing Contract B key: {str(ke)}"
        )
    except Exception as exc:
        # Mask internal Python stack traces for production security
        logger.exception("Unexpected error in vessel attribution pipeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during vessel attribution processing."
        )

    # 6. Check if any candidate vessels remained in search corridor
    ranked_suspects = contract_c_result.get("ranked_suspects", [])
    if len(ranked_suspects) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No vessels found within the spatio-temporal corridor of the estimated spill origin."
        )

    return contract_c_result
