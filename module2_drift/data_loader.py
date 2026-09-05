"""
Module 2: Geospatial & Drift Modeling - Metocean Data Loader
Handles inspection, variable name translation, coordinate alignment, and ingestion
of Ocean Current and Wind NetCDF files (e.g., CMEMS, HYCOM, ERA5, GFS) into OpenDrift readers.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, List, Union
import numpy as np
import xarray as xr

_logger = logging.getLogger(__name__)


# Canonical OpenDrift standard target variables and synonyms
OPENDRIFT_STANDARD_TARGETS = {
    'x_sea_water_velocity': [
        'uo', 'u', 'water_u', 'u_current', 'eastward_sea_water_velocity',
        'x_sea_water_velocity', 'ucur', 'u_vel', 'curr_u', 'surf_u',
        'u_curr', 'zonal_current', 'eastward_current'
    ],
    'y_sea_water_velocity': [
        'vo', 'v', 'water_v', 'v_current', 'northward_sea_water_velocity',
        'y_sea_water_velocity', 'vcur', 'v_vel', 'curr_v', 'surf_v',
        'v_curr', 'meridional_current', 'northward_current'
    ],
    'x_wind': [
        'u10', 'uwnd', 'u_wind', 'wind_u', 'eastward_wind',
        'x_wind', 'u10n', 'u_10m', '10u', 'u_surface_wind', 'wnd_u',
        'ugrd10m', 'ugrd_10m', 'ugrd', 'u-component_of_wind_height_above_ground'
    ],
    'y_wind': [
        'v10', 'vwnd', 'v_wind', 'wind_v', 'northward_wind',
        'y_wind', 'v10n', 'v_10m', '10v', 'v_surface_wind', 'wnd_v',
        'vgrd10m', 'vgrd_10m', 'vgrd', 'v-component_of_wind_height_above_ground'
    ],
    'sea_water_temperature': [
        'thetao', 'sst', 'temperature', 'sea_surface_temperature',
        'temp', 't_sea_water', 'water_temp', 'to'
    ],
    'sea_surface_wave_significant_height': [
        'swh', 'hs', 'significant_wave_height', 'wave_height', 'htsgw',
        'vhm0'
    ]
}

DEFAULT_ARABIAN_SEA_BBOX = [71.0, 18.0, 73.5, 20.0]  # [min_lon, min_lat, max_lon, max_lat]
DEFAULT_BBOX = DEFAULT_ARABIAN_SEA_BBOX
METOCEAN_TIME_TOLERANCE_HOURS = 1


class MetoceanDateOutOfRangeError(ValueError):
    """Raised when the requested simulation date is not covered by any local NetCDF dataset."""
    def __init__(self, requested_date: Any, available_ranges: List[Dict[str, Any]], message: Optional[str] = None):
        if not message:
            ranges_str = "; ".join([
                f"'{r.get('filename', '')}' ({r.get('var_type', 'data')}: {r.get('start_str', '')} to {r.get('end_str', '')}, bounds: {r.get('lon_min', 0.0):.1f}-{r.get('lon_max', 0.0):.1f}°E, {r.get('lat_min', 0.0):.1f}-{r.get('lat_max', 0.0):.1f}°N)"
                for r in available_ranges
            ]) if available_ranges else "None (no valid local NetCDF metocean files found)"
            message = (
                f"Requested date '{requested_date}' falls outside available local NetCDF data. "
                f"Available local dataset ranges: [{ranges_str}]. "
                f"Please supply a NetCDF file covering the requested date."
            )
        super().__init__(message)
        self.requested_date = requested_date
        self.available_ranges = available_ranges
        self.message = message


class MetoceanSpatialOutOfRangeError(ValueError):
    """Raised when the requested bounding box is outside available local NetCDF datasets."""
    def __init__(self, requested_bbox: List[float], available_bounds: List[Dict[str, Any]], message: Optional[str] = None):
        if not message:
            bounds_str = "; ".join([
                f"'{b.get('filename', '')}': [{b.get('bounds', [])}]"
                for b in available_bounds
            ])
            message = (
                f"Requested bounding box {requested_bbox} falls outside available local NetCDF spatial coverage. "
                f"Available local bounds: [{bounds_str}]."
            )
        super().__init__(message)
        self.requested_bbox = requested_bbox
        self.available_bounds = available_bounds
        self.message = message



def _find_coord(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    """Helper to find coordinate name in dataset."""
    for c in candidates:
        if c in ds.coords:
            return c
        if c in ds.dims:
            return c
    return None


def inspect_netcdf(filepath: str) -> Dict[str, Any]:
    """
    Inspects a NetCDF file, returning dimensions, coordinate bounds, 
    and variable metadata.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"NetCDF file not found: {filepath}")

    with xr.open_dataset(filepath) as ds:
        info = {
            "filepath": filepath,
            "dimensions": dict(ds.sizes),
            "coordinates": list(ds.coords.keys()),
            "variables": list(ds.data_vars.keys()),
            "var_details": {}
        }
        
        lon_name = _find_coord(ds, ['lon', 'longitude', 'nav_lon', 'x'])
        lat_name = _find_coord(ds, ['lat', 'latitude', 'nav_lat', 'y'])
        time_name = _find_coord(ds, ['time', 'valid_time', 'step', 't'])

        if lon_name:
            info["lon_range"] = (float(ds[lon_name].min()), float(ds[lon_name].max()))
        if lat_name:
            info["lat_range"] = (float(ds[lat_name].min()), float(ds[lat_name].max()))
        if time_name:
            info["time_range"] = (
                str(np.datetime_as_string(ds[time_name].values[0], unit='s')),
                str(np.datetime_as_string(ds[time_name].values[-1], unit='s'))
            )

        for var_name, var in ds.data_vars.items():
            info["var_details"][var_name] = {
                "shape": var.shape,
                "dims": var.dims,
                "standard_name": var.attrs.get("standard_name", ""),
                "long_name": var.attrs.get("long_name", ""),
                "units": var.attrs.get("units", "")
            }

        return info


