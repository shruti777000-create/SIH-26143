"""
Module 3: AIS & Intelligence - Preprocessor & Spatio-temporal Filter
Handles AIS ingestion, UTC timestamp normalization, coordinate & kinematic data cleaning,
vectorized Haversine distance calculations, and Contract B corridor filtering.
"""

import math
from typing import Dict, Any, Union, List, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AISConfig, DEFAULT_CONFIG


# Standard AIS Column Synonyms for flexible ingestion
COLUMN_SYNONYMS = {
    "timestamp": ["timestamp", "time", "time_utc", "datetime", "date_time", "msg_time", "t"],
    "mmsi": ["mmsi", "vessel_mmsi", "mmsi_num", "mmsi_id"],
    "latitude": ["latitude", "lat", "lat_deg", "y"],
    "longitude": ["longitude", "lon", "long", "lon_deg", "lng", "x"],
    "sog": ["sog", "speed", "speed_over_ground", "speed_knots", "v"],
    "cog": ["cog", "course", "course_over_ground", "course_deg", "heading_deg"],
}

REQUIRED_CANONICAL_COLUMNS = ["timestamp", "mmsi", "latitude", "longitude", "sog", "cog"]


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    earth_radius_km: float = DEFAULT_CONFIG.earth_radius_km
) -> float:
    """
    Computes great-circle distance between two geographic coordinates using Haversine formula.

    Args:
        lat1: Latitude of point 1 in degrees.
        lon1: Longitude of point 1 in degrees.
        lat2: Latitude of point 2 in degrees.
        lon2: Longitude of point 2 in degrees.
        earth_radius_km: Radius of the sphere in km (default 6371.0088 km).

    Returns:
        Great-circle distance in kilometers (float).
    """
    # Convert decimal degrees to radians
    phi1, lambda1 = math.radians(lat1), math.radians(lon1)
    phi2, lambda2 = math.radians(lat2), math.radians(lon2)

    delta_phi = phi2 - phi1
    delta_lambda = lambda2 - lambda1

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    # Clamp a to avoid numerical precision errors exceeding 1.0
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return earth_radius_km * c


