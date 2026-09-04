"""
Module 3: AIS & Intelligence - Trajectory Construction
Builds per-vessel trajectories, computes segment metrics, and formats GeoJSON outputs.
NOTE: Phase 1 Stub - Full trajectory interpolation and smoothing to be completed in Phase 2.
"""

from typing import Dict, Any, List
import pandas as pd


def build_vessel_trajectories(df: pd.DataFrame) -> Dict[int, pd.DataFrame]:
    """
    Splits cleaned AIS dataframe into per-vessel trajectories sorted chronologically.

    Args:
        df: Cleaned AIS dataframe containing ['mmsi', 'timestamp', 'latitude', 'longitude', 'sog', 'cog'].

    Returns:
        Dict mapping MMSI (int) -> pd.DataFrame of that vessel's chronological trajectory.
    """
    trajectories = {}
    for mmsi, group in df.groupby("mmsi"):
        trajectories[int(mmsi)] = group.sort_values(by="timestamp").reset_index(drop=True)
    return trajectories


def trajectory_to_geojson_feature(df_vessel: pd.DataFrame) -> Dict[str, Any]:
    """
    Converts a single vessel's AIS trajectory DataFrame into a GeoJSON Feature.

    IMPORTANT COORDINATE RULE:
      Raw AIS columns are 'latitude' and 'longitude'.
      GeoJSON coordinates MUST be strictly formatted as [longitude, latitude].

    Args:
        df_vessel: Chronological trajectory DataFrame for one vessel.

    Returns:
        GeoJSON Feature dictionary with LineString geometry and kinematic properties.
    """
    if df_vessel.empty:
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": []},
            "properties": {}
        }

    # Strict GeoJSON [lon, lat] ordering
    coordinates = [
        [round(float(row["longitude"]), 5), round(float(row["latitude"]), 5)]
        for _, row in df_vessel.iterrows()
    ]

    timestamps = [
        row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"])
        for _, row in df_vessel.iterrows()
    ]
    sog_vals = [round(float(row["sog"]), 2) for _, row in df_vessel.iterrows()]
    cog_vals = [round(float(row["cog"]), 1) for _, row in df_vessel.iterrows()]

    mmsi_val = int(df_vessel["mmsi"].iloc[0])
    vessel_name = str(df_vessel["vessel_name"].iloc[0]) if "vessel_name" in df_vessel.columns else "UNKNOWN"

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        },
        "properties": {
            "mmsi": mmsi_val,
            "vessel_name": vessel_name,
            "timestamps": timestamps,
            "sog_knots": sog_vals,
            "cog_degrees": cog_vals
        }
    }
