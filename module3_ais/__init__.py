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

__all__ = [
    "AISConfig",
    "DEFAULT_CONFIG",
    "load_ais_data",
    "clean_ais_data",
    "filter_by_spatiotemporal",
    "filter_from_contract_b",
    "haversine_distance_km",
    "haversine_vectorized_km",
]

__version__ = "0.1.0"
