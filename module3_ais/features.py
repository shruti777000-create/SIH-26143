"""
Module 3: AIS & Intelligence - Vessel Feature Engineering
Computes kinematic and behavioral features (rate of turn, acceleration, speed anomalies,
loitering metrics, trajectory alignment) for Isolation Forest anomaly detection.
NOTE: Phase 1 Stub - To be fully implemented in Phase 2.
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np


def compute_vessel_kinematic_features(df_vessel: pd.DataFrame) -> pd.DataFrame:
    """
    Extracts trajectory-level and point-level kinematic features for one vessel:
      - acceleration / deceleration (delta SOG / delta t)
      - rate of turn (delta COG / delta t)
      - speed variation (std dev of SOG)
      - transmission gap duration (seconds between AIS pings)

    Args:
        df_vessel: Chronological trajectory DataFrame of a vessel.

    Returns:
        DataFrame enriched with kinematic feature columns.
    """
    df = df_vessel.copy().sort_values("timestamp").reset_index(drop=True)
    if len(df) < 2:
        df["acceleration_kn_per_hr"] = 0.0
        df["rate_of_turn_deg_per_hr"] = 0.0
        df["ping_gap_seconds"] = 0.0
        return df

    time_diff_hours = (df["timestamp"].diff().dt.total_seconds() / 3600.0).fillna(1.0)
    time_diff_hours = time_diff_hours.replace(0.0, 1e-4)

    sog_diff = df["sog"].diff().fillna(0.0)
    df["acceleration_kn_per_hr"] = sog_diff / time_diff_hours

    cog_diff = (df["cog"].diff().fillna(0.0) + 180.0) % 360.0 - 180.0
    df["rate_of_turn_deg_per_hr"] = cog_diff.abs() / time_diff_hours

    df["ping_gap_seconds"] = df["timestamp"].diff().dt.total_seconds().fillna(0.0)

    return df
