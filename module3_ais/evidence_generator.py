"""
Module 3: AIS & Intelligence - Forensic Evidence Generator
Generates human-readable evidentiary packages, event timelines, and regulatory justification
for enforcement agencies (Indian Coast Guard, DG Shipping).
NOTE: Phase 1 Stub - To be fully implemented in Phase 2.
"""

from typing import Dict, Any, List


def generate_vessel_evidence_package(
    mmsi: int,
    vessel_name: str,
    vessel_type: str,
    min_dist_km: float,
    closest_time_utc: str,
    anomaly_flags: List[str]
) -> Dict[str, Any]:
    """
    Assembles narrative forensic evidence for a suspect vessel.
    """
    summary = (
        f"Vessel {vessel_name} (MMSI {mmsi}, Type: {vessel_type}) was detected within "
        f"{min_dist_km:.2f} km of the estimated spill origin at {closest_time_utc}."
    )
    if anomaly_flags:
        summary += f" Behavioral alerts triggered: {', '.join(anomaly_flags)}."

    return {
        "summary": summary,
        "anomaly_indicators": anomaly_flags,
        "recommended_action": "Request maritime log inspection upon arrival at next port of call."
    }
