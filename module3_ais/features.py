"""
Module 3: AIS & Intelligence - Vessel Feature Engineering
Extracts kinematic, behavioral, spatial proximity, and backtrack alignment features
for every candidate vessel. Computes great-circle distances, cross-track corridors,
and handles edge cases (single-point vessels, stationary ships, heading wraparound 359°->1°).
"""

import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple
import numpy as np
import pandas as pd

from .config import AISConfig, DEFAULT_CONFIG, EARTH_RADIUS_KM
from .preprocessor import haversine_distance_km, haversine_vectorized_km


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates initial great-circle bearing from (lat1, lon1) to (lat2, lon2) in degrees [0, 360).

    Args:
        lat1, lon1: Origin coordinates in degrees.
        lat2, lon2: Destination coordinates in degrees.

    Returns:
        Compass bearing in degrees (0.0 to 360.0).
    """
    phi1, lam1 = math.radians(lat1), math.radians(lon1)
    phi2, lam2 = math.radians(lat2), math.radians(lon2)
    dlam = lam2 - lam1

    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)

    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def angular_difference_deg(h1: float, h2: float) -> float:
    """
    Computes minimum acute difference between two compass headings/courses in [0, 360).
    Properly handles 360° wraparound (e.g. 359° -> 1° evaluates to 2°).
    """
    return abs((h2 - h1 + 180.0) % 360.0 - 180.0)


def compute_heading_changes_deg(cog_series: pd.Series) -> np.ndarray:
    """
    Computes consecutive heading changes in degrees accounting for 360-degree wraparound.
    For example: 359° -> 1° yields 2.0°.
    """
    valid_cogs = cog_series.dropna().to_numpy(dtype=float)
    if len(valid_cogs) < 2:
        return np.array([0.0])

    diffs = np.diff(valid_cogs)
    wrapped = np.abs((diffs + 180.0) % 360.0 - 180.0)
    return wrapped


def point_to_segment_distance_km(
    lat_p: float,
    lon_p: float,
    lat_a: float,
    lon_a: float,
    lat_b: float,
    lon_b: float,
    earth_radius_km: float = EARTH_RADIUS_KM
) -> float:
    """
    Computes great-circle cross-track distance from point P to spherical segment AB.
    Uses spherical trigonometry without flat-Earth approximations.

    Args:
        lat_p, lon_p: Point coordinates in degrees.
        lat_a, lon_a: Segment start in degrees.
        lat_b, lon_b: Segment end in degrees.
        earth_radius_km: Earth radius in kilometers.

    Returns:
        Shortest distance in kilometers from P to segment AB.
    """
    # Distance from A to B
    d_ab_km = haversine_distance_km(lat_a, lon_a, lat_b, lon_b, earth_radius_km)
    if d_ab_km < 1e-5:
        # Segment is essentially a single point
        return haversine_distance_km(lat_p, lon_p, lat_a, lon_a, earth_radius_km)

    d_ap_km = haversine_distance_km(lat_a, lon_a, lat_p, lon_p, earth_radius_km)
    if d_ap_km < 1e-5:
        return 0.0

    # Spherical angular distances in radians
    d_ap_rad = d_ap_km / earth_radius_km
    d_ab_rad = d_ab_km / earth_radius_km

    # Bearings in radians
    theta_ab = math.radians(initial_bearing_deg(lat_a, lon_a, lat_b, lon_b))
    theta_ap = math.radians(initial_bearing_deg(lat_a, lon_a, lat_p, lon_p))

    # Cross-track distance (perpendicular offset from great circle through A & B)
    sin_xtd = math.sin(d_ap_rad) * math.sin(theta_ap - theta_ab)
    sin_xtd = min(1.0, max(-1.0, sin_xtd))
    xtd_rad = math.asin(sin_xtd)

    # Along-track distance from A along great circle
    cos_xtd = math.cos(xtd_rad)
    if abs(cos_xtd) < 1e-12:
        return abs(xtd_rad) * earth_radius_km

    cos_atd = math.cos(d_ap_rad) / cos_xtd
    cos_atd = min(1.0, max(-1.0, cos_atd))
    atd_rad = math.acos(cos_atd)

    # Check projection direction (whether P is ahead or behind A relative to AB)
    if math.cos(theta_ap - theta_ab) < 0:
        atd_rad = -atd_rad

    # Determine if projection falls between A and B
    if atd_rad <= 0.0:
        # P projects before A -> distance is to endpoint A
        return d_ap_km
    elif atd_rad >= d_ab_rad:
        # P projects past B -> distance is to endpoint B
        return haversine_distance_km(lat_p, lon_p, lat_b, lon_b, earth_radius_km)
    else:
        # P projects perpendicularly inside segment AB
        return abs(xtd_rad) * earth_radius_km


def point_to_backtrack_distance_km(
    lat_p: float,
    lon_p: float,
    backtrack_coords: List[List[float]],
    earth_radius_km: float = EARTH_RADIUS_KM
) -> float:
    """
    Computes minimum great-circle distance from point P to a Contract B LineString corridor.

    IMPORTANT:
      backtrack_coords format is strictly [[lon, lat], ...].
      Unpacks: lon = coord[0], lat = coord[1].

    Args:
        lat_p, lon_p: Point coordinates in degrees.
        backtrack_coords: List of [longitude, latitude] waypoints.
        earth_radius_km: Earth radius in km.

    Returns:
        Minimum perpendicular/endpoint distance in kilometers.
    """
    if not backtrack_coords:
        return 0.0

    if len(backtrack_coords) == 1:
        w_lon, w_lat = backtrack_coords[0][0], backtrack_coords[0][1]
        return haversine_distance_km(lat_p, lon_p, w_lat, w_lon, earth_radius_km)

    min_dist = float("inf")
    for i in range(len(backtrack_coords) - 1):
        lon_a, lat_a = backtrack_coords[i][0], backtrack_coords[i][1]
        lon_b, lat_b = backtrack_coords[i + 1][0], backtrack_coords[i + 1][1]

        seg_dist = point_to_segment_distance_km(
            lat_p=lat_p,
            lon_p=lon_p,
            lat_a=lat_a,
            lon_a=lon_a,
            lat_b=lat_b,
            lon_b=lon_b,
            earth_radius_km=earth_radius_km
        )
        if seg_dist < min_dist:
            min_dist = seg_dist

    return min_dist


def interpolate_backtrack_timestamps(
    backtrack_coords: List[List[float]],
    origin_time_utc: Union[str, pd.Timestamp],
    detection_time_utc: Optional[Union[str, pd.Timestamp]] = None,
    default_backtrack_hours: float = 12.0
) -> List[Tuple[float, float, pd.Timestamp]]:
    """
    Linearly interpolates timestamps across Contract B backtrack LineString waypoints.

    Contract B waypoints start at estimated_origin (Waypoint 0, index 0)
    and proceed chronologically to detection time (Waypoint N-1, index -1).

    Args:
        backtrack_coords: List of [longitude, latitude] waypoints.
        origin_time_utc: Timestamp at estimated origin (Waypoint 0).
        detection_time_utc: Optional detection timestamp (Waypoint N-1).
        default_backtrack_hours: Fallback duration if detection_time is not provided.

    Returns:
        List of tuples: (longitude, latitude, timestamp_utc).
    """
    if not backtrack_coords:
        return []

    origin_dt = pd.to_datetime(origin_time_utc, utc=True)
    if detection_time_utc is not None:
        det_dt = pd.to_datetime(detection_time_utc, utc=True)
        total_duration = det_dt - origin_dt
    else:
        total_duration = pd.Timedelta(hours=default_backtrack_hours)

    n_points = len(backtrack_coords)
    if n_points == 1:
        return [(backtrack_coords[0][0], backtrack_coords[0][1], origin_dt)]

    interpolated = []
    for i, pt in enumerate(backtrack_coords):
        fraction = i / (n_points - 1)
        pt_time = origin_dt + (total_duration * fraction)
        interpolated.append((pt[0], pt[1], pt_time))

    return interpolated


def compute_trajectory_distance_km(
    df_vessel: pd.DataFrame,
    earth_radius_km: float = EARTH_RADIUS_KM
) -> float:
    """Computes total cumulative distance traveled along consecutive track points in km."""
    if len(df_vessel) < 2:
        return 0.0

    lats = df_vessel["latitude"].to_numpy(dtype=float)
    lons = df_vessel["longitude"].to_numpy(dtype=float)

    total_dist = 0.0
    for i in range(len(lats) - 1):
        total_dist += haversine_distance_km(
            lats[i], lons[i], lats[i + 1], lons[i + 1], earth_radius_km
        )
    return total_dist


def compute_alignment_score(
    df_vessel: pd.DataFrame,
    backtrack_coords: Optional[List[List[float]]] = None
) -> float:
    """
    Computes trajectory/drift alignment score in [0.0, 1.0].
    Measures directional correlation between vessel heading/track and spill drift vector.

    Score interpretation:
      1.0 = Traveled in exact direction of drift line
      0.5 = Orthogonal / perpendicular to drift line
      0.0 = Directly opposing direction

    Args:
        df_vessel: Chronological trajectory of the vessel.
        backtrack_coords: Contract B backtrack waypoints [[lon, lat], ...].

    Returns:
        Alignment score float in [0.0, 1.0]. Defaults to 0.5 (neutral) if undetermined.
    """
    if not backtrack_coords or len(backtrack_coords) < 2 or df_vessel.empty:
        return 0.5

    # Drift vector: from origin (waypoint 0) to detection (waypoint -1)
    drift_origin_lon, drift_origin_lat = backtrack_coords[0][0], backtrack_coords[0][1]
    drift_end_lon, drift_end_lat = backtrack_coords[-1][0], backtrack_coords[-1][1]
    theta_drift = initial_bearing_deg(drift_origin_lat, drift_origin_lon, drift_end_lat, drift_end_lon)

    # Determine vessel heading
    theta_vessel = None
    if len(df_vessel) >= 2:
        # Net vessel travel vector
        v_start_lat = float(df_vessel["latitude"].iloc[0])
        v_start_lon = float(df_vessel["longitude"].iloc[0])
        v_end_lat = float(df_vessel["latitude"].iloc[-1])
        v_end_lon = float(df_vessel["longitude"].iloc[-1])

        net_dist_km = haversine_distance_km(v_start_lat, v_start_lon, v_end_lat, v_end_lon)
        if net_dist_km > 0.1:
            theta_vessel = initial_bearing_deg(v_start_lat, v_start_lon, v_end_lat, v_end_lon)

    # Fallback to mean valid COG if net travel is too small or single point
    if theta_vessel is None and "cog" in df_vessel.columns:
        valid_cogs = df_vessel["cog"].dropna()
        if not valid_cogs.empty:
            # Mean angle in compass coordinates via circular mean
            rads = np.radians(valid_cogs.to_numpy(dtype=float))
            mean_sin = np.nanmean(np.sin(rads))
            mean_cos = np.nanmean(np.cos(rads))
            if not (math.isclose(mean_sin, 0.0) and math.isclose(mean_cos, 0.0)):
                theta_vessel = (math.degrees(math.atan2(mean_sin, mean_cos)) + 360.0) % 360.0

    if theta_vessel is None:
        return 0.5

    delta_theta = angular_difference_deg(theta_vessel, theta_drift)
    # Directional cosine alignment normalized to [0.0, 1.0]
    alignment = (1.0 + math.cos(math.radians(delta_theta))) / 2.0
    return round(float(alignment), 4)


def extract_vessel_features(
    df_vessel: pd.DataFrame,
    origin_point: List[float],
    origin_time_utc: Union[str, pd.Timestamp],
    backtrack_coords: Optional[List[List[float]]] = None,
    detection_time_utc: Optional[Union[str, pd.Timestamp]] = None,
    stop_speed_threshold_knots: float = 0.5,
    earth_radius_km: float = EARTH_RADIUS_KM
) -> Dict[str, Any]:
    """
    Computes all target attribution features for a single vessel trajectory.

    Target features generated:
      - mmsi
      - min_distance_to_origin_km
      - avg_speed_knots
      - max_speed_knots
      - speed_std
      - total_track_distance_km
      - ais_observation_count
      - stop_count
      - avg_heading_change_deg
      - max_heading_change_deg
      - closest_point_time_utc
      - time_difference_minutes
      - cross_track_distance_km
      - trajectory_alignment_score

    Args:
        df_vessel: Chronological trajectory DataFrame for one vessel.
        origin_point: [longitude, latitude] of spill origin from Contract B.
        origin_time_utc: Spill release timestamp from Contract B.
        backtrack_coords: Optional Contract B LineString waypoints [[lon, lat], ...].
        detection_time_utc: Optional detection timestamp.
        stop_speed_threshold_knots: SOG cutoff for near-zero-speed observations.
        earth_radius_km: Earth radius in km.

    Returns:
        Dictionary of vessel-level features.
    """
    if df_vessel.empty:
        raise ValueError("Cannot extract features from empty vessel DataFrame.")

    # Contract B unpack: [longitude, latitude]
    origin_lon, origin_lat = float(origin_point[0]), float(origin_point[1])
    origin_dt = pd.to_datetime(origin_time_utc, utc=True)

    mmsi = int(df_vessel["mmsi"].iloc[0])
    obs_count = int(len(df_vessel))

    # 1. Proximity to Origin & Closest Point of Approach (CPA)
    lats = df_vessel["latitude"].to_numpy(dtype=float)
    lons = df_vessel["longitude"].to_numpy(dtype=float)
    distances_to_origin = haversine_vectorized_km(lats, lons, origin_lat, origin_lon, earth_radius_km)

    closest_idx = int(np.argmin(distances_to_origin))
    min_distance_to_origin_km = round(float(distances_to_origin[closest_idx]), 3)

    closest_ts = df_vessel["timestamp"].iloc[closest_idx]
    closest_point_time_utc = (
        closest_ts.isoformat() if hasattr(closest_ts, "isoformat") else str(closest_ts)
    )
    time_difference_minutes = round(float((closest_ts - origin_dt).total_seconds() / 60.0), 2)

    # 2. Speed / SOG Statistics
    if "sog" in df_vessel.columns and not df_vessel["sog"].dropna().empty:
        sogs = df_vessel["sog"].dropna().to_numpy(dtype=float)
        avg_speed_knots = round(float(np.mean(sogs)), 2)
        max_speed_knots = round(float(np.max(sogs)), 2)
        speed_std = round(float(np.std(sogs, ddof=1)), 2) if len(sogs) > 1 else 0.0
        stop_count = int(np.sum(sogs <= stop_speed_threshold_knots))

        # Speed change / acceleration statistics
        if len(sogs) > 1:
            speed_diffs = np.abs(np.diff(sogs))
            avg_speed_change = round(float(np.mean(speed_diffs)), 2)
            max_speed_change = round(float(np.max(speed_diffs)), 2)
        else:
            avg_speed_change = 0.0
            max_speed_change = 0.0
    else:
        avg_speed_knots = 0.0
        max_speed_knots = 0.0
        speed_std = 0.0
        stop_count = 0
        avg_speed_change = 0.0
        max_speed_change = 0.0

    # 3. Total Track Distance
    total_track_distance_km = round(compute_trajectory_distance_km(df_vessel, earth_radius_km), 3)

    # 4. Heading / COG Change Statistics (with 360° wraparound)
    if "cog" in df_vessel.columns and not df_vessel["cog"].dropna().empty:
        heading_changes = compute_heading_changes_deg(df_vessel["cog"])
        avg_heading_change_deg = round(float(np.mean(heading_changes)), 2)
        max_heading_change_deg = round(float(np.max(heading_changes)), 2)
    else:
        avg_heading_change_deg = 0.0
        max_heading_change_deg = 0.0

    # 5. Cross-track distance to Backtrack Corridor
    if backtrack_coords:
        # Check cross-track distance across all vessel points
        cross_dists = [
            point_to_backtrack_distance_km(lats[i], lons[i], backtrack_coords, earth_radius_km)
            for i in range(len(lats))
        ]
        cross_track_distance_km = round(float(min(cross_dists)), 3)
    else:
        cross_track_distance_km = min_distance_to_origin_km

    # 6. Trajectory / Drift Alignment Score
    trajectory_alignment_score = compute_alignment_score(df_vessel, backtrack_coords)

    # Optional metadata retention
    vessel_name = str(df_vessel["vessel_name"].iloc[0]) if "vessel_name" in df_vessel.columns else "UNKNOWN"
    vessel_type = str(df_vessel["vessel_type"].iloc[0]) if "vessel_type" in df_vessel.columns else "UNKNOWN"

    return {
        "mmsi": mmsi,
        "min_distance_to_origin_km": min_distance_to_origin_km,
        "avg_speed_knots": avg_speed_knots,
        "max_speed_knots": max_speed_knots,
        "speed_std": speed_std,
        "total_track_distance_km": total_track_distance_km,
        "ais_observation_count": obs_count,
        "stop_count": stop_count,
        "avg_heading_change_deg": avg_heading_change_deg,
        "max_heading_change_deg": max_heading_change_deg,
        "closest_point_time_utc": closest_point_time_utc,
        "time_difference_minutes": time_difference_minutes,
        "cross_track_distance_km": cross_track_distance_km,
        "trajectory_alignment_score": trajectory_alignment_score,
        "speed_change_avg_knots": avg_speed_change,
        "speed_change_max_knots": max_speed_change,
        "vessel_name": vessel_name,
        "vessel_type": vessel_type,
    }


def extract_all_vessel_features(
    df: pd.DataFrame,
    origin_point: List[float],
    origin_time_utc: Union[str, pd.Timestamp],
    backtrack_coords: Optional[List[List[float]]] = None,
    detection_time_utc: Optional[Union[str, pd.Timestamp]] = None,
    stop_speed_threshold_knots: float = 0.5,
    earth_radius_km: float = EARTH_RADIUS_KM
) -> pd.DataFrame:
    """
    Extracts vessel-level attribution features across all vessels in an AIS DataFrame.

    Returns:
        Clean DataFrame where each row corresponds to one unique MMSI.
    """
    if df.empty:
        # Return empty DataFrame with exact target schema
        return pd.DataFrame(columns=[
            "mmsi",
            "min_distance_to_origin_km",
            "avg_speed_knots",
            "max_speed_knots",
            "speed_std",
            "total_track_distance_km",
            "ais_observation_count",
            "stop_count",
            "avg_heading_change_deg",
            "max_heading_change_deg",
            "closest_point_time_utc",
            "time_difference_minutes",
            "cross_track_distance_km",
            "trajectory_alignment_score"
        ])

    rows = []
    for _, df_vessel in df.groupby("mmsi"):
        df_sorted = df_vessel.sort_values(by="timestamp").reset_index(drop=True)
        feat = extract_vessel_features(
            df_vessel=df_sorted,
            origin_point=origin_point,
            origin_time_utc=origin_time_utc,
            backtrack_coords=backtrack_coords,
            detection_time_utc=detection_time_utc,
            stop_speed_threshold_knots=stop_speed_threshold_knots,
            earth_radius_km=earth_radius_km
        )
        rows.append(feat)

    features_df = pd.DataFrame(rows)
    return features_df.sort_values(by="min_distance_to_origin_km").reset_index(drop=True)


def extract_features_from_contract_b(
    df: pd.DataFrame,
    contract_b: Dict[str, Any],
    detection_time_utc: Optional[Union[str, pd.Timestamp]] = None,
    config: AISConfig = DEFAULT_CONFIG
) -> pd.DataFrame:
    """
    Convenience wrapper to extract vessel features directly from a Contract B payload.

    Args:
        df: AIS DataFrame.
        contract_b: Contract B dictionary.
        detection_time_utc: Optional detection timestamp.
        config: AISConfig instance.

    Returns:
        pd.DataFrame of vessel attribution features.
    """
    est_origin = contract_b.get("estimated_origin", {})
    if "point" not in est_origin or "time_utc" not in est_origin:
        raise KeyError("Contract B must contain 'estimated_origin' with 'point' and 'time_utc'.")

    origin_point = est_origin["point"]
    origin_time_utc = est_origin["time_utc"]

    backtrack_track = contract_b.get("backtrack_track", {})
    backtrack_coords = backtrack_track.get("coordinates") if isinstance(backtrack_track, dict) else None

    return extract_all_vessel_features(
        df=df,
        origin_point=origin_point,
        origin_time_utc=origin_time_utc,
        backtrack_coords=backtrack_coords,
        detection_time_utc=detection_time_utc,
        earth_radius_km=config.earth_radius_km
    )
