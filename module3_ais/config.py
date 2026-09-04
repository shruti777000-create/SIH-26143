"""
Module 3: AIS & Intelligence - Configuration & Hyperparameters
Defines spatial thresholds, temporal windows, physical validation limits,
anomaly detection hyperparameters, and multi-criteria suspect ranking weights.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Tuple


# Physical & Geo-constants
EARTH_RADIUS_KM: float = 6371.0088

# Default Spatio-temporal corridor matching Contract B
DEFAULT_SPATIAL_RADIUS_KM: float = 50.0
DEFAULT_TEMPORAL_WINDOW_HOURS: float = 12.0

# Physical validation bounds for marine AIS messages
LATITUDE_BOUNDS: Tuple[float, float] = (-90.0, 90.0)
LONGITUDE_BOUNDS: Tuple[float, float] = (-180.0, 180.0)
SOG_BOUNDS_KNOTS: Tuple[float, float] = (0.0, 102.2)  # 102.3 is standard AIS "not available"
COG_BOUNDS_DEGREES: Tuple[float, float] = (0.0, 360.0)

# Multi-criteria Suspect Scoring Weights (Must sum to 1.0)
DEFAULT_WEIGHT_PROXIMITY: float = 0.40
DEFAULT_WEIGHT_TEMPORAL: float = 0.25
DEFAULT_WEIGHT_TRAJECTORY: float = 0.20
DEFAULT_WEIGHT_ANOMALY: float = 0.15

# Sub-weights for Trajectory Score (Alignment vs Cross-Track proximity)
DEFAULT_WEIGHT_TRAJ_ALIGNMENT: float = 0.50
DEFAULT_WEIGHT_TRAJ_CROSS_TRACK: float = 0.50

# Suspect Threat Level Classification Thresholds
DEFAULT_HIGH_THREAT_THRESHOLD: float = 0.70
DEFAULT_MEDIUM_THREAT_THRESHOLD: float = 0.40

# Scoring Decay Scales
DEFAULT_PROXIMITY_DECAY_KM: float = 15.0  # Characteristic exponential decay distance
DEFAULT_TEMPORAL_DECAY_MINUTES: float = 180.0  # Characteristic temporal decay window (3 hours)
DEFAULT_CORRIDOR_MAX_WIDTH_KM: float = 25.0  # Max corridor cross-track buffer

# Isolation Forest Anomaly Detection Defaults
DEFAULT_ANOMALY_RANDOM_STATE: int = 42
DEFAULT_ANOMALY_CONTAMINATION: float = 0.10


@dataclass
class AISConfig:
    """
    Configuration parameters for AIS preprocessing, anomaly detection,
    and multi-criteria vessel attribution scoring.
    """
    spatial_radius_km: float = DEFAULT_SPATIAL_RADIUS_KM
    temporal_window_hours: float = DEFAULT_TEMPORAL_WINDOW_HOURS
    earth_radius_km: float = EARTH_RADIUS_KM

    lat_bounds: Tuple[float, float] = LATITUDE_BOUNDS
    lon_bounds: Tuple[float, float] = LONGITUDE_BOUNDS
    sog_bounds: Tuple[float, float] = SOG_BOUNDS_KNOTS
    cog_bounds: Tuple[float, float] = COG_BOUNDS_DEGREES

    # Composite Scoring Weights (Must sum to 1.0)
    weight_proximity: float = DEFAULT_WEIGHT_PROXIMITY
    weight_temporal: float = DEFAULT_WEIGHT_TEMPORAL
    weight_trajectory: float = DEFAULT_WEIGHT_TRAJECTORY
    weight_anomaly: float = DEFAULT_WEIGHT_ANOMALY

    # Trajectory sub-weights
    weight_traj_alignment: float = DEFAULT_WEIGHT_TRAJ_ALIGNMENT
    weight_traj_cross_track: float = DEFAULT_WEIGHT_TRAJ_CROSS_TRACK

    # Decay & Scale Hyperparameters
    proximity_decay_km: float = DEFAULT_PROXIMITY_DECAY_KM
    proximity_decay_mode: str = "exponential"  # "exponential", "gaussian", or "linear"
    temporal_decay_minutes: float = DEFAULT_TEMPORAL_DECAY_MINUTES
    temporal_decay_mode: str = "exponential"  # "exponential" or "linear"
    corridor_max_width_km: float = DEFAULT_CORRIDOR_MAX_WIDTH_KM

    # Suspect classification thresholds
    high_threat_threshold: float = DEFAULT_HIGH_THREAT_THRESHOLD
    medium_threat_threshold: float = DEFAULT_MEDIUM_THREAT_THRESHOLD

    # Anomaly Model Hyperparameters
    anomaly_random_state: int = DEFAULT_ANOMALY_RANDOM_STATE
    anomaly_contamination: float = DEFAULT_ANOMALY_CONTAMINATION

    def validate_weights(self) -> None:
        """
        Validates that composite scoring weights sum to 1.0 within numerical precision.
        Raises ValueError if validation fails.
        """
        total = (
            self.weight_proximity
            + self.weight_temporal
            + self.weight_trajectory
            + self.weight_anomaly
        )
        if not math.isclose(total, 1.0, abs_tol=1e-5):
            raise ValueError(
                f"Composite attribution weights must sum to 1.0. Got: {total:.6f} "
                f"(proximity={self.weight_proximity}, temporal={self.weight_temporal}, "
                f"trajectory={self.weight_trajectory}, anomaly={self.weight_anomaly})"
            )

        traj_sub_total = self.weight_traj_alignment + self.weight_traj_cross_track
        if not math.isclose(traj_sub_total, 1.0, abs_tol=1e-5):
            raise ValueError(
                f"Trajectory sub-weights must sum to 1.0. Got: {traj_sub_total:.6f}"
            )


# Global default configuration instance (pre-validated)
DEFAULT_CONFIG = AISConfig()
DEFAULT_CONFIG.validate_weights()
