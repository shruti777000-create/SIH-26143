"""
Module 3: AIS & Intelligence - FastAPI Service & Endpoints
Exposes RESTful endpoints for spill attribution queries.
NOTE: Phase 1 Stub - Full attribution integration to be wired in Phase 2.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any

from .schemas import ContractBInput

app = FastAPI(
    title="AIS Vessel Attribution Service",
    description="SIH Problem Statement 26143 - Module 3 Attribution Engine API",
    version="0.1.0"
)


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok", "module": "module3_ais"}


@app.post("/api/attribute")
def attribute_vessel(payload: ContractBInput) -> Dict[str, Any]:
    """
    Vessel Attribution API endpoint.
    Ingests Contract B JSON and returns ranked suspects (Contract C).
    """
    return {
        "slick_id": payload.slick_id,
        "message": "Phase 1 Stub: /api/attribute endpoint created. Full AI scoring active in Phase 2.",
        "status": "STUB"
    }
