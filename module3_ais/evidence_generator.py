"""
Module 3: AIS & Intelligence - Explainable Forensic Evidence Generator
Generates verifiable, explainable factual summaries and legal evidence packages
for ranked candidate vessels. Never fabricates vessel metadata or asserts legal guilt.
"""

from typing import Dict, Any, List, Optional, Union
import pandas as pd
from .config import AISConfig, DEFAULT_CONFIG


def generate_vessel_evidence_package(
    row: Union[pd.Series, Dict[str, Any]],
    config: AISConfig = DEFAULT_CONFIG
) -> Dict[str, Any]:
    """
    Generates a factual, verifiable evidence package for a single candidate vessel.

    Rules:
      1. Every statement is strictly backed by calculated metrics.
      2. No vessel names, IMOs, flags, or types are invented if missing.
      3. Terminology refers to 'candidate vessel' or 'potential suspect', not proven guilt.

    Args:
        row: Series or dict containing vessel features and attribution scores.
        config: AISConfig instance.

    Returns:
        Dict containing summary, supporting facts, anomaly indicators, and recommended action.
    """
    mmsi = int(row.get("mmsi", 0))
    threat_level = str(row.get("threat_level", "LOW"))
    comp_score = float(row.get("composite_threat_score", 0.0))

    # Safely retrieve vessel metadata without fabricating
    raw_name = row.get("vessel_name")
    vessel_name = str(raw_name).strip() if (pd.notna(raw_name) and str(raw_name).strip() not in ["", "nan", "UNKNOWN"]) else None

    raw_type = row.get("vessel_type")
    vessel_type = str(raw_type).strip() if (pd.notna(raw_type) and str(raw_type).strip() not in ["", "nan", "UNKNOWN"]) else None

    # 1. Physical & Spatio-temporal Facts
    min_dist_km = float(row.get("min_distance_to_origin_km", 0.0))
    time_diff_min = float(row.get("time_difference_minutes", 0.0))
    closest_ts = str(row.get("closest_point_time_utc", ""))
    xtd_km = float(row.get("cross_track_distance_km", min_dist_km))
    alignment_score = float(row.get("trajectory_alignment_score", 0.5))

    factual_claims = []

    # Proximity statement
    factual_claims.append(f"Positioned {min_dist_km:.2f} km from the estimated spill origin.")

    # Temporal statement
    abs_min = abs(time_diff_min)
    if abs_min < 60.0:
        time_text = f"{abs_min:.1f} minutes"
    else:
        time_text = f"{abs_min / 60.0:.1f} hours"

    if time_diff_min >= 0:
        factual_claims.append(f"Closest point of approach occurred {time_text} after estimated discharge time.")
    else:
        factual_claims.append(f"Closest point of approach occurred {time_text} prior to estimated discharge time.")

    # Trajectory & corridor statements
    if xtd_km <= config.corridor_max_width_km:
        factual_claims.append(f"Traversed within {xtd_km:.2f} km of the historical backtrack drift corridor.")

    if alignment_score >= 0.75:
        factual_claims.append(f"Vessel course was directionally aligned with spill drift vector (alignment index: {alignment_score:.2f}).")
    elif alignment_score <= 0.25:
        factual_claims.append(f"Vessel course was opposed to spill drift vector (alignment index: {alignment_score:.2f}).")

    # 2. Behavioral & Kinematic Anomalies (Only generated when supported by data)
    anomaly_indicators = []
    speed_drop = float(row.get("speed_change_max_knots", 0.0))
    if speed_drop >= 6.0:
        anomaly_indicators.append(f"Unusual speed reduction detected (deceleration of {speed_drop:.1f} knots)")

    stop_count = int(row.get("stop_count", 0))
    if stop_count > 0:
        anomaly_indicators.append(f"Vessel stoppage/loitering detected ({stop_count} observations at near-zero speed)")

    max_turn = float(row.get("max_heading_change_deg", 0.0))
    if max_turn >= 45.0:
        anomaly_indicators.append(f"Sharp course alteration observed ({max_turn:.1f}° heading change)")

    is_anom = bool(row.get("is_behavioral_anomaly", False))
    anom_score = float(row.get("behavioral_anomaly_score", 0.0))
    if is_anom or anom_score >= 0.65:
        anomaly_indicators.append(f"Navigation pattern flagged as anomalous by Isolation Forest (score: {anom_score:.2f})")

    # 3. Formulate Non-Accusatory Investigative Narrative
    vessel_id_str = f"'{vessel_name}' (MMSI {mmsi})" if vessel_name else f"MMSI {mmsi}"
    if vessel_type:
        vessel_id_str += f" [Type: {vessel_type}]"

    summary_paragraphs = [
        f"Candidate vessel {vessel_id_str} has been ranked as a potential suspect "
        f"(Threat Level: {threat_level}, Composite Score: {comp_score:.3f})."
    ]
    summary_paragraphs.extend(factual_claims)
    if anomaly_indicators:
        summary_paragraphs.append("Behavioral anomalies identified: " + "; ".join(anomaly_indicators) + ".")

    full_summary = " ".join(summary_paragraphs)

    # 4. Recommended Action
    if threat_level == "HIGH":
        action = "Prioritize for Port State Control / Coast Guard physical inspection and logbook audit."
    elif threat_level == "MEDIUM":
        action = "Review destination port schedule and correlate with satellite radar imagery."
    else:
        action = "Low correlation observed; maintain in maritime record for situational awareness."

    return {
        "summary": full_summary,
        "factual_observations": factual_claims,
        "anomaly_indicators": anomaly_indicators,
        "recommended_action": action,
        "vessel_metadata": {
            "mmsi": mmsi,
            "vessel_name": vessel_name,
            "vessel_type": vessel_type,
        }
    }
