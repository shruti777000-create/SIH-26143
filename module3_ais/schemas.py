"""
Module 3: AIS & Intelligence - Pydantic Data Schemas
Defines structured data contracts for AIS ingestion, Contract B validation,
and Contract C vessel attribution output.
"""

from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


class EstimatedOriginModel(BaseModel):
    """Estimated spill origin from Contract B."""
    point: List[float] = Field(..., description="[longitude, latitude] coordinates of origin")
    time_utc: str = Field(..., description="ISO-8601 UTC timestamp of origin release")

    @field_validator("point")
    @classmethod
    def validate_point(cls, v: List[float]) -> List[float]:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            raise ValueError("estimated_origin.point must be a 2-element [longitude, latitude] list")
        lon, lat = float(v[0]), float(v[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError(f"Coordinates out of physical bounds [-180, 180], [-90, 90]: [{lon}, {lat}]")
        return [lon, lat]

    @field_validator("time_utc")
    @classmethod
    def validate_time_utc(cls, v: str) -> str:
        if not isinstance(v, str) or not (v.endswith("Z") or "+00:00" in v):
            raise ValueError("estimated_origin.time_utc must explicitly specify UTC zone ('Z' or '+00:00')")
        try:
            clean_t = v.replace("Z", "+00:00")
            datetime.fromisoformat(clean_t)
        except Exception as e:
            raise ValueError(f"Invalid ISO-8601 datetime: {v} ({e})")
        return v


class BacktrackTrackModel(BaseModel):
    """LineString backtrack path of spill from Contract B."""
    type: str = Field("LineString", description="GeoJSON geometry type")
    coordinates: List[List[float]] = Field(..., description="List of [lon, lat] waypoints")

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, v: List[List[float]]) -> List[List[float]]:
        if not isinstance(v, list) or len(v) < 1:
            raise ValueError("backtrack_track.coordinates must contain at least one waypoint")
        for idx, pt in enumerate(v):
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValueError(f"Waypoint {idx} must be a 2-element [lon, lat] list")
            lon, lat = float(pt[0]), float(pt[1])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError(f"Waypoint {idx} out of bounds: [{lon}, {lat}]")
        return v


class ContractBInput(BaseModel):
    """Unified drift output schema ingested from Member 2 (Contract B)."""
    slick_id: str = Field(..., min_length=1, description="Unique identifier of detected slick")
    estimated_origin: EstimatedOriginModel
    backtrack_track: BacktrackTrackModel
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
    evidence_package: Optional[Dict[str, Any]] = None
    evidence_summary: Optional[str] = None
    trajectory_geojson: Optional[Dict[str, Any]] = None


class ContractCOutput(BaseModel):
    """Final vessel attribution intelligence payload (Contract C)."""
    slick_id: str
    attribution_timestamp_utc: str
    spill_context: Dict[str, Any]
    suspect_summary: Dict[str, int]
    ranked_suspects: List[SuspectVessel]
    status: str = "COMPLETED"
