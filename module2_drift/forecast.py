"""
Module 2: Geospatial & Drift Modeling - Forward Forecasting Engine
Executes forward OpenDrift Lagrangian advection and dispersion modelling to predict
oil slick spread envelopes at specified horizons (+6 h, +24 h).

Ensemble mode (default)
-----------------------
``run_forecast()`` launches *ensemble_size* independent OpenDrift simulations,
each with:

* A small Gaussian position jitter on every seed particle (``position_jitter_m``
  sigma, default 250 m) to sample initial-position uncertainty.
* OpenDrift's built-in ``horizontal_diffusivity`` (50 m^2/s) for within-run
  stochastic turbulent spread.

All member particle clouds are pooled at each forecast timestep and converted
to a single GeoJSON Polygon (concave/convex hull + buffer).  The output schema
is identical to the old single-run format so Contract B remains unchanged.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import shapely
import xarray as xr
from shapely.geometry import MultiPoint, Point, Polygon
from .exceptions import SimulationError


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def particles_to_polygon_geojson(
    lons: np.ndarray,
    lats: np.ndarray,
    concave_ratio: float = 0.35,
    buffer_deg: float = 0.012,
) -> Dict[str, Any]:
    """
    Converts a particle cloud into a closed GeoJSON Polygon envelope.

    Uses Shapely concave_hull when available (Shapely >= 2.0), falling back
    to a buffered convex hull.  Coordinates are rounded to 5 decimal places.
    """
    valid_mask = ~np.isnan(lons) & ~np.isnan(lats)
    valid_lons = lons[valid_mask]
    valid_lats = lats[valid_mask]

    if len(valid_lons) < 3:
        center_lon = float(np.nanmean(lons)) if len(valid_lons) > 0 else 72.0
        center_lat = float(np.nanmean(lats)) if len(valid_lats) > 0 else 19.0
        poly = Point(center_lon, center_lat).buffer(buffer_deg)
        coords = [
            [[round(float(c[0]), 5), round(float(c[1]), 5)] for c in poly.exterior.coords]
        ]
        return {"type": "Polygon", "coordinates": coords}

    multi_point = MultiPoint(
        [Point(x, y) for x, y in zip(valid_lons, valid_lats)]
    )

    if hasattr(shapely, "concave_hull"):
        try:
            hull = shapely.concave_hull(multi_point, ratio=concave_ratio, allow_holes=False)
            if not isinstance(hull, Polygon) or hull.is_empty:
                hull = multi_point.convex_hull
        except Exception:
            hull = multi_point.convex_hull
    else:
        hull = multi_point.convex_hull

    buffered = hull.buffer(buffer_deg)
    if buffered.geom_type == "MultiPolygon":
        buffered = buffered.convex_hull

    simplified = buffered.simplify(0.001, preserve_topology=True)
    if simplified.geom_type == "MultiPolygon":
        simplified = simplified.convex_hull

    exterior_coords = [
        [round(float(pt[0]), 5), round(float(pt[1]), 5)]
        for pt in simplified.exterior.coords
    ]
    if exterior_coords and exterior_coords[0] != exterior_coords[-1]:
        exterior_coords.append(exterior_coords[0])

    return {"type": "Polygon", "coordinates": [exterior_coords]}


def _polygon_area_km2(geojson_polygon: Dict[str, Any]) -> float:
    """
    Approximate area of a GeoJSON Polygon in km^2 using a local
    equirectangular projection (adequate for small coastal areas).
    """
    try:
        coords = geojson_polygon["coordinates"][0]
        if len(coords) < 4:
            return 0.0
        lons_p = np.array([c[0] for c in coords])
        lats_p = np.array([c[1] for c in coords])
        mean_lat_rad = np.radians(np.mean(lats_p))
        xs = lons_p * 111.0 * np.cos(mean_lat_rad)
        ys = lats_p * 111.0
        n = len(xs)
        area = 0.5 * abs(
            sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))
        )
        return round(area, 3)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Ensemble helpers
# ---------------------------------------------------------------------------

def _jitter_seeds(
    lons: np.ndarray,
    lats: np.ndarray,
    jitter_m: float,
    rng: np.random.Generator,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Adds independent Gaussian noise (sigma = jitter_m metres) to each
    seed particle position.

    Conversion:  1 deg lat ~ 111 km,  1 deg lon ~ 111 km * cos(lat).
    Member 0 (jitter_m == 0) returns the arrays unchanged.
    """
    if jitter_m <= 0.0:
        return lons.copy(), lats.copy()

    mean_lat_rad = np.radians(np.nanmean(lats))
    jitter_deg_lat = jitter_m / 111_000.0
    jitter_deg_lon = jitter_m / (111_000.0 * max(np.cos(mean_lat_rad), 1e-6))

    jlon = rng.normal(0.0, jitter_deg_lon, size=len(lons))
    jlat = rng.normal(0.0, jitter_deg_lat, size=len(lats))

    return (
        np.clip(lons + jlon, -180.0, 180.0),
        np.clip(lats + jlat, -90.0, 90.0),
    )


