"""
Module 2: Geospatial & Drift Modeling - Reverse Backtracking Engine
Executes OpenDrift backward in time to estimate the initial discharge point,
discharge timestamp, and historical trajectory for vessel attribution.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Union, Optional
import numpy as np
import xarray as xr
from .exceptions import SimulationError

# Physics constants
BACKTRACK_TIME_STEP_MIN = 30    # minutes; backward advection sub-step
OUTPUT_INTERVAL_HOURS = 1       # hours; timestep written to NetCDF output


def run_backtrack(
    centroid_lon: float,
    centroid_lat: float,
    radius_meters: float,
    det_time: datetime,
    readers: List[Any],
    backtrack_hours: int = 12,
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE",
    slick_id: str = "SLICK-DETECTION-001",
    seed_mode: str = "distributed",
    seed_lons: Optional[np.ndarray] = None,
    seed_lats: Optional[np.ndarray] = None
) -> Tuple[List[float], str, List[List[float]]]:
    """
    Runs reverse Lagrangian advection to trace particles back to their estimated origin.

    Args:
      centroid_lon: Detection polygon centroid longitude.
      centroid_lat: Detection polygon centroid latitude.
      radius_meters: Approximate slick radius in meters.
      det_time: Detection timestamp (datetime).
      readers: List of OpenDrift readers (currents, winds).
      backtrack_hours: Duration to backtrack in hours.
      num_particles: Number of seeded particles.
      oil_type: ADIOS oil library identifier.
      slick_id: Slick ID for logging and temp file naming.
      seed_mode: "centroid" (single seed point) or "distributed" (particles across polygon).
      seed_lons: Array of longitudes for distributed seeding.
      seed_lats: Array of latitudes for distributed seeding.

    Returns:
      Tuple[origin_point, origin_time_str, track_coords]
        - origin_point: [lon, lat] of earliest estimated position.
        - origin_time_str: ISO8601 UTC string of origin timestamp.
        - track_coords: List of [lon, lat] waypoints from Origin -> Detection.
    """
    import uuid
    from opendrift.models.openoil import OpenOil
    uid = uuid.uuid4().hex[:8]
    o_back = OpenOil(loglevel=30)
    for r in readers:
        o_back.add_reader(r)

    if seed_mode == "distributed" and seed_lons is not None and seed_lats is not None:
        # Distributed seeding: particles dispersed across the detected slick polygon area
        o_back.seed_elements(
            lon=seed_lons,
            lat=seed_lats,
            radius=0,
            number=len(seed_lons),
            time=det_time,
            oil_type=oil_type
        )
    else:
        # Centroid seeding: single mathematical seed point at the polygon centroid
        o_back.seed_elements(
            lon=centroid_lon,
            lat=centroid_lat,
            radius=0,
            number=num_particles,
            time=det_time,
            oil_type=oil_type
        )

    back_nc = f"temp_back_{slick_id}_{uid}.nc"
    try:
        try:
            o_back.run(
                duration=timedelta(hours=backtrack_hours),
                time_step=timedelta(minutes=-BACKTRACK_TIME_STEP_MIN),  # Negative advection step
                time_step_output=timedelta(hours=OUTPUT_INTERVAL_HOURS),
                outfile=back_nc
            )
        except Exception as sim_err:
            raise SimulationError(
                stage="backtrack",
                message=f"OpenDrift reverse trajectory simulation failed near coastline or grid boundary: {str(sim_err)}",
                details={"slick_id": slick_id, "error": str(sim_err)}
            )

        with xr.open_dataset(back_nc) as ds_back:
            ds_back.load()
            b_lons = ds_back['lon'].values
            b_lats = ds_back['lat'].values
            b_times = ds_back['time'].values

            track_coords = []
            # Order chronologically: from Origin (past) -> Detection (T0)
            for t_idx in range(len(b_times) - 1, -1, -1):
                valid_mask = ~np.isnan(b_lons[t_idx])
                if np.any(valid_mask):
                    mean_lon = round(float(b_lons[t_idx, valid_mask].mean()), 5)
                    mean_lat = round(float(b_lats[t_idx, valid_mask].mean()), 5)
                    track_coords.append([mean_lon, mean_lat])

            if not track_coords:
                raise SimulationError(
                    stage="backtrack",
                    message="Backtracking failed: All particles stranded on the coastline immediately. Unable to reconstruct origin trajectory.",
                    details={"slick_id": slick_id, "num_particles": num_particles}
                )

            origin_point = track_coords[0] if track_coords else [round(centroid_lon, 5), round(centroid_lat, 5)]
            origin_time_str = np.datetime_as_string(b_times[-1], unit='s') + "Z"

        return origin_point, origin_time_str, track_coords

    finally:
        try:
            if os.path.exists(back_nc):
                os.remove(back_nc)
        except Exception:
            pass

