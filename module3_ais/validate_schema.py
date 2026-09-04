"""
Module 3: AIS & Intelligence - Contract C Schema Validator
Validates vessel attribution outputs against team Contract C specification and GeoJSON standards.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Tuple, Union


def validate_contract_c(output_data: Union[Dict[str, Any], str]) -> Tuple[bool, List[str]]:
    """
    Validates Contract C payload structure, coordinate orientation, and data integrity.

    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_error_strings)
    """
    errors = []

    if isinstance(output_data, str):
        try:
            data = json.loads(output_data)
        except Exception as e:
            return False, [f"Invalid JSON string: {e}"]
    elif isinstance(output_data, dict):
        data = output_data
    else:
        return False, [f"Expected dict or JSON string, got {type(output_data).__name__}"]

    # 1. Required top-level keys
    required_keys = [
        "slick_id",
        "attribution_timestamp_utc",
        "spill_context",
        "suspect_summary",
        "ranked_suspects",
        "status"
    ]
    for k in required_keys:
        if k not in data:
            errors.append(f"Missing required top-level key: '{k}'")

    if errors:
        return False, errors

    # 2. Verify timestamp format
    t_str = data["attribution_timestamp_utc"]
    if not isinstance(t_str, str) or not (t_str.endswith("Z") or t_str.endswith("+00:00")):
        errors.append(f"'attribution_timestamp_utc' must specify explicit UTC ('Z' or '+00:00'), got: {t_str}")

    # 3. Check suspect ranking
    suspects = data.get("ranked_suspects", [])
    if not isinstance(suspects, list):
        errors.append(f"'ranked_suspects' must be a list, got {type(suspects).__name__}")
    else:
        prev_score = 1.01
        for i, s in enumerate(suspects):
            if not isinstance(s, dict):
                errors.append(f"Suspect entry {i} is not a dict.")
                continue
            
            score = s.get("composite_threat_score", 0.0)
            if not (0.0 <= score <= 1.0):
                errors.append(f"Suspect {i} composite_threat_score {score} out of bounds [0.0, 1.0]")
            if score > prev_score + 1e-6:
                errors.append(f"Suspects not sorted in descending threat score at index {i}")
            prev_score = score

            # Check CPA coordinates if present
            cpa = s.get("closest_encounter", {})
            pt = cpa.get("vessel_point_at_cpa")
            if pt and isinstance(pt, (list, tuple)) and len(pt) == 2:
                lon, lat = pt[0], pt[1]
                # Flipped coordinate check for Indian waters: [lon, lat] vs [lat, lon]
                if -35.0 <= lon <= 35.0 and 55.0 <= lat <= 100.0:
                    errors.append(
                        f"CRITICAL: Suspect {i} 'vessel_point_at_cpa' appears FLIPPED as [lat, lon]! Got [{lon}, {lat}]."
                    )

    return (len(errors) == 0), errors