def check_metocean_coverage(
    filepath: str,
    centroid_lon: float,
    centroid_lat: float,
    target_time: Optional[datetime] = None,
    polygon_bounds: Optional[Tuple[float, float, float, float]] = None,
    backtrack_hours: int = 12,
    forecast_hours: int = 24
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validates that a location/polygon and time window fall within the spatial
    and temporal domain of the NetCDF dataset, and verifies that the location
    is offshore (not on land).

    Returns:
      (True, None) if within coverage.
      (False, error_dict) if coverage check fails.
    """
    if not os.path.exists(filepath):
        return False, {
            "error": True,
            "error_type": "DATASET_NOT_FOUND",
            "reason": f"Metocean dataset file not found: '{filepath}'. Please check the file path or download required forcing data.",
            "details": {"filepath": filepath}
        }

    try:
        with xr.open_dataset(filepath) as ds:
            lon_name = _find_coord(ds, ['lon', 'longitude', 'nav_lon', 'x'])
            lat_name = _find_coord(ds, ['lat', 'latitude', 'nav_lat', 'y'])
            time_name = _find_coord(ds, ['time', 'valid_time', 'step', 't'])

            if not lon_name or not lat_name:
                return True, None

            lon_min = float(ds[lon_name].min())
            lon_max = float(ds[lon_name].max())
            lat_min = float(ds[lat_name].min())
            lat_max = float(ds[lat_name].max())

            # 1. Spatial Coverage Check (Bounding Box)
            # Check centroid
            if not (lon_min <= centroid_lon <= lon_max and lat_min <= centroid_lat <= lat_max):
                return False, {
                    "error": True,
                    "error_type": "SPATIAL_OUT_OF_BOUNDS",
                    "reason": (
                        f"Slick location [{centroid_lon:.4f}°E, {centroid_lat:.4f}°N] falls outside "
                        f"the dataset spatial coverage domain ([{lon_min:.2f} to {lon_max:.2f}°E, {lat_min:.2f} to {lat_max:.2f}°N])."
                    ),
                    "details": {
                        "location": [centroid_lon, centroid_lat],
                        "dataset_bounds": {
                            "lon_min": lon_min, "lon_max": lon_max,
                            "lat_min": lat_min, "lat_max": lat_max
                        }
                    }
                }

            # Check polygon bounds if provided
            if polygon_bounds:
                minx, miny, maxx, maxy = polygon_bounds
                if minx < lon_min or maxx > lon_max or miny < lat_min or maxy > lat_max:
                    return False, {
                        "error": True,
                        "error_type": "SPATIAL_OUT_OF_BOUNDS",
                        "reason": (
                            f"Slick polygon boundary extends outside the dataset spatial domain. "
                            f"Polygon bounds: [{minx:.3f}..{maxx:.3f}°E, {miny:.3f}..{maxy:.3f}°N], "
                            f"Dataset bounds: [{lon_min:.2f}..{lon_max:.2f}°E, {lat_min:.2f}..{lat_max:.2f}°N]."
                        ),
                        "details": {
                            "polygon_bounds": {"min_lon": minx, "max_lon": maxx, "min_lat": miny, "max_lat": maxy},
                            "dataset_bounds": {"min_lon": lon_min, "max_lon": lon_max, "min_lat": lat_min, "max_lat": lat_max}
                        }
                    }

            # 2. Land / Terrestrial Topography Check
            # Check if ocean current velocities are masked (NaN) or point is known terrestrial mainland
            for v_name in ['uo', 'u', 'water_u', 'x_sea_water_velocity']:
                if v_name in ds.data_vars:
                    try:
                        sample_var = ds[v_name].isel({time_name: 0}) if time_name in ds[v_name].dims else ds[v_name]
                        if len(sample_var.dims) > 2:
                            sample_var = sample_var.isel({d: 0 for d in sample_var.dims if d not in [lat_name, lon_name]})
                        val = float(sample_var.sel({lat_name: centroid_lat, lon_name: centroid_lon}, method='nearest').values)
                        if np.isnan(val):
                            return False, {
                                "error": True,
                                "error_type": "LAND_INTERSECTION",
                                "reason": (
                                    f"Slick coordinates [{centroid_lon:.4f}°E, {centroid_lat:.4f}°N] are situated on land "
                                    f"or in an unmodeled intertidal zone. Ocean hydrodynamic currents are unavailable for land points."
                                ),
                                "details": {
                                    "location": [centroid_lon, centroid_lat],
                                    "variable_tested": v_name
                                }
                            }
                    except Exception:
                        pass
                    break

            # In the Maharashtra / Arabian Sea context: coordinates east of coastline (e.g. lon > 73.0 near Mumbai) are terrestrial land
            if 18.5 <= centroid_lat <= 19.5 and centroid_lon >= 73.05:
                return False, {
                    "error": True,
                    "error_type": "LAND_INTERSECTION",
                    "reason": (
                        f"Slick coordinates [{centroid_lon:.4f}°E, {centroid_lat:.4f}°N] are located inland on the Maharashtra mainland. "
                        f"Ocean drift modeling cannot be executed on land."
                    ),
                    "details": {"location": [centroid_lon, centroid_lat]}
                }

            # 3. Temporal Coverage Check
            if time_name and target_time is not None:
                t_vals = ds[time_name].values
                t_start = np.datetime64(t_vals[0], 's').astype('datetime64[s]').astype(datetime)
                t_end = np.datetime64(t_vals[-1], 's').astype('datetime64[s]').astype(datetime)
                
                t_start_str = t_vals[0].astype('str') if hasattr(t_vals[0], 'astype') else str(t_vals[0])
                t_end_str = t_vals[-1].astype('str') if hasattr(t_vals[-1], 'astype') else str(t_vals[-1])
                if not t_start_str.endswith('Z'):
                    t_start_str += 'Z'
                if not t_end_str.endswith('Z'):
                    t_end_str += 'Z'

                # Check if target detection time itself is outside
                if target_time < t_start or target_time > t_end:
                    return False, {
                        "error": True,
                        "error_type": "TEMPORAL_OUT_OF_BOUNDS",
                        "reason": (
                            f"Requested timestamp {target_time.isoformat()}Z is outside available metocean dataset range "
                            f"({t_start_str} to {t_end_str}). Please supply metocean data covering this event."
                        ),
                        "details": {
                            "requested_time": target_time.isoformat() + "Z",
                            "data_start": t_start_str,
                            "data_end": t_end_str
                        }
                    }

                # Check if backtrack window exceeds start
                required_backtrack_start = target_time - timedelta(hours=backtrack_hours)
                if required_backtrack_start < t_start:
                    return False, {
                        "error": True,
                        "error_type": "TEMPORAL_OUT_OF_BOUNDS",
                        "reason": (
                            f"Backtrack duration (-{backtrack_hours}h) requires metocean data back to "
                            f"{required_backtrack_start.isoformat()}Z, but dataset only begins at {t_start_str}."
                        ),
                        "details": {
                            "requested_backtrack_start": required_backtrack_start.isoformat() + "Z",
                            "data_start": t_start_str,
                            "backtrack_hours": backtrack_hours
                        }
                    }

        return True, None

    except Exception as e:
        return False, {
            "error": True,
            "error_type": "METOCEAN_READ_ERROR",
            "reason": f"Failed inspecting metocean file '{filepath}': {str(e)}",
            "details": {"filepath": filepath, "exception": str(e)}
        }



def detect_variable_mapping(filepath: str) -> Dict[str, str]:
    """
    Inspects variable names and attributes in the NetCDF file and returns
    a mapping dictionary of {file_var_name: opendrift_standard_name}.
    """
    mapping = {}
    with xr.open_dataset(filepath) as ds:
        for var_name, var in ds.data_vars.items():
            std_attr = str(var.attrs.get("standard_name", "")).lower().strip()
            long_attr = str(var.attrs.get("long_name", "")).lower().strip()
            var_lower = var_name.lower().strip()

            matched_target = None
            # 1. First priority: Exact variable name match
            for target_std, candidates in OPENDRIFT_STANDARD_TARGETS.items():
                if var_lower in [c.lower() for c in candidates]:
                    matched_target = target_std
                    break

            # 2. Second priority: Standard name / long name exact or key phrase match
            if not matched_target:
                if any(k in std_attr or k in long_attr for k in ['eastward_sea_water', 'eastward velocity', 'u-velocity of current', 'u-current', 'zonal current']):
                    matched_target = 'x_sea_water_velocity'
                elif any(k in std_attr or k in long_attr for k in ['northward_sea_water', 'northward velocity', 'v-velocity of current', 'v-current', 'meridional current']):
                    matched_target = 'y_sea_water_velocity'
                elif any(k in std_attr or k in long_attr for k in ['eastward_wind', '10m u-wind', '10 metre u wind', 'u-component of wind', 'zonal wind']):
                    matched_target = 'x_wind'
                elif any(k in std_attr or k in long_attr for k in ['northward_wind', '10m v-wind', '10 metre v wind', 'v-component of wind', 'meridional wind']):
                    matched_target = 'y_wind'
                elif any(k in std_attr or k in long_attr for k in ['sea_water_potential_temperature', 'sea surface temperature', 'water temperature']):
                    matched_target = 'sea_water_temperature'

            if matched_target:
                mapping[var_name] = matched_target

    return mapping


def load_metocean_reader(
    filepath: str,
    reader_name: Optional[str] = None,
    custom_mapping: Optional[Dict[str, str]] = None
) -> Any:
    """
    Loads a NetCDF file into an OpenDrift generic CF reader with automatic 
    variable name discovery, depth slicing, and coordinate alignment.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"NetCDF file does not exist: {filepath}")

    detected_mapping = detect_variable_mapping(filepath)
    if custom_mapping:
        detected_mapping.update(custom_mapping)

    _logger.info("Metocean Loader: ingesting %s", os.path.basename(filepath))
    _logger.debug("Detected variable mapping: %s", detected_mapping)

    if not detected_mapping:
        _logger.warning("No canonical variables auto-matched for %s; relying on OpenDrift CF metadata.", filepath)

    ds = xr.open_dataset(filepath)

    # Normalize longitude from 0..360 to -180..180 if needed
    lon_name = _find_coord(ds, ['lon', 'longitude', 'nav_lon', 'x'])
    if lon_name and float(ds[lon_name].max()) > 180.0:
        _logger.debug("Converting longitude scale from [0, 360] to [-180, 180] for %s", filepath)
        ds = ds.assign_coords({lon_name: (((ds[lon_name] + 180) % 360) - 180)})
        ds = ds.sortby(lon_name)

    # If dataset has multiple vertical levels/depths, select surface level (0)
    depth_name = _find_coord(ds, ['depth', 'lev', 'level', 'z'])
    if depth_name and depth_name in ds.dims and ds.sizes[depth_name] > 1:
        _logger.debug("Multi-level dataset: selecting surface layer (%s=0)", depth_name)
        ds = ds.isel({depth_name: 0})

    from opendrift.readers import reader_netCDF_CF_generic
    name = reader_name or os.path.basename(filepath)
    reader = reader_netCDF_CF_generic.Reader(
        filename=ds,
        name=name,
        standard_name_mapping=detected_mapping
    )

    _logger.info("Initialized OpenDrift reader '%s', variables: %s", reader.name, reader.variables)
    return reader


