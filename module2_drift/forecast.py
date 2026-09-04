"""
Module 2: Geospatial & Drift Modeling - Forward Forecasting Engine
Executes forward OpenDrift Lagrangian advection and dispersion modeling to predict
oil slick spread envelopes at specified horizons (+6h, +24h).
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union, Optional
import numpy as np
import xarray as xr
import shapely
from shapely.geometry import Point, MultiPoint, Polygon, mapping
from opendrift.models.openoil import OpenOil


def particles_to_polygon_geojson(
    lons: np.ndarray,
    lats: np.ndarray,
    concave_ratio: float = 0.35,
    buffer_deg: float = 0.012
) -> Dict[str, Any]:
    """
    Generates a closed GeoJSON Polygon envelope from a particle cloud.
    Uses concave hull when possible, falling back to buffered convex hull.
    """
    valid_mask = ~np.isnan(lons) & ~np.isnan(lats)
    valid_lons = lons[valid_mask]
    valid_lats = lats[valid_mask]

    if len(valid_lons) < 3:
        center_lon = float(np.nanmean(lons)) if len(valid_lons) > 0 else 72.0
        center_lat = float(np.nanmean(lats)) if len(valid_lats) > 0 else 19.0
        poly = Point(center_lon, center_lat).buffer(buffer_deg)
        return mapping(poly)

    pts = [Point(x, y) for x, y in zip(valid_lons, valid_lats)]
    multi_point = MultiPoint(pts)

    if hasattr(shapely, "concave_hull"):
        try:
            hull = shapely.concave_hull(multi_point, ratio=concave_ratio, allow_holes=False)
            if not isinstance(hull, Polygon) or hull.is_empty:
                hull = multi_point.convex_hull
        except Exception:
            hull = multi_point.convex_hull
    else:
        hull = multi_point.convex_hull

    buffered_hull = hull.buffer(buffer_deg)
    if buffered_hull.geom_type == 'MultiPolygon':
        buffered_hull = buffered_hull.convex_hull

    simplified_hull = buffered_hull.simplify(0.001, preserve_topology=True)
    return mapping(simplified_hull)


def run_forecast(
    centroid_lon: float,
    centroid_lat: float,
    radius_meters: float,
    det_time: datetime,
    readers: List[Any],
    forecast_hours: List[int] = [6, 24],
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE",
    slick_id: str = "SLICK"
) -> List[Dict[str, Any]]:
    """
    Executes forward simulation and extracts closed GeoJSON polygon envelopes.

    Returns:
      List of dicts: [ { "hours_ahead": h, "geometry": {"type":"Polygon", ...} }, ... ]
    """
    timestamp_key = int(det_time.timestamp())
    max_forecast = max(forecast_hours)
    
    o_fore = OpenOil(loglevel=30)
    for r in readers:
        o_fore.add_reader(r)

    o_fore.seed_elements(
        lon=centroid_lon,
        lat=centroid_lat,
        radius=radius_meters,
        number=num_particles,
        time=det_time,
        oil_type=oil_type
    )

    fore_nc = f"temp_fore_{slick_id}_{timestamp_key}.nc"
    try:
        o_fore.run(
            duration=timedelta(hours=max_forecast),
            time_step=timedelta(minutes=30),   # Forward advection step
            time_step_output=timedelta(hours=1),
            outfile=fore_nc
        )

        forecast_polygons = []
        with xr.open_dataset(fore_nc) as ds_fore:
            ds_fore.load()
            f_lons = ds_fore['lon'].values
            f_lats = ds_fore['lat'].values
            f_times = ds_fore['time'].values

            for h in forecast_hours:
                target_time = np.datetime64(det_time) + np.timedelta64(h, 'h')
                t_idx = int(np.argmin(np.abs(f_times - target_time)))

                poly_geom = particles_to_polygon_geojson(
                    f_lons[t_idx],
                    f_lats[t_idx],
                    concave_ratio=0.35,
                    buffer_deg=0.012
                )

                forecast_polygons.append({
                    "hours_ahead": h,
                    "geometry": poly_geom
                })

        return forecast_polygons

    finally:
        try:
            if os.path.exists(fore_nc):
                os.remove(fore_nc)
        except Exception:
            pass
