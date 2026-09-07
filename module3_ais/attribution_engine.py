"""
Module 3: AIS & Intelligence - Multi-Criteria Vessel Attribution Engine
Combines spatial proximity, temporal correlation, trajectory corridor alignment,
and Isolation Forest behavioral anomaly detection to produce ranked potential suspects (Contract C).
"""

import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from .config import AISConfig, DEFAULT_CONFIG
from .preprocessor import (
    load_ais_data,
    clean_ais_data,
    filter_by_spatiotemporal,
    filter_from_contract_b,
    haversine_distance_km,
)
from .trajectory import (
    build_vessel_trajectories,
    trajectory_to_geojson_feature,
)
from .features import (
    extract_all_vessel_features,
    point_to_backtrack_distance_km,
)
from .anomaly_model import AISAnomalyDetector
from .evidence_generator import generate_vessel_evidence_package


def compute_proximity_score(
    min_distance_km: float,
    config: AISConfig = DEFAULT_CONFIG
) -> float:
    """
    Computes normalized proximity score in [0.0, 1.0].
    Decreases monotonically as distance from estimated origin increases.
    """
    d = max(0.0, float(min_distance_km))

    if config.proximity_decay_mode == "linear":
        max_r = config.spatial_radius_km
        score = max(0.0, 1.0 - (d / max_r))
    elif config.proximity_decay_mode == "gaussian":
        sigma = config.proximity_decay_km
        score = math.exp(- (d ** 2) / (2.0 * (sigma ** 2)))
    else:
        # Default: exponential decay
        scale = config.proximity_decay_km
        score = math.exp(- d / scale)

    return round(float(np.clip(score, 0.0, 1.0)), 4)


def compute_temporal_score(
    time_difference_minutes: float,
    config: AISConfig = DEFAULT_CONFIG
) -> float:
    """
    Computes normalized temporal correlation score in [0.0, 1.0].
    Highest (1.0) when vessel CPA coincides with estimated release time (diff = 0 min),
    decaying as absolute time difference increases.
    """
    delta_t = abs(float(time_difference_minutes))

    if config.temporal_decay_mode == "linear":
        max_min = config.temporal_window_hours * 60.0
        score = max(0.0, 1.0 - (delta_t / max_min))
    else:
        # Default: exponential decay
        scale = config.temporal_decay_minutes
        score = math.exp(- delta_t / scale)

    return round(float(np.clip(score, 0.0, 1.0)), 4)


def compute_trajectory_score(
    trajectory_alignment_score: float,
    cross_track_distance_km: float,
    config: AISConfig = DEFAULT_CONFIG
) -> float:
    """
    Computes normalized trajectory score in [0.0, 1.0].
    Combines directional course alignment with cross-track proximity to the backtrack corridor.
    Does NOT confuse trajectory alignment with proximity to origin.
    """
    align = float(np.clip(trajectory_alignment_score, 0.0, 1.0))
    xtd = max(0.0, float(cross_track_distance_km))

    # Cross-track corridor score (1.0 on centerline, 0.0 at outer boundary)
    corridor_w = config.corridor_max_width_km
    xtd_score = max(0.0, 1.0 - (xtd / corridor_w))

    traj_score = (
        config.weight_traj_alignment * align
        + config.weight_traj_cross_track * xtd_score
    )
    return round(float(np.clip(traj_score, 0.0, 1.0)), 4)


def compute_composite_threat_score(
    proximity_score: float,
    temporal_score: float,
    trajectory_score: float,
    anomaly_score: float,
    config: AISConfig = DEFAULT_CONFIG
) -> float:
    """
    Computes weighted composite threat score in [0.0, 1.0].
    Validates that weights sum to 1.0.
    """
    config.validate_weights()

    composite = (
        config.weight_proximity * proximity_score
        + config.weight_temporal * temporal_score
        + config.weight_trajectory * trajectory_score
        + config.weight_anomaly * anomaly_score
    )
    return round(float(np.clip(composite, 0.0, 1.0)), 4)