def haversine_vectorized_km(
    lats: Union[pd.Series, np.ndarray],
    lons: Union[pd.Series, np.ndarray],
    target_lat: float,
    target_lon: float,
    earth_radius_km: float = DEFAULT_CONFIG.earth_radius_km
) -> np.ndarray:
    """
    Vectorized Haversine distance calculation against a single target reference point.

    Args:
        lats: Array or Series of latitudes in degrees.
        lons: Array or Series of longitudes in degrees.
        target_lat: Target latitude in degrees.
        target_lon: Target longitude in degrees.
        earth_radius_km: Mean Earth radius in kilometers.

    Returns:
        NumPy array of great-circle distances in kilometers.
    """
    lat_arr = np.radians(np.asarray(lats, dtype=np.float64))
    lon_arr = np.radians(np.asarray(lons, dtype=np.float64))
    t_lat = math.radians(target_lat)
    t_lon = math.radians(target_lon)

    delta_lat = lat_arr - t_lat
    delta_lon = lon_arr - t_lon

    a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat_arr) * math.cos(t_lat) * (np.sin(delta_lon / 2.0) ** 2)
    )
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius_km * c


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Maps varying input column names to canonical internal names."""
    df_renamed = df.copy()
    lower_cols = {str(c).strip().lower(): c for c in df.columns}
    
    mapping = {}
    for canonical, synonyms in COLUMN_SYNONYMS.items():
        found = False
        for syn in synonyms:
            if syn in lower_cols:
                mapping[lower_cols[syn]] = canonical
                found = True
                break
        if not found and canonical in lower_cols:
            mapping[lower_cols[canonical]] = canonical

    df_renamed.rename(columns=mapping, inplace=True)
    return df_renamed


def load_ais_data(
    source: Union[str, Path, pd.DataFrame],
    **read_csv_kwargs
) -> pd.DataFrame:
    """
    Loads raw AIS data from a file path or accepts an existing DataFrame.

    Required canonical AIS fields:
      - timestamp
      - mmsi
      - latitude
      - longitude
      - sog
      - cog

    Args:
        source: File path (str, Path) or pandas DataFrame.
        **read_csv_kwargs: Additional arguments passed to pd.read_csv.

    Returns:
        pd.DataFrame with normalized canonical column names.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    elif isinstance(source, (str, Path)):
        df = pd.read_csv(source, **read_csv_kwargs)
    else:
        raise TypeError(f"Expected file path or pd.DataFrame, received: {type(source).__name__}")

    df = _normalize_column_names(df)

    missing = [col for col in REQUIRED_CANONICAL_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"AIS input is missing mandatory columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    return df


def clean_ais_data(
    df: pd.DataFrame,
    config: AISConfig = DEFAULT_CONFIG
) -> pd.DataFrame:
    """
    Validates and cleans raw AIS data:
      1. Drops rows with missing or unparseable timestamps.
      2. Normalizes all timestamps to standard UTC datetime.
      3. Drops rows with missing or invalid MMSI (MMSI <= 0 or NaN).
      4. Validates coordinates: Latitude in [-90, 90], Longitude in [-180, 180].
      5. Validates kinematics: SOG >= 0 (negative SOG dropped), SOG <= 102.2 knots.
      6. Validates COG: COG in [0, 360].
      7. Deduplicates records with identical (MMSI, timestamp).
      8. Preserves internal columns as 'latitude' and 'longitude'.

    Args:
        df: DataFrame loaded via load_ais_data().
        config: AISConfig instance specifying thresholds.

    Returns:
        Cleaned, deduplicated, chronologically sorted pd.DataFrame.
    """
    cleaned = df.copy()

    # 1. Timestamp validation & UTC normalization
    cleaned["timestamp"] = pd.to_datetime(
        cleaned["timestamp"],
        utc=True,
        format="mixed",
        errors="coerce"
    )
    cleaned = cleaned.dropna(subset=["timestamp"])

    # 2. MMSI validation (Must be numeric and positive)
    cleaned["mmsi"] = pd.to_numeric(cleaned["mmsi"], errors="coerce")
    cleaned = cleaned.dropna(subset=["mmsi"])
    cleaned = cleaned[cleaned["mmsi"] > 0]
    cleaned["mmsi"] = cleaned["mmsi"].astype(np.int64)

    # 3. Coordinate validation
    cleaned["latitude"] = pd.to_numeric(cleaned["latitude"], errors="coerce")
    cleaned["longitude"] = pd.to_numeric(cleaned["longitude"], errors="coerce")
    cleaned = cleaned.dropna(subset=["latitude", "longitude"])

    min_lat, max_lat = config.lat_bounds
    min_lon, max_lon = config.lon_bounds
    coord_mask = (
        (cleaned["latitude"] >= min_lat) & (cleaned["latitude"] <= max_lat) &
        (cleaned["longitude"] >= min_lon) & (cleaned["longitude"] <= max_lon)
    )
    cleaned = cleaned[coord_mask]

    # 4. SOG validation (Negative SOG dropped, cap at physical AIS max)
    cleaned["sog"] = pd.to_numeric(cleaned["sog"], errors="coerce")
    cleaned = cleaned.dropna(subset=["sog"])
    min_sog, max_sog = config.sog_bounds
    sog_mask = (cleaned["sog"] >= min_sog) & (cleaned["sog"] <= max_sog)
    cleaned = cleaned[sog_mask]

    # 5. COG validation
    cleaned["cog"] = pd.to_numeric(cleaned["cog"], errors="coerce")
    cleaned = cleaned.dropna(subset=["cog"])
    min_cog, max_cog = config.cog_bounds
    cog_mask = (cleaned["cog"] >= min_cog) & (cleaned["cog"] <= max_cog)
    cleaned = cleaned[cog_mask]

    # 6. Deduplication on MMSI + timestamp (keep first occurrence)
    cleaned = cleaned.drop_duplicates(subset=["mmsi", "timestamp"], keep="first")

    # 7. Sort by MMSI and chronological order
    cleaned = cleaned.sort_values(by=["mmsi", "timestamp"]).reset_index(drop=True)

    return cleaned


def filter_by_spatiotemporal(
    df: pd.DataFrame,
    origin_point: List[float],
    origin_time_utc: Union[str, pd.Timestamp],
    spatial_radius_km: float = DEFAULT_CONFIG.spatial_radius_km,
    temporal_window_hours: float = DEFAULT_CONFIG.temporal_window_hours,
    earth_radius_km: float = DEFAULT_CONFIG.earth_radius_km
) -> pd.DataFrame:
    """
    Filters cleaned AIS records around a Contract B estimated origin point and time.

    IMPORTANT COORDINATE RULE:
      Contract B provides 'point' as [longitude, latitude].
      This function unpacks:
        origin_lon = origin_point[0]
        origin_lat = origin_point[1]
      While DataFrame columns are preserved as 'latitude' and 'longitude'.

    Args:
        df: Cleaned AIS DataFrame.
        origin_point: 2-element list [longitude, latitude] from Contract B.
        origin_time_utc: ISO-8601 string or Timestamp of spill origin.
        spatial_radius_km: Maximum radius from origin in kilometers (default: 50 km).
        temporal_window_hours: Symmetric time window in hours (default: ±12 hours).
        earth_radius_km: Mean Earth radius for Haversine distance.

    Returns:
        Filtered pd.DataFrame with an added 'distance_to_origin_km' column.
    """
    if len(origin_point) != 2:
        raise ValueError(
            f"origin_point must be a 2-element [longitude, latitude] list, got: {origin_point}"
        )

    # Note: Contract B format is strictly [longitude, latitude]
    origin_lon = float(origin_point[0])
    origin_lat = float(origin_point[1])

    # Convert origin_time to UTC Timestamp
    origin_dt = pd.to_datetime(origin_time_utc, utc=True)

    if df.empty:
        res = df.copy()
        res["distance_to_origin_km"] = pd.Series(dtype=float)
        res["time_diff_hours"] = pd.Series(dtype=float)
        return res

    working_df = df.copy()

    # 1. Temporal filter: abs(timestamp - origin_time) <= window
    delta_time = (working_df["timestamp"] - origin_dt).abs()
    temporal_mask = delta_time <= pd.Timedelta(hours=temporal_window_hours)
    time_filtered = working_df[temporal_mask].copy()

    if time_filtered.empty:
        time_filtered["distance_to_origin_km"] = pd.Series(dtype=float)
        time_filtered["time_diff_hours"] = pd.Series(dtype=float)
        return time_filtered

    # 2. Spatial filter: Haversine distance <= spatial_radius_km
    distances = haversine_vectorized_km(
        lats=time_filtered["latitude"],
        lons=time_filtered["longitude"],
        target_lat=origin_lat,
        target_lon=origin_lon,
        earth_radius_km=earth_radius_km
    )

    time_filtered["distance_to_origin_km"] = np.round(distances, 3)
    time_filtered["time_diff_hours"] = np.round(
        (time_filtered["timestamp"] - origin_dt).dt.total_seconds() / 3600.0, 3
    )

    spatial_mask = time_filtered["distance_to_origin_km"] <= spatial_radius_km
    result = time_filtered[spatial_mask].copy()

    return result.sort_values(by=["distance_to_origin_km"]).reset_index(drop=True)


def filter_from_contract_b(
    df: pd.DataFrame,
    contract_b: Dict[str, Any],
    spatial_radius_km: Optional[float] = None,
    temporal_window_hours: Optional[float] = None,
    config: AISConfig = DEFAULT_CONFIG
) -> pd.DataFrame:
    """
    Convenience wrapper to filter AIS data directly using a Contract B dictionary payload.

    Args:
        df: Cleaned AIS DataFrame.
        contract_b: Dictionary matching Contract B schema (e.g., sample_drift_output.json).
        spatial_radius_km: Override for spatial radius (default: from config).
        temporal_window_hours: Override for temporal window (default: from config).
        config: AISConfig fallback.

    Returns:
        Filtered pd.DataFrame with distance_to_origin_km.
    """
    est_origin = contract_b.get("estimated_origin")
    if not est_origin or "point" not in est_origin or "time_utc" not in est_origin:
        raise KeyError("Contract B must contain 'estimated_origin' with 'point' and 'time_utc'.")

    s_radius = spatial_radius_km if spatial_radius_km is not None else config.spatial_radius_km
    t_window = temporal_window_hours if temporal_window_hours is not None else config.temporal_window_hours

    return filter_by_spatiotemporal(
        df=df,
        origin_point=est_origin["point"],
        origin_time_utc=est_origin["time_utc"],
        spatial_radius_km=s_radius,
        temporal_window_hours=t_window,
        earth_radius_km=config.earth_radius_km
    )
