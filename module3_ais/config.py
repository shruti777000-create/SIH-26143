"""
Module 3: AIS & Intelligence - Configuration & Hyperparameters
Defines spatial thresholds, temporal windows, physical validation limits,
and suspect threat ranking weights for vessel attribution.
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


# Physical & Geo-constants
EARTH_RADIUS_KM: float = 6371.0088

# Default Filter Thresholds (Spatio-temporal corridor matching Contract B)
DEFAULT_SPATIAL_RADIUS_KM: float = 50.0
DEFAULT_TEMPORAL_WINDOW_HOURS: float = 12.0

# Physical validation bounds for marine AIS messages
LATITUDE_BOUNDS: Tuple[float, float] = (-90.0, 90.0)
LONGITUDE_BOUNDS: Tuple[float, float] = (-180.0, 180.0)
SOG_BOUNDS_KNOTS: Tuple[float, float] = (0.0, 102.2)  # 102.3 is standard AIS "not available"
COG_BOUNDS_DEGREES: Tuple[float, float] = (0.0, 360.0)

# Default Multi-criteria Suspect Scoring Weights (Phase 2)
DEFAULT_WEIGHT_PROXIMITY: float = 0.35
DEFAULT_WEIGHT_TEMPORAL: float = 0.25
DEFAULT_WEIGHT_ALIGNMENT: float = 0.20
DEFAULT_WEIGHT_ANOMALY: float = 0.20


@dataclass
class AISConfig:
    """
    Configuration parameters for AIS preprocessing, spatial/temporal filtering,
    and vessel attribution scoring.
    """
    spatial_radius_km: float = DEFAULT_SPATIAL_RADIUS_KM
    temporal_window_hours: float = DEFAULT_TEMPORAL_WINDOW_HOURS
    earth_radius_km: float = EARTH_RADIUS_KM

    lat_bounds: Tuple[float, float] = LATITUDE_BOUNDS
    lon_bounds: Tuple[float, float] = LONGITUDE_BOUNDS
    sog_bounds: Tuple[float, float] = SOG_BOUNDS_KNOTS
    cog_bounds: Tuple[float, float] = COG_BOUNDS_DEGREES

    # Scoring weights (sum to 1.0)
    weight_proximity: float = DEFAULT_WEIGHT_PROXIMITY
    weight_temporal: float = DEFAULT_WEIGHT_TEMPORAL
    weight_alignment: float = DEFAULT_WEIGHT_ALIGNMENT
    weight_anomaly: float = DEFAULT_WEIGHT_ANOMALY

    # Suspect classification thresholds
    high_threat_threshold: float = 0.70
    medium_threat_threshold: float = 0.40


# Global default configuration instance
DEFAULT_CONFIG = AISConfig()
