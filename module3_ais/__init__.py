"""
Module 3: AIS & Intelligence Engine (Vessel Attribution)
SIH Problem Statement 26143

Autonomous AIS preprocessing, per-vessel trajectory reconstruction,
behavioral anomaly detection (Isolation Forest), and spatio-temporal
oil slick origin attribution engine.
"""

from .config import AISConfig, DEFAULT_CONFIG
from .preprocessor import (
    load_ais_data,
    clean_ais_data,
    filter_by_spatiotemporal,
    filter_from_contract_b,
    haversine_distance_km,
    haversine_vectorized_km,
)
from .trajectory import (
    build_vessel_trajectories,
    trajectory_to_geojson_feature,
    trajectories_to_feature_collection,
)
from .features import (
    extract_vessel_features,
    extract_all_vessel_features,
    extract_features_from_contract_b,
    compute_heading_changes_deg,
    angular_difference_deg,
    point_to_backtrack_distance_km,
    compute_alignment_score,
    interpolate_backtrack_timestamps,
)

__all__ = [
    "AISConfig",
    "DEFAULT_CONFIG",
    "load_ais_data",
    "clean_ais_data",
    "filter_by_spatiotemporal",
    "filter_from_contract_b",
    "haversine_distance_km",
    "haversine_vectorized_km",
    "build_vessel_trajectories",
    "trajectory_to_geojson_feature",
    "trajectories_to_feature_collection",
    "extract_vessel_features",
    "extract_all_vessel_features",
    "extract_features_from_contract_b",
    "compute_heading_changes_deg",
    "angular_difference_deg",
    "point_to_backtrack_distance_km",
    "compute_alignment_score",
    "interpolate_backtrack_timestamps",
]

__version__ = "0.2.0"
