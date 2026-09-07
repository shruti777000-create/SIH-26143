"""
Module 3: AIS & Intelligence Engine (Vessel Attribution)
SIH Problem Statement 26143

Autonomous AIS preprocessing, per-vessel trajectory reconstruction,
Isolation Forest behavioral anomaly detection, multi-criteria suspect ranking,
and explainable evidence generation.
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
from .anomaly_model import (
    AISAnomalyDetector,
    BEHAVIORAL_FEATURE_COLUMNS,
)
from .attribution_engine import (
    VesselAttributionEngine,
    compute_proximity_score,
    compute_temporal_score,
    compute_trajectory_score,
    compute_composite_threat_score,
    classify_threat_level,
)
from .evidence_generator import (
    generate_vessel_evidence_package,
)
from .validate_schema import (
    validate_contract_c,
)

__all__ = [
    # Config
    "AISConfig",
    "DEFAULT_CONFIG",
    # Preprocessor
    "load_ais_data",
    "clean_ais_data",
    "filter_by_spatiotemporal",
    "filter_from_contract_b",
    "haversine_distance_km",
    "haversine_vectorized_km",
    # Trajectory
    "build_vessel_trajectories",
    "trajectory_to_geojson_feature",
    "trajectories_to_feature_collection",
    # Features
    "extract_vessel_features",
    "extract_all_vessel_features",
    "extract_features_from_contract_b",
    "compute_heading_changes_deg",
    "angular_difference_deg",
    "point_to_backtrack_distance_km",
    "compute_alignment_score",
    "interpolate_backtrack_timestamps",
    # Anomaly Model
    "AISAnomalyDetector",
    "BEHAVIORAL_FEATURE_COLUMNS",
    # Attribution Engine
    "VesselAttributionEngine",
    "compute_proximity_score",
    "compute_temporal_score",
    "compute_trajectory_score",
    "compute_composite_threat_score",
    "classify_threat_level",
    # Evidence Generator
    "generate_vessel_evidence_package",
    # Validation
    "validate_contract_c",
]

__version__ = "0.3.0"
