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

from opendrift.readers import reader_constant

from .data_loader import load_metocean_reader
from .backtrack import run_backtrack
from .forecast import run_forecast


def _extract_slick_inputs(slick_json: Union[Dict[str, Any], str]) -> Tuple[str, datetime, float, float, float]:
    """Helper to parse varied input formats (GeoJSON, standard dict, or JSON string)."""
    if isinstance(slick_json, str):
        data = json.loads(slick_json)
    else:
        data = slick_json

    slick_id = str(data.get("slick_id", data.get("id", "SLICK-BOB-DEMO-001")))
    
    # Extract timestamp
    raw_time = data.get("timestamp_utc", data.get("timestamp", data.get("time_utc", "2026-09-04T12:00:00Z")))
    if isinstance(raw_time, datetime):
        dt = raw_time.replace(tzinfo=None) if raw_time.tzinfo else raw_time
    else:
        dt = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00")).replace(tzinfo=None)

    # Extract polygon geometry
    geom_data = data.get("geometry", data.get("polygon", data.get("coordinates", None)))
    if isinstance(geom_data, dict):
        poly = shape(geom_data)
    elif isinstance(geom_data, list):
        if len(geom_data) > 0 and isinstance(geom_data[0], list) and isinstance(geom_data[0][0], list):
            poly = Polygon(geom_data[0])
        else:
            poly = Polygon(geom_data)
    else:
        center_lon = data.get("lon", 72.0)
        center_lat = data.get("lat", 19.0)
        poly = Point(center_lon, center_lat).buffer(0.02)

    centroid_lon, centroid_lat = poly.centroid.x, poly.centroid.y
    radius_meters = max(500, int(np.sqrt(poly.area) * 111000 / 2))

    return slick_id, dt, centroid_lon, centroid_lat, radius_meters


def _get_readers(current_nc_path: Optional[str], wind_nc_path: Optional[str]) -> List[Any]:
    """Sets up NetCDF readers or falls back to standard coastal forcing."""
    if current_nc_path and os.path.exists(current_nc_path) and wind_nc_path and os.path.exists(wind_nc_path):
        r_curr = load_metocean_reader(current_nc_path, reader_name="CurrentReader")
        r_wind = load_metocean_reader(wind_nc_path, reader_name="WindReader")
        return [r_curr, r_wind]
    else:
        # Default fallback conditions (Arabian Sea / Bay of Bengal mean monsoon forcing)
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
    slick_json: Union[Dict[str, Any], str],
    current_nc_path: Optional[str] = None,
    wind_nc_path: Optional[str] = None,
    backtrack_hours: int = 12,
    forecast_hours: List[int] = [6, 24],
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE"
) -> Dict[str, Any]:
    """
    Main Unified Function for Module 2.
    
    Takes ML-detected slick polygon + timestamp (Contract A), executes reverse backtracking
    to pinpoint origin, and forecasts forward spread polygons (+6h, +24h).

    Returns exact Team Contract B schema:
    {
      "slick_id": "string",
      "estimated_origin": { "point": [lon, lat], "time_utc": "ISO8601 string" },
      "backtrack_track": { "type": "LineString", "coordinates": [[lon, lat], ...] },
      "forecast_polygons": [
        { "hours_ahead": 6, "geometry": {"type":"Polygon","coordinates": [...]} },
        { "hours_ahead": 24, "geometry": {"type":"Polygon","coordinates": [...]} }
      ]
    }
    """
    slick_id, det_time, centroid_lon, centroid_lat, radius_meters = _extract_slick_inputs(slick_json)
    readers = _get_readers(current_nc_path, wind_nc_path)

    # 1. Backtracking (-12h)
    origin_pt, origin_time_str, track_coords = run_backtrack(
        centroid_lon=centroid_lon,
        centroid_lat=centroid_lat,
        radius_meters=radius_meters,
        det_time=det_time,
        readers=readers,
        backtrack_hours=backtrack_hours,
        num_particles=num_particles,
        oil_type=oil_type,
        slick_id=slick_id
    )

    # 2. Forward Forecasting (+6h, +24h)
    forecast_polys = run_forecast(
        centroid_lon=centroid_lon,
        centroid_lat=centroid_lat,
        radius_meters=radius_meters,
        det_time=det_time,
        readers=readers,
        forecast_hours=forecast_hours,
        num_particles=num_particles,
        oil_type=oil_type,
        slick_id=slick_id
    )

    # 3. Contract B Assemble
    return {
        "slick_id": slick_id,
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