def discover_local_netcdf_catalog(search_dirs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Scans local directories for NetCDF files, discovering their variable types (currents vs winds),
    spatial bounding boxes, and time coverage horizons.
    Excludes temporary files (temp_*.nc) and virtual environments.
    """
    if search_dirs is None:
        search_dirs = [".", "data", "downloads", "raw_data"]

    catalog = []
    seen_paths = set()

    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue

        for root, dirs, files in os.walk(s_dir):
            # Exclude virtual environments, git, and caches
            dirs[:] = [d for d in dirs if d not in ('venv', '.venv', 'env', '.env', '__pycache__', '.git', 'site-packages')]
            for f in files:
                if f.endswith(".nc") and not f.startswith("temp_") and not f.startswith("test_"):
                    f_path = os.path.normpath(os.path.join(root, f))
                    if f_path in seen_paths:
                        continue
                    seen_paths.add(f_path)

                    try:
                        info = inspect_netcdf(f_path)
                        var_map = detect_variable_mapping(f_path)
                        targets = set(var_map.values())
                        has_currents = bool(targets & {'x_sea_water_velocity', 'y_sea_water_velocity'})
                        has_winds = bool(targets & {'x_wind', 'y_wind'})

                        if not has_currents and not has_winds:
                            var_names = [v.lower() for v in info.get("variables", [])]
                            if any(x in var_names for x in ['uo', 'vo', 'ucur', 'vcur', 'water_u', 'water_v']):
                                has_currents = True
                            if any(x in var_names for x in ['u10', 'v10', 'uwnd', 'vwnd', 'wind_u', 'wind_v']):
                                has_winds = True

                        if has_currents and has_winds:
                            v_type = "both"
                        elif has_currents:
                            v_type = "currents"
                        elif has_winds:
                            v_type = "winds"
                        else:
                            v_type = "unknown"

                        lon_range = info.get("lon_range", (-180.0, 180.0))
                        lat_range = info.get("lat_range", (-90.0, 90.0))
                        time_range = info.get("time_range")

                        time_start = None
                        time_end = None
                        start_str = ""
                        end_str = ""

                        if time_range:
                            start_str = time_range[0]
                            end_str = time_range[1]
                            try:
                                time_start = datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None)
                                time_end = datetime.fromisoformat(end_str.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                pass

                        catalog.append({
                            "filepath": f_path,
                            "filename": f,
                            "var_type": v_type,
                            "lon_min": lon_range[0],
                            "lon_max": lon_range[1],
                            "lat_min": lat_range[0],
                            "lat_max": lat_range[1],
                            "time_start": time_start,
                            "time_end": time_end,
                            "start_str": start_str,
                            "end_str": end_str,
                            "targets": list(targets)
                        })
                    except Exception:
                        continue

    return catalog


def load_environment_data(
    date: Union[str, datetime, Any],
    bbox: Optional[List[float]] = None,
    search_dirs: Optional[List[str]] = None,
    custom_mapping: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Selects and initializes metocean readers (currents and winds) dynamically
    based on the requested date and bounding box, matching available local NetCDF files.

    Args:
      date: Requested target date/timestamp (ISO8601 string or datetime).
      bbox: Optional bounding box [min_lon, min_lat, max_lon, max_lat].
            Defaults to DEFAULT_BBOX ([71.0, 18.0, 73.5, 20.0]).
      search_dirs: Optional directories to scan for NetCDF files.
      custom_mapping: Optional custom variable mapping dict.

    Returns:
      Dict with loaded readers and metadata:
      {
        "readers": [current_reader, wind_reader],
        "current_reader": current_reader,
        "wind_reader": wind_reader,
        "current_file": path_to_current_nc,
        "wind_file": path_to_wind_nc,
        "available_time_range": (start_dt, end_dt),
        "bbox": bbox
      }

    Raises:
      MetoceanDateOutOfRangeError: If the requested date falls outside available local NetCDF datasets,
                                  listing the exact date ranges that are actually available.
      MetoceanSpatialOutOfRangeError: If the requested bbox is outside available local coverage.
      FileNotFoundError: If no candidate NetCDF files are found.
    """
    if bbox is None:
        bbox = list(DEFAULT_BBOX)

    # 1. Parse date parameter
    if isinstance(date, datetime):
        target_dt = date.replace(tzinfo=None) if date.tzinfo else date
    elif isinstance(date, str):
        try:
            target_dt = datetime.fromisoformat(date.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            try:
                target_dt = datetime.strptime(date, "%Y-%m-%d")
            except Exception as e:
                raise ValueError(f"Invalid date format '{date}': {e}. Expected 'YYYY-MM-DD' or ISO8601 timestamp.")
    elif hasattr(date, "year") and hasattr(date, "month") and hasattr(date, "day"):
        target_dt = datetime(date.year, date.month, date.day)
    else:
        raise TypeError(f"Expected datetime or string date; got {type(date).__name__}")

    # 2. Discover local NetCDFs
    catalog = discover_local_netcdf_catalog(search_dirs)
    if not catalog:
        # Check if sample files exist in current directory
        if os.path.exists("arabian_sea_currents.nc") and os.path.exists("arabian_sea_winds.nc"):
            catalog = discover_local_netcdf_catalog(["."])
        else:
            raise FileNotFoundError(
                "No local NetCDF metocean files found on disk. Please supply NetCDF current and wind data files."
            )

    curr_candidates = [c for c in catalog if c["var_type"] in ("currents", "both")]
    wind_candidates = [c for c in catalog if c["var_type"] in ("winds", "both")]

    if not curr_candidates:
        raise FileNotFoundError("No NetCDF files serving ocean current data ('uo', 'vo') found in local catalog.")
    if not wind_candidates:
        raise FileNotFoundError("No NetCDF files serving wind data ('u10', 'v10') found in local catalog.")

    # 3. Match Currents by Date
    matched_curr = None
    for cand in curr_candidates:
        if cand["time_start"] and cand["time_end"]:
            # Check date match with 1 hour tolerance
            if cand["time_start"] - timedelta(hours=1) <= target_dt <= cand["time_end"] + timedelta(hours=1):
                matched_curr = cand
                break

    if matched_curr is None:
        ranges = [
            {
                "filename": c["filename"],
                "var_type": c["var_type"],
                "start_str": c["start_str"],
                "end_str": c["end_str"],
                "lon_min": c["lon_min"],
                "lon_max": c["lon_max"],
                "lat_min": c["lat_min"],
                "lat_max": c["lat_max"]
            }
            for c in curr_candidates
        ]
        raise MetoceanDateOutOfRangeError(
            requested_date=target_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            available_ranges=ranges
        )

    # 4. Match Winds by Date
    matched_wind = None
    for cand in wind_candidates:
        if cand["time_start"] and cand["time_end"]:
            if cand["time_start"] - timedelta(hours=METOCEAN_TIME_TOLERANCE_HOURS) <= target_dt <= cand["time_end"] + timedelta(hours=METOCEAN_TIME_TOLERANCE_HOURS):
                matched_wind = cand
                break

    if matched_wind is None:
        ranges = [
            {
                "filename": c["filename"],
                "var_type": c["var_type"],
                "start_str": c["start_str"],
                "end_str": c["end_str"],
                "lon_min": c["lon_min"],
                "lon_max": c["lon_max"],
                "lat_min": c["lat_min"],
                "lat_max": c["lat_max"]
            }
            for c in wind_candidates
        ]
        raise MetoceanDateOutOfRangeError(
            requested_date=target_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            available_ranges=ranges
        )

    # 5. Check Spatial Bounding Box Coverage
    req_min_lon, req_min_lat, req_max_lon, req_max_lat = bbox[0], bbox[1], bbox[2], bbox[3]
    if (matched_curr["lon_min"] > req_min_lon or matched_curr["lon_max"] < req_max_lon or
        matched_curr["lat_min"] > req_min_lat or matched_curr["lat_max"] < req_max_lat):
        available_bounds = [
            {"filename": matched_curr["filename"], "bounds": [matched_curr["lon_min"], matched_curr["lat_min"], matched_curr["lon_max"], matched_curr["lat_max"]]},
            {"filename": matched_wind["filename"], "bounds": [matched_wind["lon_min"], matched_wind["lat_min"], matched_wind["lon_max"], matched_wind["lat_max"]]}
        ]
        raise MetoceanSpatialOutOfRangeError(
            requested_bbox=bbox,
            available_bounds=available_bounds
        )

    # 6. Load OpenDrift Readers
    r_curr = load_metocean_reader(matched_curr["filepath"], reader_name="CurrentReader", custom_mapping=custom_mapping)
    r_wind = load_metocean_reader(matched_wind["filepath"], reader_name="WindReader", custom_mapping=custom_mapping)

    _logger.info(
        "Auto-selected metocean files for %s: currents=%s, winds=%s, domain=[%.1f..%.1f E, %.1f..%.1f N]",
        target_dt.isoformat(), matched_curr["filepath"], matched_wind["filepath"],
        req_min_lon, req_max_lon, req_min_lat, req_max_lat,
    )

    return {
        "readers": [r_curr, r_wind],
        "current_reader": r_curr,
        "wind_reader": r_wind,
        "current_file": matched_curr["filepath"],
        "wind_file": matched_wind["filepath"],
        "available_time_range": (matched_curr["time_start"], matched_curr["time_end"]),
        "bbox": bbox
    }


def generate_arabian_sea_sample_netcdf(
    current_out: str = "arabian_sea_currents.nc",
    wind_out: str = "arabian_sea_winds.nc",
    start_time: str = "2026-09-04T00:00:00"
) -> Tuple[str, str]:
    """
    Generates realistic NetCDF files for the Arabian Sea Maharashtra coast 
    (Mumbai/JNPT & Bombay High: lon 71.0 to 73.5, lat 18.0 to 20.0).
    Currents follow CMEMS naming ('uo', 'vo', 'thetao').
    Winds follow GFS/ERA5 naming ('u10', 'v10').
    """
    _logger.info("Generating sample NetCDFs for %s", DEFAULT_ARABIAN_SEA_BBOX)
    lon_min, lat_min, lon_max, lat_max = DEFAULT_ARABIAN_SEA_BBOX
    lons = np.linspace(lon_min, lon_max, 51)
    lats = np.linspace(lat_min, lat_max, 41)
    times = [np.datetime64(start_time) + np.timedelta64(h, 'h') for h in range(48)]

    lon_grid, lat_grid = np.meshgrid(lons, lats)

    uo_data = np.zeros((len(times), len(lats), len(lons)), dtype=np.float32)
    vo_data = np.zeros((len(times), len(lats), len(lons)), dtype=np.float32)

    for t_i in range(len(times)):
        tide_phase = 2 * np.pi * t_i / 12.42
        tidal_u = 0.12 * np.sin(tide_phase)
        tidal_v = 0.18 * np.cos(tide_phase)
        uo_data[t_i] = 0.08 + tidal_u + 0.02 * np.sin(lat_grid * 0.5)
        vo_data[t_i] = -0.22 + tidal_v + 0.03 * np.cos(lon_grid * 0.5)

    ds_currents = xr.Dataset(
        data_vars={
            "uo": (["time", "latitude", "longitude"], uo_data, {
                "standard_name": "eastward_sea_water_velocity",
                "long_name": "Eastward velocity of sea water",
                "units": "m/s"
            }),
            "vo": (["time", "latitude", "longitude"], vo_data, {
                "standard_name": "northward_sea_water_velocity",
                "long_name": "Northward velocity of sea water",
                "units": "m/s"
            }),
            "thetao": (["time", "latitude", "longitude"], np.full_like(uo_data, 29.0), {
                "standard_name": "sea_water_potential_temperature",
                "long_name": "Sea water potential temperature",
                "units": "degrees_C"
            })
        },
        coords={
            "longitude": lons,
            "latitude": lats,
            "time": times
        },
        attrs={
            "title": "Arabian Sea (Mumbai/JNPT & Bombay High) Currents - CMEMS Format",
            "region": "Arabian Sea (Maharashtra Shelf)",
            "bounding_box": "[71.0, 18.0, 73.5, 20.0]"
        }
    )
    ds_currents.to_netcdf(current_out)

    u10_data = np.zeros((len(times), len(lats), len(lons)), dtype=np.float32)
    v10_data = np.zeros((len(times), len(lats), len(lons)), dtype=np.float32)

    for t_i in range(len(times)):
        diurnal = 0.8 * np.sin(2 * np.pi * t_i / 24.0)
        u10_data[t_i] = 7.2 + diurnal + 0.3 * np.sin(lon_grid * 0.4)
        v10_data[t_i] = 4.1 + 0.5 * diurnal + 0.2 * np.cos(lat_grid * 0.4)

    ds_winds = xr.Dataset(
        data_vars={
            "u10": (["time", "latitude", "longitude"], u10_data, {
                "standard_name": "eastward_wind",
                "long_name": "10 metre U wind component",
                "units": "m s**-1"
            }),
            "v10": (["time", "latitude", "longitude"], v10_data, {
                "standard_name": "northward_wind",
                "long_name": "10 metre V wind component",
                "units": "m s**-1"
            })
        },
        coords={
            "longitude": lons,
            "latitude": lats,
            "time": times
        },
        attrs={
            "title": "Arabian Sea (Mumbai/JNPT & Bombay High) Winds - ERA5/GFS Format",
            "region": "Arabian Sea (Maharashtra Shelf)",
            "bounding_box": "[71.0, 18.0, 73.5, 20.0]"
        }
    )
    ds_winds.to_netcdf(wind_out)
    return current_out, wind_out