def classify_threat_level(
    composite_score: float,
    config: AISConfig = DEFAULT_CONFIG
) -> str:
    """
    Classifies a composite threat score into categorical tiers:
      - HIGH (>= high_threat_threshold, default 0.70)
      - MEDIUM (>= medium_threat_threshold, default 0.40)
      - LOW (< medium_threat_threshold)
    """
    score = float(composite_score)
    if score >= config.high_threat_threshold:
        return "HIGH"
    elif score >= config.medium_threat_threshold:
        return "MEDIUM"
    else:
        return "LOW"


class VesselAttributionEngine:
    """
    Autonomous vessel attribution engine correlating Contract B oil drift outputs
    with AIS feeds using multi-criteria weighted scoring and Isolation Forest anomalies.
    """

    def __init__(self, config: AISConfig = DEFAULT_CONFIG):
        self.config = config
        self.config.validate_weights()
        self.anomaly_detector = AISAnomalyDetector(
            contamination=self.config.anomaly_contamination,
            random_state=self.config.anomaly_random_state
        )

    def attribute_spill(
        self,
        contract_b: Dict[str, Any],
        ais_source: Union[str, pd.DataFrame],
        attribution_timestamp_utc: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes full attribution pipeline:
          1. Validates Contract B inputs.
          2. Cleans raw AIS feed and normalizes timestamps.
          3. Spatio-temporal corridor filtering around estimated spill origin.
          4. Feature engineering per candidate vessel.
          5. Behavioral anomaly detection via Isolation Forest.
          6. Multi-criteria sub-scoring and composite ranking.
          7. Verifiable evidence generation.
          8. Contract C GeoJSON payload packaging.

        Returns:
            Dict conforming to Contract C schema.
        """
        # 1. Parse Contract B context
        slick_id = str(contract_b.get("slick_id", "SLICK-UNKNOWN"))
        est_origin = contract_b.get("estimated_origin")
        if not est_origin or "point" not in est_origin or "time_utc" not in est_origin:
            raise KeyError("Contract B must contain 'estimated_origin' with 'point' and 'time_utc'.")

        origin_pt = est_origin["point"]
        origin_t = est_origin["time_utc"]
        backtrack_geom = contract_b.get("backtrack_track", {})
        backtrack_coords = backtrack_geom.get("coordinates") if isinstance(backtrack_geom, dict) else None

        # Compute approximate backtrack length in km
        backtrack_len_km = 0.0
        if backtrack_coords and len(backtrack_coords) > 1:
            for i in range(len(backtrack_coords) - 1):
                lon1, lat1 = backtrack_coords[i][0], backtrack_coords[i][1]
                lon2, lat2 = backtrack_coords[i + 1][0], backtrack_coords[i + 1][1]
                backtrack_len_km += haversine_distance_km(lat1, lon1, lat2, lon2, self.config.earth_radius_km)
            backtrack_len_km = round(backtrack_len_km, 2)

        # 2. Ingest and Clean AIS
        raw_df = load_ais_data(ais_source)
        clean_df = clean_ais_data(raw_df, self.config)

        # 3. Spatio-temporal filter
        filtered_df = filter_by_spatiotemporal(
            df=clean_df,
            origin_point=origin_pt,
            origin_time_utc=origin_t,
            spatial_radius_km=self.config.spatial_radius_km,
            temporal_window_hours=self.config.temporal_window_hours,
            earth_radius_km=self.config.earth_radius_km
        )

        # 4. Feature Extraction across candidate vessels
        features_df = extract_all_vessel_features(
            df=filtered_df,
            origin_point=origin_pt,
            origin_time_utc=origin_t,
            backtrack_coords=backtrack_coords,
            earth_radius_km=self.config.earth_radius_km
        )

        # 5. Isolation Forest Anomaly Detection
        if not features_df.empty:
            features_df = self.anomaly_detector.score_features_df(features_df)
        else:
            features_df["behavioral_anomaly_score"] = pd.Series(dtype=float)
            features_df["is_behavioral_anomaly"] = pd.Series(dtype=bool)

        # Trajectories for GeoJSON generation
        trajectories = build_vessel_trajectories(filtered_df)

        # 6. Score candidate vessels
        candidates = []
        for _, row in features_df.iterrows():
            mmsi = int(row["mmsi"])
            min_dist_km = float(row["min_distance_to_origin_km"])
            time_diff_min = float(row["time_difference_minutes"])
            align_score = float(row["trajectory_alignment_score"])
            xtd_km = float(row["cross_track_distance_km"])
            anom_score = float(row.get("behavioral_anomaly_score", 0.5))

            # Sub-scores
            prox_score = compute_proximity_score(min_dist_km, self.config)
            temp_score = compute_temporal_score(time_diff_min, self.config)
            traj_score = compute_trajectory_score(align_score, xtd_km, self.config)

            # Composite Threat Score
            comp_score = compute_composite_threat_score(
                proximity_score=prox_score,
                temporal_score=temp_score,
                trajectory_score=traj_score,
                anomaly_score=anom_score,
                config=self.config
            )

            threat_tier = classify_threat_level(comp_score, self.config)

            # Closest encounter coordinates
            vessel_traj = trajectories.get(mmsi)
            if vessel_traj is not None and not vessel_traj.empty:
                dists_to_orig = [
                    haversine_distance_km(r["latitude"], r["longitude"], origin_pt[1], origin_pt[0], self.config.earth_radius_km)
                    for _, r in vessel_traj.iterrows()
                ]
                min_idx = int(np.argmin(dists_to_orig))
                cpa_row = vessel_traj.iloc[min_idx]
                cpa_coord = [round(float(cpa_row["longitude"]), 5), round(float(cpa_row["latitude"]), 5)]
                sog_cpa = round(float(cpa_row["sog"]), 2) if pd.notna(cpa_row["sog"]) else 0.0
            else:
                cpa_coord = [round(float(origin_pt[0]), 5), round(float(origin_pt[1]), 5)]
                sog_cpa = 0.0

            row_dict = row.to_dict()
            row_dict["threat_level"] = threat_tier
            row_dict["composite_threat_score"] = comp_score

            # Evidence package
            evidence = generate_vessel_evidence_package(row_dict, self.config)

            # Trajectory GeoJSON feature
            traj_geojson = trajectory_to_geojson_feature(vessel_traj) if vessel_traj is not None else None

            candidate = {
                "mmsi": mmsi,
                "vessel_name": evidence["vessel_metadata"]["vessel_name"],
                "vessel_type": evidence["vessel_metadata"]["vessel_type"],
                "composite_threat_score": comp_score,
                "threat_level": threat_tier,
                "score_breakdown": {
                    "spatial_proximity_score": prox_score,
                    "temporal_correlation_score": temp_score,
                    "trajectory_alignment_score": traj_score,
                    "behavioral_anomaly_score": anom_score,
                },
                "closest_encounter": {
                    "min_distance_to_origin_km": min_dist_km,
                    "min_distance_to_backtrack_km": xtd_km,
                    "closest_point_time_utc": str(row["closest_point_time_utc"]),
                    "vessel_point_at_cpa": cpa_coord,  # Strict [lon, lat]
                    "speed_at_cpa_knots": sog_cpa,
                },
                "anomaly_indicators": evidence["anomaly_indicators"],
                "evidence_package": evidence,
                "trajectory_geojson": traj_geojson
            }
            candidates.append(candidate)

        # 7. Rank candidates descending by composite_threat_score
        candidates.sort(key=lambda x: x["composite_threat_score"], reverse=True)
        for rank_idx, cand in enumerate(candidates, start=1):
            cand["rank"] = rank_idx

        # 8. Summary counts
        high_cnt = sum(1 for c in candidates if c["threat_level"] == "HIGH")
        med_cnt = sum(1 for c in candidates if c["threat_level"] == "MEDIUM")
        low_cnt = sum(1 for c in candidates if c["threat_level"] == "LOW")

        now_utc = attribution_timestamp_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "slick_id": slick_id,
            "attribution_timestamp_utc": now_utc,
            "spill_context": {
                "estimated_origin_point": origin_pt,  # [lon, lat]
                "estimated_origin_time_utc": origin_t,
                "backtrack_length_km": backtrack_len_km,
                "spatial_radius_km": self.config.spatial_radius_km,
                "temporal_window_hours": self.config.temporal_window_hours,
            },
            "suspect_summary": {
                "total_vessels_evaluated": len(candidates),
                "high_threat_count": high_cnt,
                "medium_threat_count": med_cnt,
                "low_threat_count": low_cnt,
            },
            "ranked_suspects": candidates,
            "status": "COMPLETED"
        }
