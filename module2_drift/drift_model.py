"""
Module 2: Geospatial & Drift Modeling - Unified Drift Engine (Contract B Entrypoint)
Combines data_loader, backtrack, and forecast into the public forecast_drift() function.

Accepts ML-detected slick input (Contract A) and returns the standardized Contract B JSON.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Union, List, Optional, Tuple
import numpy as np
from shapely.geometry import Point, Polygon, shape



from .data_loader import (
    load_metocean_reader,
    check_metocean_coverage,
    load_environment_data,
    MetoceanDateOutOfRangeError,
    MetoceanSpatialOutOfRangeError
)
from .backtrack import run_backtrack
from .forecast import run_forecast
from .exceptions import SimulationError


def sample_points_in_polygon(
    polygon: Polygon,
    num_points: int,
    seed: Optional[int] = 42
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Uniformly samples points within a Shapely polygon using rejection sampling.
    """
    if polygon.is_empty or polygon.area == 0:
        c = polygon.centroid
        return np.full(num_points, c.x), np.full(num_points, c.y)

    minx, miny, maxx, maxy = polygon.bounds
    rng = np.random.RandomState(seed)
    points = []
    max_attempts = max(num_points * 60, 1000)
    attempts = 0

    while len(points) < num_points and attempts < max_attempts:
        batch_size = max((num_points - len(points)) * 3, 50)
        xs = rng.uniform(minx, maxx, batch_size)
        ys = rng.uniform(miny, maxy, batch_size)
        for x, y in zip(xs, ys):
            p = Point(x, y)
            if polygon.contains(p):
                points.append((x, y))
                if len(points) == num_points:
                    break
        attempts += batch_size

    # Fallback to centroid if polygon is complex or points remain unfilled
    while len(points) < num_points:
        points.append((polygon.centroid.x, polygon.centroid.y))

    lons = np.array([p[0] for p in points], dtype=np.float64)
    lats = np.array([p[1] for p in points], dtype=np.float64)
    return lons, lats