def _run_single_member(
    member_idx: int,
    seed_lons: Optional[np.ndarray],
    seed_lats: Optional[np.ndarray],
    centroid_lon: float,
    centroid_lat: float,
    num_particles: int,
    det_time: datetime,
    readers: List[Any],
    max_forecast_hours: int,
    forecast_hours: List[int],
    oil_type: str,
    slick_id: str,
    seed_mode: str,
    position_jitter_m: float,
    horizontal_diffusivity: float,
) -> Dict[int, Tuple[np.ndarray, np.ndarray]]:
    """
    Runs one ensemble member forward in time and returns particle positions
    at each requested forecast horizon.

    Returns an empty dict on simulation failure so that partial failures
    do not abort the entire ensemble.
    """
    uid = uuid.uuid4().hex[:8]
    fore_nc = f"temp_fore_{slick_id}_m{member_idx}_{uid}.nc"

    from opendrift.models.openoil import OpenOil
    o = OpenOil(loglevel=50)
    for r in readers:
        o.add_reader(r)

    # Enable stochastic within-run turbulent diffusion
    try:
        o.set_config("drift:horizontal_diffusivity", horizontal_diffusivity)
    except Exception:
        pass  # Config key may vary across OpenDrift versions

    # Apply position jitter (member 0 = zero jitter = deterministic baseline)
    rng = np.random.default_rng(seed=member_idx)
    jitter_m = 0.0 if member_idx == 0 else position_jitter_m

    if seed_mode == "distributed" and seed_lons is not None and seed_lats is not None:
        m_lons, m_lats = _jitter_seeds(seed_lons, seed_lats, jitter_m, rng)
        o.seed_elements(
            lon=m_lons,
            lat=m_lats,
            radius=0,
            number=len(m_lons),
            time=det_time,
            oil_type=oil_type,
        )
    else:
        # Centroid mode: jitter the centroid, then seed around it
        c_lons = np.array([centroid_lon])
        c_lats = np.array([centroid_lat])
        jc_lons, jc_lats = _jitter_seeds(c_lons, c_lats, jitter_m, rng)
        o.seed_elements(
            lon=float(jc_lons[0]),
            lat=float(jc_lats[0]),
            radius=0,
            number=num_particles,
            time=det_time,
            oil_type=oil_type,
        )

    try:
        o.run(
            duration=timedelta(hours=max_forecast_hours),
            time_step=timedelta(minutes=30),
            time_step_output=timedelta(hours=1),
            outfile=fore_nc,
        )
    except Exception:
        return {}  # Silent skip — logged at ensemble level

    result: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
    try:
        with xr.open_dataset(fore_nc) as ds:
            ds.load()
            f_lons = ds["lon"].values   # shape: (time, particles)
            f_lats = ds["lat"].values
            f_times = ds["time"].values

            for h in forecast_hours:
                target_t = np.datetime64(det_time) + np.timedelta64(h, "h")
                t_idx = int(np.argmin(np.abs(f_times - target_t)))
                result[h] = (f_lons[t_idx].copy(), f_lats[t_idx].copy())
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(fore_nc):
                os.remove(fore_nc)
        except Exception:
            pass

    return result




# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def run_forecast(
    centroid_lon: float,
    centroid_lat: float,
    radius_meters: float,  # reserved for API compatibility; not used in ensemble engine
    det_time: datetime,
    readers: List[Any],
    forecast_hours: Optional[List[int]] = None,
    num_particles: int = 100,
    oil_type: str = "GENERIC MEDIUM CRUDE",
    slick_id: str = "SLICK-DETECTION-001",
    seed_mode: str = "distributed",
    seed_lons: Optional[np.ndarray] = None,
    seed_lats: Optional[np.ndarray] = None,
    # Ensemble parameters
    ensemble_size: int = 5,
    position_jitter_m: float = 250.0,
    horizontal_diffusivity: float = 50.0,
) -> List[Dict[str, Any]]:
    """
    Runs an ensemble of forward Lagrangian simulations and returns pooled
    GeoJSON Polygon envelopes at each forecast horizon.

    Each of the *ensemble_size* members is an independent OpenDrift run:
    - Member 0: deterministic baseline (zero jitter).
    - Members 1..N: Gaussian position jitter (sigma = position_jitter_m metres)
      + stochastic horizontal diffusion (horizontal_diffusivity m^2/s).

    All member particle clouds are pooled at each timestep and passed to
    ``particles_to_polygon_geojson()`` to produce a single polygon whose
    width represents the ensemble spread / uncertainty zone.

    Args:
        centroid_lon:            Slick centroid longitude.
        centroid_lat:            Slick centroid latitude.
        radius_meters:           Approximate slick radius in metres (kept for
                                 API compatibility; not used directly here).
        det_time:                Detection timestamp (simulation t0).
        readers:                 OpenDrift metocean readers.
        forecast_hours:          Forward horizons in hours (default [6, 24]).
        num_particles:           Particles per member for centroid seeding.
        oil_type:                ADIOS oil identifier.
        slick_id:                Slick ID for temp-file naming.
        seed_mode:               "distributed" or "centroid".
        seed_lons:               Pre-sampled longitudes for distributed seeding.
        seed_lats:               Pre-sampled latitudes for distributed seeding.
        ensemble_size:           Number of independent ensemble members (default 5).
        position_jitter_m:       Gaussian 1-sigma position offset in metres
                                 for members 1..N (default 250 m ~ 0.0023 deg).
        horizontal_diffusivity:  Within-run turbulent diffusion in m^2/s (default 50).

    Returns:
        List matching Contract B ``forecast_polygons`` schema, e.g.::

            [
              {
                "hours_ahead": 6,
                "geometry": {"type": "Polygon", "coordinates": [...]},
                "ensemble_size": 5,
                "ensemble_spread_km2": 42.3
              },
              ...
            ]

    Raises:
        SimulationError: If *all* ensemble members fail.
    """
    if forecast_hours is None:
        forecast_hours = [6, 24]

    max_forecast = max(forecast_hours)

    # ---- Run all ensemble members ----------------------------------------
    # pooled[h] = list of (lons_array, lats_array) from each successful member
    pooled: Dict[int, List[Tuple[np.ndarray, np.ndarray]]] = {h: [] for h in forecast_hours}
    successful_members = 0

    for member_idx in range(ensemble_size):
        member_result = _run_single_member(
            member_idx=member_idx,
            seed_lons=seed_lons,
            seed_lats=seed_lats,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            num_particles=num_particles,
            det_time=det_time,
            readers=readers,
            max_forecast_hours=max_forecast,
            forecast_hours=forecast_hours,
            oil_type=oil_type,
            slick_id=slick_id,
            seed_mode=seed_mode,
            position_jitter_m=position_jitter_m,
            horizontal_diffusivity=horizontal_diffusivity,
        )
        if member_result:
            successful_members += 1
            for h, (lons_arr, lats_arr) in member_result.items():
                if h in pooled:
                    pooled[h].append((lons_arr, lats_arr))

    if successful_members == 0:
        raise SimulationError(
            stage="forecast",
            message=(
                "Ensemble forecast failed: all ensemble members crashed "
                "(coastline stranding or grid-edge boundary violations). "
                "Try moving the slick polygon further offshore."
            ),
            details={
                "slick_id": slick_id,
                "ensemble_size": ensemble_size,
                "successful_members": 0,
            },
        )

    # ---- Pool and polygonise at each horizon ----------------------------
    forecast_polygons: List[Dict[str, Any]] = []

    for h in forecast_hours:
        member_clouds = pooled[h]

        if not member_clouds:
            # Horizon had no data — return centroid fallback
            poly_geom = particles_to_polygon_geojson(
                np.array([centroid_lon]),
                np.array([centroid_lat]),
                buffer_deg=0.012,
            )
            forecast_polygons.append({
                "hours_ahead": h,
                "geometry": poly_geom,
                "ensemble_size": 0,
                "ensemble_spread_km2": 0.0,
            })
            continue

        all_lons = np.concatenate([lons for lons, _ in member_clouds])
        all_lats = np.concatenate([lats for _, lats in member_clouds])

        # Buffer grows with horizon: +6 h → base×1.125, +24 h → base×1.5, cap at base×2.
        # Rationale: particle cloud spatial uncertainty expands approximately linearly
        # with advection time in open-water conditions.
        buffer_scale = min(1.0 + (h / 24.0) * 0.5, 2.0)
        buffer_deg = round(0.012 * buffer_scale, 4)

        poly_geom = particles_to_polygon_geojson(
            all_lons,
            all_lats,
            concave_ratio=0.35,
            buffer_deg=buffer_deg,
        )

        spread_km2 = _polygon_area_km2(poly_geom)

        forecast_polygons.append({
            "hours_ahead": h,
            "geometry": poly_geom,
            "ensemble_size": successful_members,
            "ensemble_spread_km2": spread_km2,
        })

    return forecast_polygons
