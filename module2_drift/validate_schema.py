"""
Module 2: Geospatial & Drift Modeling - Contract B Schema Validator
Validates forecast_drift() outputs against the exact team contract schema.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple, Union
from shapely.geometry import shape, LineString, Polygon


def validate_drift_output(output_data: Union[Dict[str, Any], str]) -> Tuple[bool, List[str]]:
    """
    Validates output data against the exact team Contract B schema:

    {
      "slick_id": "string",
      "estimated_origin": { "point": [lon, lat], "time_utc": "ISO8601 string" },
      "backtrack_track": { "type": "LineString", "coordinates": [[lon, lat], ...] },
      "forecast_polygons": [
        { "hours_ahead": number, "geometry": {"type":"Polygon","coordinates": [...]} }
      ]
    }

    Returns:
      Tuple[bool, List[str]]: (is_valid, list_of_mismatch_messages)
    """
    mismatches = []

    if isinstance(output_data, str):
        try:
            data = json.loads(output_data)
        except Exception as e:
            return False, [f"Invalid JSON format: {str(e)}"]
    elif isinstance(output_data, dict):
        data = output_data
    else:
        return False, [f"Expected dict or JSON string, received {type(output_data).__name__}"]

    # 1. Top-Level Required Keys
    required_top_keys = ["slick_id", "estimated_origin", "backtrack_track", "forecast_polygons"]
    for k in required_top_keys:
        if k not in data:
            mismatches.append(f"Missing required top-level key: '{k}'")

    if mismatches:
        return False, mismatches

    # 2. Slick ID
    slick_id = data["slick_id"]
    if not isinstance(slick_id, str) or not slick_id.strip():
        mismatches.append(f"Key 'slick_id' must be a non-empty string, got: {repr(slick_id)}")

    # 3. Estimated Origin
    est_origin = data["estimated_origin"]
    if not isinstance(est_origin, dict):
        mismatches.append(f"Key 'estimated_origin' must be a dict, got: {type(est_origin).__name__}")
    else:
        for sub_k in ["point", "time_utc"]:
            if sub_k not in est_origin:
                mismatches.append(f"Missing key 'estimated_origin.{sub_k}'")

        if "point" in est_origin:
            pt = est_origin["point"]
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                mismatches.append(f"'estimated_origin.point' must be a 2-element list [lon, lat], got: {repr(pt)}")
            else:
                lon, lat = pt[0], pt[1]
                if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float))):
                    mismatches.append(f"'estimated_origin.point' values must be numeric, got: {repr(pt)}")
                else:
                    if not (-180.0 <= lon <= 180.0):
                        mismatches.append(f"Longitude in 'estimated_origin.point' out of range [-180, 180]: {lon}")
                    if not (-90.0 <= lat <= 90.0):
                        mismatches.append(f"Latitude in 'estimated_origin.point' out of range [-90, 90]: {lat}")

                    # Flipped coordinate detection (Indian waters: lon ~65-98°E, lat ~5-25°N)
                    if -35.0 <= lon <= 35.0 and 55.0 <= lat <= 100.0:
                        mismatches.append(
                            f"CRITICAL: 'estimated_origin.point' appears FLIPPED as [lat, lon] instead of [lon, lat]! "
                            f"Got [{lon}, {lat}]. Expected Longitude (~70-90°E) first, Latitude (~10-25°N) second."
                        )

        if "time_utc" in est_origin:
            t_str = est_origin["time_utc"]
            if not isinstance(t_str, str):
                mismatches.append(f"'estimated_origin.time_utc' must be a string, got: {type(t_str).__name__}")
            else:
                if not (t_str.endswith("Z") or t_str.endswith("+00:00")):
                    mismatches.append(
                        f"'estimated_origin.time_utc' must explicitly specify UTC zone ('Z' or '+00:00'), got: '{t_str}'"
                    )
                try:
                    clean_t = t_str.replace("Z", "+00:00")
                    datetime.fromisoformat(clean_t)
                except Exception as e:
                    mismatches.append(f"'estimated_origin.time_utc' is not a valid ISO8601 datetime: '{t_str}' ({e})")

    # 4. Backtrack Track
    track = data["backtrack_track"]
    if not isinstance(track, dict):
        mismatches.append(f"Key 'backtrack_track' must be a GeoJSON dict, got: {type(track).__name__}")
    else:
        if track.get("type") != "LineString":
            mismatches.append(f"'backtrack_track.type' must be 'LineString', got: '{track.get('type')}'")

        coords = track.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            mismatches.append(f"'backtrack_track.coordinates' must be a list of at least 2 waypoints, got: {coords}")
        else:
            for idx, pt in enumerate(coords):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    mismatches.append(f"'backtrack_track.coordinates[{idx}]' must be [lon, lat], got: {pt}")
                    break
                lon, lat = pt[0], pt[1]
                if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                    mismatches.append(f"'backtrack_track.coordinates[{idx}]' out of bounds: [{lon}, {lat}]")
                    break
                if -35.0 <= lon <= 35.0 and 55.0 <= lat <= 100.0:
                    mismatches.append(
                        f"CRITICAL: 'backtrack_track.coordinates[{idx}]' appears FLIPPED as [lat, lon]: [{lon}, {lat}]"
                    )
                    break

            try:
                geom = shape(track)
                if not isinstance(geom, LineString) or geom.is_empty:
                    mismatches.append("Shapely could not construct a valid, non-empty LineString for 'backtrack_track'")
                elif not geom.is_valid:
                    mismatches.append("'backtrack_track' geometry is topologically invalid")
            except Exception as e:
                mismatches.append(f"Invalid GeoJSON LineString in 'backtrack_track': {e}")

    # 5. Forecast Polygons (Strictly +6h and +24h)
    polys = data["forecast_polygons"]
    if not isinstance(polys, list):
        mismatches.append(f"Key 'forecast_polygons' must be a list, got: {type(polys).__name__}")
    else:
        if len(polys) != 2:
            mismatches.append(f"'forecast_polygons' must contain exactly 2 entries (+6h and +24h), found: {len(polys)}")

        hours_found = []
        for i, item in enumerate(polys):
            if not isinstance(item, dict):
                mismatches.append(f"'forecast_polygons[{i}]' must be a dict, got: {type(item).__name__}")
                continue

            h = item.get("hours_ahead")
            if h is None or not isinstance(h, (int, float)):
                mismatches.append(f"'forecast_polygons[{i}].hours_ahead' must be numeric, got: {h}")
            else:
                hours_found.append(h)

            geom_dict = item.get("geometry")
            if not isinstance(geom_dict, dict):
                mismatches.append(f"'forecast_polygons[{i}].geometry' must be a dict, got: {geom_dict}")
                continue

            if geom_dict.get("type") != "Polygon":
                mismatches.append(f"'forecast_polygons[{i}].geometry.type' must be 'Polygon', got: '{geom_dict.get('type')}'")

            poly_coords = geom_dict.get("coordinates")
            if not isinstance(poly_coords, list) or len(poly_coords) == 0:
                mismatches.append(f"'forecast_polygons[{i}].geometry.coordinates' must contain linear rings")
            else:
                exterior = poly_coords[0]
                if not isinstance(exterior, list) or len(exterior) < 4:
                    mismatches.append(
                        f"'forecast_polygons[{i}]' exterior ring must have >= 4 points, got: {len(exterior) if isinstance(exterior, list) else exterior}"
                    )
                else:
                    first_pt, last_pt = exterior[0], exterior[-1]
                    if first_pt != last_pt:
                        mismatches.append(
                            f"'forecast_polygons[{i}]' exterior ring is NOT closed! First: {first_pt}, Last: {last_pt}"
                        )

                    for pt_idx, pt in enumerate(exterior):
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            lon, lat = pt[0], pt[1]
                            if -35.0 <= lon <= 35.0 and 55.0 <= lat <= 100.0:
                                mismatches.append(
                                    f"CRITICAL: 'forecast_polygons[{i}]' point {pt_idx} appears FLIPPED as [lat, lon]: [{lon}, {lat}]"
                                )
                                break

            try:
                poly_geom = shape(geom_dict)
                if not isinstance(poly_geom, Polygon) or poly_geom.is_empty:
                    mismatches.append(f"Shapely could not construct a valid Polygon for 'forecast_polygons[{i}]'")
                elif not poly_geom.is_valid:
                    mismatches.append(f"'forecast_polygons[{i}]' Polygon geometry is topologically invalid")
            except Exception as e:
                mismatches.append(f"Invalid GeoJSON Polygon in 'forecast_polygons[{i}]': {e}")

        if set(hours_found) != {6, 24}:
            mismatches.append(
                f"'forecast_polygons' must contain exactly the 6-hour and 24-hour entries. Found hours: {hours_found}"
            )

    is_valid = (len(mismatches) == 0)
    return is_valid, mismatches


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "contracts/sample_drift_output.json"
    if not os.path.exists(target):
        print(f"[!] File not found: {target}")
        sys.exit(1)

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)

    valid, errors = validate_drift_output(data)
    print("=" * 60)
    print(f"Contract Validation for: {target}")
    print("=" * 60)
    if valid:
        print("Status: [PASS] 100% Valid Contract B format!")
        print(f"  - Slick ID: {data.get('slick_id')}")
        print(f"  - Origin Point: {data.get('estimated_origin', {}).get('point')}")
        print(f"  - Forecast Horizons: {[p.get('hours_ahead') for p in data.get('forecast_polygons', [])]}h")
    else:
        print("Status: [FAIL] Validation Errors:")
        for err in errors:
            print(f"  * {err}")
    sys.exit(0 if valid else 1)