def validate_and_extract_polygon(
    slick_input: Any
) -> Tuple[Optional[Polygon], Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Strictly validates input polygon geometry matching Member 1 detection outputs.
    Catches malformed, self-intersecting, unclosed, or invalid coordinates.

    Returns:
      (polygon_obj, slick_id, raw_time_str, error_dict)
    """
    if slick_input is None or slick_input == "":
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": "Input slick polygon is missing, null, or empty.",
            "details": {"received": str(type(slick_input))}
        }

    data = None
    slick_id = "SLICK-DETECTION-001"
    raw_time_str = None

    if isinstance(slick_input, str):
        try:
            data = json.loads(slick_input)
        except Exception as e:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": f"Input string could not be parsed as valid JSON: {str(e)}",
                "details": {"raw_string": slick_input[:120]}
            }
    elif isinstance(slick_input, dict):
        data = slick_input
    elif isinstance(slick_input, Polygon):
        if not slick_input.is_valid:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": "Provided Shapely Polygon is topologically invalid (e.g. self-intersecting boundary).",
                "details": {"is_valid": False, "wkt": slick_input.wkt[:120]}
            }
        return slick_input, slick_id, None, None
    else:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": f"Expected GeoJSON Polygon dict, JSON string, or Shapely Polygon; received {type(slick_input).__name__}.",
            "details": {"type": type(slick_input).__name__}
        }

    # Extract slick metadata
    slick_id = str(data.get("slick_id", data.get("id", "SLICK-DETECTION-001")))
    raw_time_str = data.get("timestamp_utc", data.get("timestamp", data.get("time_utc", None)))

    # Locate geometry coordinates
    geom_dict = None
    if data.get("type") == "Polygon" and "coordinates" in data:
        geom_dict = data
    elif "geometry" in data and isinstance(data["geometry"], dict):
        geom_dict = data["geometry"]
    elif "polygon" in data and isinstance(data["polygon"], dict):
        geom_dict = data["polygon"]
    elif "coordinates" in data:
        geom_dict = {"type": "Polygon", "coordinates": data["coordinates"]}

    if geom_dict is None:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": "No valid Polygon geometry or 'coordinates' structure found in input.",
            "details": {"available_keys": list(data.keys())}
        }

    if geom_dict.get("type") != "Polygon":
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": f"Expected geometry of type 'Polygon', but received '{geom_dict.get('type')}'.",
            "details": {"geometry_type": geom_dict.get("type")}
        }

    coords = geom_dict.get("coordinates")
    if not isinstance(coords, list) or len(coords) == 0:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": "Polygon 'coordinates' must be a non-empty list of linear rings.",
            "details": {"coordinates": coords}
        }

    exterior = coords[0]
    if not isinstance(exterior, list) or len(exterior) < 4:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": f"Polygon exterior ring must contain at least 4 vertices (3 points + 1 closing point); got {len(exterior) if isinstance(exterior, list) else 0}.",
            "details": {"vertex_count": len(exterior) if isinstance(exterior, list) else 0}
        }

    # Check that ring is closed (first point == last point)
    first_pt, last_pt = exterior[0], exterior[-1]
    if first_pt != last_pt:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": f"Polygon exterior ring is not closed. First point {first_pt} does not match last point {last_pt}.",
            "details": {"first_point": first_pt, "last_point": last_pt}
        }

    # Validate coordinate values
    for idx, pt in enumerate(exterior):
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": f"Vertex at index {idx} is not a valid coordinate pair: {pt}.",
                "details": {"index": idx, "vertex": pt}
            }
        try:
            lon, lat = float(pt[0]), float(pt[1])
        except (ValueError, TypeError):
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": f"Non-numeric coordinates encountered at index {idx}: {pt}.",
                "details": {"index": idx, "vertex": pt}
            }

        if np.isnan(lon) or np.isnan(lat):
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": f"NaN coordinate encountered at vertex {idx}.",
                "details": {"index": idx, "vertex": [lon, lat]}
            }

        # Check global bounds
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": f"Coordinate [{lon}, {lat}] at index {idx} is outside geographic limits (-180..180° lon, -90..90° lat).",
                "details": {"index": idx, "vertex": [lon, lat]}
            }

        # Flipped coordinate check for Indian Ocean / Arabian Sea
        if -35.0 <= lon <= 35.0 and 55.0 <= lat <= 100.0:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": (
                    f"Coordinates appear inverted as [lat, lon] rather than GeoJSON standard [lon, lat] "
                    f"at index {idx}: [{lon}, {lat}]."
                ),
                "details": {"index": idx, "detected_pair": [lon, lat]}
            }

    # Validate topology using Shapely
    try:
        poly = shape(geom_dict)
        if not isinstance(poly, Polygon) or poly.is_empty:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": "Geometry could not be parsed into a non-empty polygon.",
                "details": {"is_empty": True}
            }
        if not poly.is_valid:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": "Polygon has self-intersections or invalid topology (e.g. figure-8 or self-crossing edges).",
                "details": {"shapely_reason": "Self-intersection detected"}
            }
        if poly.area == 0:
            return None, None, None, {
                "error": True,
                "error_type": "INVALID_POLYGON",
                "reason": "Polygon has zero surface area (collinear points).",
                "details": {"area": 0.0}
            }
    except Exception as e:
        return None, None, None, {
            "error": True,
            "error_type": "INVALID_POLYGON",
            "reason": f"Failed constructing valid Shapely polygon: {str(e)}",
            "details": {"exception": str(e)}
        }

    return poly, slick_id, raw_time_str, None


def _get_readers(current_nc_path: Optional[str], wind_nc_path: Optional[str]) -> List[Any]:
    """Sets up NetCDF readers or falls back to standard coastal forcing."""
    if current_nc_path and os.path.exists(current_nc_path) and wind_nc_path and os.path.exists(wind_nc_path):
        r_curr = load_metocean_reader(current_nc_path, reader_name="CurrentReader")
        r_wind = load_metocean_reader(wind_nc_path, reader_name="WindReader")
        return [r_curr, r_wind]
    else:
        # Default fallback conditions (Arabian Sea / Bay of Bengal mean monsoon forcing)
        from opendrift.readers import reader_constant
        r_default = reader_constant.Reader({
            'x_sea_water_velocity': 0.25,
            'y_sea_water_velocity': -0.15,
            'x_wind': 7.5,
            'y_wind': 4.0,
            'sea_water_temperature': 28.5,
            'sea_surface_wave_significant_height': 1.5
        })
        return [r_default]


def forecast_drift(
    slick_polygon: Union[Dict[str, Any], str, Polygon],
    timestamp: Optional[Union[datetime, str]] = None,
    seed_mode: str = "distributed",
    current_nc_path: Optional[str] = None,
    wind_nc_path: Optional[str] = None,
    backtrack_hours: int = 12,
    forecast_hours: List[int] = [6, 24],
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE",
    ensemble_size: int = 5,
    position_jitter_m: float = 250.0,
    horizontal_diffusivity: float = 50.0,
) -> Dict[str, Any]:
    """
    Main Unified Entrypoint for Module 2 with Robust Error Handling.
    
    Accepts Member 1's ML-detected slick polygon (GeoJSON Polygon, Shapely Polygon, or Contract A dict)
    and executes reverse backtracking to pinpoint origin, and forecasts forward spread polygons (+6h, +24h).

    Errors handled cleanly without traceback:
      (1) Invalid/malformed input polygon -> error_type: 'INVALID_POLYGON'
      (2) Requested date outside available data range -> error_type: 'TEMPORAL_OUT_OF_BOUNDS'
      (3) Point or polygon outside coverage or on land -> error_type: 'SPATIAL_OUT_OF_BOUNDS' / 'LAND_INTERSECTION'
      (4) OpenDrift simulation failures near coastlines/edges -> error_type: 'SIMULATION_FAILURE'

    Returns:
      On Success: Standardized Contract B dictionary.
      On Failure: Standardized error dictionary {"error": True, "error_type": "...", "reason": "...", "details": {...}}.
    """
    # Backward compatibility: older call sites passed (slick_polygon, curr_nc_path, wind_nc_path)
    # as positional args.  Detect this pattern by checking if `timestamp` looks like a .nc path.
    # Deprecated: prefer keyword arguments current_nc_path= and wind_nc_path= explicitly.
    if isinstance(timestamp, str) and (timestamp.endswith(".nc") or (os.path.exists(timestamp) and not timestamp.endswith(".json"))):
        current_nc_path = timestamp
        if isinstance(seed_mode, str) and (seed_mode.endswith(".nc") or os.path.exists(seed_mode)):
            wind_nc_path = seed_mode
        seed_mode = "distributed"
        timestamp = None

    if seed_mode not in ("centroid", "distributed"):
        return {
            "error": True,
            "error_type": "INVALID_PARAMETER",
            "reason": f"Invalid seed_mode '{seed_mode}'. Must be 'centroid' or 'distributed'.",
            "details": {"valid_options": ["centroid", "distributed"]}
        }

    # 1. Validate Input Polygon Geometry
    poly, slick_id, raw_time_str, poly_error = validate_and_extract_polygon(slick_polygon)
    if poly_error:
        return poly_error

    # 2. Validate and Parse Timestamp
    chosen_time = timestamp if timestamp is not None else raw_time_str
    if chosen_time is None:
        det_time = datetime.fromisoformat("2026-09-04T12:00:00")
    elif isinstance(chosen_time, datetime):
        det_time = chosen_time.replace(tzinfo=None) if chosen_time.tzinfo else chosen_time
    else:
        try:
            det_time = datetime.fromisoformat(str(chosen_time).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception as te:
            return {
                "error": True,
                "error_type": "INVALID_TIMESTAMP",
                "reason": f"Unparseable timestamp '{chosen_time}'. Must be valid ISO8601 string (e.g. '2026-09-04T12:00:00Z'): {str(te)}",
                "details": {"timestamp_input": str(chosen_time)}
            }

    centroid_lon = round(float(poly.centroid.x), 6)
    centroid_lat = round(float(poly.centroid.y), 6)
    radius_meters = max(250, int(np.sqrt(poly.area) * 111000 / 2))

    # 3. Metocean Spatial, Land, and Temporal Coverage Validation
    if current_nc_path and os.path.exists(current_nc_path):
        is_cov, cov_err = check_metocean_coverage(
            filepath=current_nc_path,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            target_time=det_time,
            polygon_bounds=poly.bounds,
            backtrack_hours=backtrack_hours,
            forecast_hours=max(forecast_hours) if forecast_hours else 24
        )
        if not is_cov:
            return cov_err

    if wind_nc_path and os.path.exists(wind_nc_path):
        is_cov_w, cov_err_w = check_metocean_coverage(
            filepath=wind_nc_path,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            target_time=det_time,
            polygon_bounds=poly.bounds,
            backtrack_hours=backtrack_hours,
            forecast_hours=max(forecast_hours) if forecast_hours else 24
        )
        if not is_cov_w:
            return cov_err_w

    # 4. Initialize Readers
    readers = None
    if current_nc_path and wind_nc_path:
        try:
            readers = _get_readers(current_nc_path, wind_nc_path)
        except Exception as re:
            return {
                "error": True,
                "error_type": "READER_INITIALIZATION_ERROR",
                "reason": f"Failed to load metocean readers: {str(re)}",
                "details": {"current_nc": current_nc_path, "wind_nc": wind_nc_path}
            }
    else:
        # Auto-discover and select local NetCDF files matching requested date and bbox
        try:
            poly_bbox = [float(poly.bounds[0]), float(poly.bounds[1]), float(poly.bounds[2]), float(poly.bounds[3])]
            env_data = load_environment_data(date=det_time, bbox=poly_bbox)
            readers = env_data["readers"]
            auto_curr = env_data.get("current_file")
            if auto_curr and os.path.exists(auto_curr):
                is_cov, cov_err = check_metocean_coverage(
                    filepath=auto_curr,
                    centroid_lon=centroid_lon,
                    centroid_lat=centroid_lat,
                    target_time=det_time,
                    polygon_bounds=poly.bounds,
                    backtrack_hours=backtrack_hours,
                    forecast_hours=max(forecast_hours) if forecast_hours else 24
                )
                if not is_cov:
                    return cov_err
        except MetoceanDateOutOfRangeError as d_err:
            return {
                "error": True,
                "error_type": "TEMPORAL_OUT_OF_BOUNDS",
                "reason": str(d_err),
                "details": {
                    "requested_date": det_time.isoformat(),
                    "available_ranges": d_err.available_ranges
                }
            }
        except MetoceanSpatialOutOfRangeError as s_err:
            return {
                "error": True,
                "error_type": "SPATIAL_OUT_OF_BOUNDS",
                "reason": str(s_err),
                "details": {
                    "requested_bbox": s_err.requested_bbox,
                    "available_bounds": s_err.available_bounds
                }
            }
        except Exception:
            # Fallback to constant coastal reader if no local NetCDFs match or exist
            readers = _get_readers(None, None)

    # 5. Particle Seeding Preparation
    if seed_mode == "distributed":
        seed_lons, seed_lats = sample_points_in_polygon(poly, num_particles, seed=42)
    else:
        seed_lons, seed_lats = None, None

    # 6. Execute Simulations with Coastal/Grid Edge Failure Handling
    try:
        # A. Backtracking (-12h)
        origin_pt, origin_time_str, track_coords = run_backtrack(
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            radius_meters=radius_meters,
            det_time=det_time,
            readers=readers,
            backtrack_hours=backtrack_hours,
            num_particles=num_particles,
            oil_type=oil_type,
            slick_id=slick_id,
            seed_mode=seed_mode,
            seed_lons=seed_lons,
            seed_lats=seed_lats
        )

        # B. Forward Forecasting (+6h, +24h)
        forecast_polys = run_forecast(
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            radius_meters=radius_meters,
            det_time=det_time,
            readers=readers,
            forecast_hours=forecast_hours,
            num_particles=num_particles,
            oil_type=oil_type,
            slick_id=slick_id,
            seed_mode=seed_mode,
            seed_lons=seed_lons,
            seed_lats=seed_lats,
            ensemble_size=ensemble_size,
            position_jitter_m=position_jitter_m,
            horizontal_diffusivity=horizontal_diffusivity,
        )

    except SimulationError as se:
        return {
            "error": True,
            "error_type": "SIMULATION_FAILURE",
            "reason": se.message,
            "details": {
                "stage": se.stage,
                "slick_id": slick_id,
                "details": se.details
            }
        }
    except Exception as ge:
        return {
            "error": True,
            "error_type": "SIMULATION_FAILURE",
            "reason": f"OpenDrift simulation crashed near coastline or grid edge: {str(ge)}",
            "details": {"slick_id": slick_id, "exception": str(ge)}
        }

    # 7. Assemble Clean Contract B Result
    return {
        "slick_id": slick_id,
        "seed_mode": seed_mode,
        "estimated_origin": {
            "point": origin_pt,
            "time_utc": origin_time_str
        },
        "backtrack_track": {
            "type": "LineString",
            "coordinates": track_coords
        },
        "forecast_polygons": forecast_polys
    }

