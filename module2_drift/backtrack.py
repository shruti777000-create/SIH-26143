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
from opendrift.models.openoil import OpenOil


def run_backtrack(
    centroid_lon: float,
    centroid_lat: float,
    radius_meters: float,
    det_time: datetime,
    readers: List[Any],
    backtrack_hours: int = 12,
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE",
    slick_id: str = "SLICK"
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

    Returns:
      Tuple[origin_point, origin_time_str, track_coords]
        - origin_point: [lon, lat] of earliest estimated position.
        - origin_time_str: ISO8601 UTC string of origin timestamp.
        - track_coords: List of [lon, lat] waypoints from Origin -> Detection.
    """
    timestamp_key = int(det_time.timestamp())
    o_back = OpenOil(loglevel=30)
    for r in readers:
        o_back.add_reader(r)

    o_back.seed_elements(
        lon=centroid_lon,
        lat=centroid_lat,
        radius=radius_meters,
        number=num_particles,
        time=det_time,
        oil_type=oil_type
    )

    back_nc = f"temp_back_{slick_id}_{timestamp_key}.nc"
    try:
        o_back.run(
            duration=timedelta(hours=backtrack_hours),
            time_step=timedelta(minutes=-30),  # Negative advection step
            time_step_output=timedelta(hours=1),
            outfile=back_nc
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

            origin_point = track_coords[0] if track_coords else [round(centroid_lon, 5), round(centroid_lat, 5)]
            origin_time_str = np.datetime_as_string(b_times[-1], unit='s') + "Z"

        return origin_point, origin_time_str, track_coords

    finally:
        try:
            if os.path.exists(back_nc):
                os.remove(back_nc)
        except Exception:
            pass
