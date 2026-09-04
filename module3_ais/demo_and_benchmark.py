"""
Module 3: AIS & Intelligence - Demo, Validation, and Performance Benchmark Script
Runs the end-to-end Member 3 attribution pipeline against the sample Contract B and synthetic AIS feed,
measures execution times of each phase, validates Contract C compliance, and updates sample output.
"""

import os
import sys
import json
import time

base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(base_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from typing import Dict, Any

from module3_ais.config import DEFAULT_CONFIG
from module3_ais.preprocessor import (
    load_ais_data,
    clean_ais_data,
    filter_by_spatiotemporal,
)
from module3_ais.trajectory import (
    build_vessel_trajectories,
    trajectory_to_geojson_feature,
)
from module3_ais.features import extract_all_vessel_features
from module3_ais.anomaly_model import AISAnomalyDetector
from module3_ais.attribution_engine import (
    VesselAttributionEngine,
    compute_proximity_score,
    compute_temporal_score,
    compute_trajectory_score,
    compute_composite_threat_score,
    classify_threat_level,
)
from module3_ais.evidence_generator import generate_vessel_evidence_package
from module3_ais.validate_schema import validate_contract_c


def run_demo_and_benchmark():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(base_dir, ".."))

    contract_b_path = os.path.join(repo_root, "contracts", "sample_drift_output.json")
    ais_csv_path = os.path.join(base_dir, "data", "synthetic_ais.csv")
    output_contract_c_path = os.path.join(repo_root, "contracts", "sample_attribution_output.json")

    print(f"Loading Contract B from: {contract_b_path}")
    print(f"Loading AIS CSV from:    {ais_csv_path}")

    with open(contract_b_path, "r", encoding="utf-8") as f:
        contract_b = json.load(f)

    # -------------------------------------------------------------
    # Stage 1: Ingestion & Preprocessing
    # -------------------------------------------------------------
    t0 = time.perf_counter()

    raw_df = load_ais_data(ais_csv_path)
    clean_df = clean_ais_data(raw_df, DEFAULT_CONFIG)

    origin_pt = contract_b["estimated_origin"]["point"]
    origin_t = contract_b["estimated_origin"]["time_utc"]
    backtrack_coords = contract_b.get("backtrack_track", {}).get("coordinates")

    filtered_df = filter_by_spatiotemporal(
        df=clean_df,
        origin_point=origin_pt,
        origin_time_utc=origin_t,
        spatial_radius_km=DEFAULT_CONFIG.spatial_radius_km,
        temporal_window_hours=DEFAULT_CONFIG.temporal_window_hours,
        earth_radius_km=DEFAULT_CONFIG.earth_radius_km
    )

    t1 = time.perf_counter()
    prep_time_ms = (t1 - t0) * 1000.0

    # -------------------------------------------------------------
    # Stage 2: Trajectory Reconstruction & Feature Engineering
    # -------------------------------------------------------------
    t2_start = time.perf_counter()

    trajectories = build_vessel_trajectories(filtered_df)
    features_df = extract_all_vessel_features(
        df=filtered_df,
        origin_point=origin_pt,
        origin_time_utc=origin_t,
        backtrack_coords=backtrack_coords,
        earth_radius_km=DEFAULT_CONFIG.earth_radius_km
    )

    t2_end = time.perf_counter()
    feat_time_ms = (t2_end - t2_start) * 1000.0

    # -------------------------------------------------------------
    # Stage 3: Isolation Forest Behavioral Anomaly Detection
    # -------------------------------------------------------------
    t3_start = time.perf_counter()

    detector = AISAnomalyDetector(
        contamination=DEFAULT_CONFIG.anomaly_contamination,
        random_state=DEFAULT_CONFIG.anomaly_random_state
    )
    scored_features_df = detector.score_features_df(features_df)

    t3_end = time.perf_counter()
    anom_time_ms = (t3_end - t3_start) * 1000.0

    # -------------------------------------------------------------
    # Stage 4: Attribution Scoring, Ranking, Evidence & Packaging
    # -------------------------------------------------------------
    t4_start = time.perf_counter()

    engine = VesselAttributionEngine(DEFAULT_CONFIG)
    contract_c = engine.attribute_spill(
        contract_b=contract_b,
        ais_source=ais_csv_path,
        attribution_timestamp_utc="2026-09-04T12:00:00Z"
    )

    t4_end = time.perf_counter()
    attr_time_ms = (t4_end - t4_start) * 1000.0
    total_time_ms = (t4_end - t0) * 1000.0

    # -------------------------------------------------------------
    # Stage 5: Manual & Schema Validation Checks
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("MEMBER 3 DEMO EXECUTION & VALIDATION RESULTS")
    print("=" * 60)

    # 1. JSON and Schema Validation
    is_valid, errors = validate_contract_c(contract_c)
    print(f"Contract C Schema Validity: {'PASS' if is_valid else 'FAIL'}")
    if errors:
        for err in errors:
            print(f"  - ERROR: {err}")

    # 2. Check slick_id
    expected_slick = contract_b.get("slick_id")
    actual_slick = contract_c.get("slick_id")
    assert expected_slick == actual_slick, f"slick_id mismatch: {expected_slick} vs {actual_slick}"
    print(f"Slick ID Match:             {actual_slick}")

    # 3. Check Origin Context
    spill_ctx = contract_c.get("spill_context", {})
    assert spill_ctx.get("estimated_origin_point") == origin_pt
    assert spill_ctx.get("estimated_origin_time_utc") == origin_t
    assert spill_ctx.get("spatial_radius_km") == DEFAULT_CONFIG.spatial_radius_km
    assert spill_ctx.get("temporal_window_hours") == DEFAULT_CONFIG.temporal_window_hours
    print(f"Spill Context:              Origin={origin_pt}, Time={origin_t}")

    # 4. Suspects evaluation
    suspects = contract_c.get("ranked_suspects", [])
    print(f"Total Vessels Evaluated:    {len(suspects)}")
    print(f"Summary Counts:             {contract_c.get('suspect_summary')}")

    prev_score = 1.01
    for s in suspects:
        rank = s["rank"]
        mmsi = s["mmsi"]
        score = s["composite_threat_score"]
        tier = s["threat_level"]
        name = s.get("vessel_name") or "Unnamed"
        breakdown = s["score_breakdown"]
        cpa = s["closest_encounter"]
        pt = cpa["vessel_point_at_cpa"]

        # Assertions
        assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"
        assert score <= prev_score + 1e-6, f"Rank order violated at rank {rank}"
        assert tier in ["HIGH", "MEDIUM", "LOW"], f"Invalid threat tier: {tier}"
        assert len(pt) == 2, f"CPA point must be 2D: {pt}"
        # Strict GeoJSON [lon, lat] check for Indian waters
        assert pt[0] > pt[1], f"Possible flipped coords [lat, lon] instead of [lon, lat]: {pt}"

        # Terminology check: no accusation in summary
        summary = s["evidence_package"]["summary"]
        forbidden = ["guilty", "perpetrator", "culprit", "proven responsible", "illegal"]
        for f_word in forbidden:
            assert f_word not in summary.lower(), f"Forbidden word '{f_word}' in summary!"

        prev_score = score
        print(f"  Rank #{rank}: MMSI {mmsi} | Threat: {tier:<6} | Score: {score:.4f} | Name: {name}")
        print(f"          Breakdown: Prox={breakdown['spatial_proximity_score']} | Temp={breakdown['temporal_correlation_score']} | Traj={breakdown['trajectory_alignment_score']} | Anom={breakdown['behavioral_anomaly_score']}")
        print(f"          CPA Coord: {pt} (Strict [lon, lat]) | CPA Dist: {cpa['min_distance_to_origin_km']} km")

    # -------------------------------------------------------------
    # Stage 6: Performance Report
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PERFORMANCE MEASUREMENTS")
    print("=" * 60)
    print(f"  1. AIS Preprocessing & Corridor Filter:  {prep_time_ms:8.2f} ms")
    print(f"  2. Trajectory & Feature Extraction:      {feat_time_ms:8.2f} ms")
    print(f"  3. Isolation Forest Anomaly Scoring:     {anom_time_ms:8.2f} ms")
    print(f"  4. Attribution Scoring & Packaging:      {attr_time_ms:8.2f} ms")
    print(f"  -------------------------------------------------------")
    print(f"  Total Pipeline Execution Time:           {total_time_ms:8.2f} ms (~{total_time_ms/1000.0:.3f} s)")
    print("=" * 60)

    # Save to contracts/sample_attribution_output.json
    with open(output_contract_c_path, "w", encoding="utf-8") as f:
        json.dump(contract_c, f, indent=2)
    print(f"\nSuccessfully wrote validated Contract C payload to:\n  {output_contract_c_path}")

    return {
        "valid": is_valid,
        "suspect_count": len(suspects),
        "total_time_ms": total_time_ms,
        "prep_time_ms": prep_time_ms,
        "feat_time_ms": feat_time_ms,
        "anom_time_ms": anom_time_ms,
        "attr_time_ms": attr_time_ms,
    }


if __name__ == "__main__":
    run_demo_and_benchmark()
