"""
Module 3: AIS & Intelligence - Vessel Trajectory Reconstruction
Reconstructs per-vessel trajectories, preserves internal latitude/longitude coordinates,
handles edge cases (single-point or stationary vessels), and exports standard GeoJSON
with strict [longitude, latitude] ordering for Contract C.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .preprocessor import haversine_distance_km


def build_vessel_trajectories(df: pd.DataFrame) -> Dict[int, pd.DataFrame]:
    """
    Groups cleaned AIS records by MMSI and sorts each vessel's trajectory chronologically.

    Internal columns preserved:
      - 'latitude'
      - 'longitude'
      - 'timestamp'
      - 'sog'
      - 'cog'

    Args:
        df: Cleaned AIS dataframe.

    Returns:
        Dict mapping MMSI (int) -> pd.DataFrame of that vessel's chronological points.
    """
    if df.empty:
        return {}

    trajectories: Dict[int, pd.DataFrame] = {}
    for mmsi, group in df.groupby("mmsi"):
        # Sort strictly chronologically and reset index
        sorted_group = group.sort_values(by="timestamp").reset_index(drop=True)
        trajectories[int(mmsi)] = sorted_group

    return trajectories


def trajectory_to_geojson_feature(df_vessel: pd.DataFrame) -> Dict[str, Any]:
    """
    Converts a single vessel's AIS trajectory DataFrame into a standard GeoJSON Feature.

    IMPORTANT COORDINATE RULE:
      Raw AIS input uses latitude/longitude.
      Internally preserved as 'latitude' and 'longitude'.
      Whenever generating GeoJSON coordinates for Contract C, use [longitude, latitude].

    Edge Cases:
      - Empty DataFrame: Feature with empty LineString geometry.
      - 1-Point Trajectory: Feature with Point geometry [lon, lat].
      - >= 2 Points: Feature with LineString geometry [[lon1, lat1], [lon2, lat2], ...].

    Args:
        df_vessel: Chronological trajectory DataFrame for a single MMSI.

    Returns:
        GeoJSON Feature dictionary.
    """
    if df_vessel.empty:
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": []},
            "properties": {
                "observation_count": 0,
                "status": "EMPTY_TRACK"
            }
        }

    mmsi_val = int(df_vessel["mmsi"].iloc[0])
    vessel_name = str(df_vessel["vessel_name"].iloc[0]) if "vessel_name" in df_vessel.columns else "UNKNOWN"
    vessel_type = str(df_vessel["vessel_type"].iloc[0]) if "vessel_type" in df_vessel.columns else "UNKNOWN"
    obs_count = len(df_vessel)

    # Format timestamps
    timestamps = [
        row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"])
        for _, row in df_vessel.iterrows()
    ]
    sog_vals = [round(float(row["sog"]), 2) if pd.notna(row["sog"]) else None for _, row in df_vessel.iterrows()]
    cog_vals = [round(float(row["cog"]), 1) if pd.notna(row["cog"]) else None for _, row in df_vessel.iterrows()]

    # Single-point edge case
    if obs_count == 1:
        lon = round(float(df_vessel["longitude"].iloc[0]), 5)
        lat = round(float(df_vessel["latitude"].iloc[0]), 5)
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]  # Strict [lon, lat]
            },
            "properties": {
                "mmsi": mmsi_val,
                "vessel_name": vessel_name,
                "vessel_type": vessel_type,
                "observation_count": 1,
                "timestamp": timestamps[0],
                "sog_knots": sog_vals[0],
                "cog_degrees": cog_vals[0],
                "is_single_point": True
            }
        }

    # >= 2 points: Construct LineString
    coordinates = [
        [round(float(row["longitude"]), 5), round(float(row["latitude"]), 5)]
        for _, row in df_vessel.iterrows()
    ]

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates  # Strict [lon, lat]
        },
        "properties": {
            "mmsi": mmsi_val,
            "vessel_name": vessel_name,
            "vessel_type": vessel_type,
            "observation_count": obs_count,
            "start_time_utc": timestamps[0],
            "end_time_utc": timestamps[-1],
            "timestamps": timestamps,
            "sog_knots": sog_vals,
            "cog_degrees": cog_vals,
            "is_single_point": False
        }
    }


def trajectories_to_feature_collection(trajectories: Dict[int, pd.DataFrame]) -> Dict[str, Any]:
    """
    Aggregates all vessel trajectory features into a GeoJSON FeatureCollection.

    Args:
        trajectories: Dict mapping MMSI -> DataFrame.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    features = [
        trajectory_to_geojson_feature(df_v)
        for df_v in trajectories.values()
    ]
    return {
        "type": "FeatureCollection",
        "features": features
    }
