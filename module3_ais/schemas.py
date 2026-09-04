"""
Module 3: AIS & Intelligence - Pydantic Data Schemas
Defines structured data contracts for AIS ingestion, Contract B validation,
and Contract C vessel attribution output.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EstimatedOriginModel(BaseModel):
    """Estimated spill origin from Contract B."""
    point: List[float] = Field(..., description="[longitude, latitude] coordinates of origin")
    time_utc: str = Field(..., description="ISO-8601 UTC timestamp of origin release")


class BacktrackTrackModel(BaseModel):
    """LineString backtrack path of spill from Contract B."""
    type: str = Field("LineString", description="GeoJSON geometry type")
    coordinates: List[List[float]] = Field(..., description="List of [lon, lat] waypoints")


class ContractBInput(BaseModel):
    """Unified drift output schema ingested from Member 2 (Contract B)."""
    slick_id: str
    estimated_origin: EstimatedOriginModel
    backtrack_track: Optional[BacktrackTrackModel] = None
    region: Optional[str] = None
    forecast_polygons: Optional[List[Dict[str, Any]]] = None


class AISRecord(BaseModel):
    """Individual AIS message record."""
    timestamp: str
    mmsi: int
    latitude: float
    longitude: float
    sog: float
    cog: float
    vessel_name: Optional[str] = None
    vessel_type: Optional[str] = None


class ClosestEncounter(BaseModel):
    """Closest point of approach metrics for a suspect vessel."""
    min_distance_to_origin_km: float
    min_distance_to_backtrack_km: Optional[float] = None
    closest_point_time_utc: str
    vessel_point_at_cpa: List[float] = Field(..., description="[longitude, latitude]")
    speed_at_cpa_knots: float


class SuspectScoreBreakdown(BaseModel):
    """Granular attribution score components."""
    spatial_proximity_score: float
    temporal_correlation_score: float
    trajectory_alignment_score: float
    behavioral_anomaly_score: float


class SuspectVessel(BaseModel):
    """Ranked suspect vessel profile."""
    rank: int
    mmsi: int
    vessel_name: Optional[str] = None
    vessel_type: Optional[str] = None
    composite_threat_score: float
    threat_level: str
    score_breakdown: SuspectScoreBreakdown
    closest_encounter: ClosestEncounter
    anomaly_indicators: List[str] = Field(default_factory=list)
    evidence_summary: str
    trajectory_geojson: Optional[Dict[str, Any]] = None


class ContractCOutput(BaseModel):
    """Final vessel attribution intelligence payload (Contract C)."""
    slick_id: str
    attribution_timestamp_utc: str
    spill_context: Dict[str, Any]
    suspect_summary: Dict[str, int]
    ranked_suspects: List[SuspectVessel]
    status: str = "COMPLETED"
