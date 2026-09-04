"""
Module 2: Geospatial & Drift Modeling - Metocean Data Loader
Handles inspection, variable name translation, coordinate alignment, and ingestion
of Ocean Current and Wind NetCDF files (e.g., CMEMS, HYCOM, ERA5, GFS) into OpenDrift readers.
"""

import os
from typing import Dict, Optional, Tuple, Any, List
import numpy as np
import xarray as xr


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

    print(f"\n[Metocean Loader] Ingesting: {os.path.basename(filepath)}")
    print(f" -> Detected Variable Mapping:")
    for file_var, od_var in detected_mapping.items():
        print(f"    * '{file_var}'  -->  '{od_var}'")

    if not detected_mapping:
        print(" [!] Warning: No canonical variables auto-matched. Relying on OpenDrift CF standard metadata.")

    ds = xr.open_dataset(filepath)

    # Normalize longitude from 0..360 to -180..180 if needed
    lon_name = _find_coord(ds, ['lon', 'longitude', 'nav_lon', 'x'])
    if lon_name and float(ds[lon_name].max()) > 180.0:
        print(" -> Converting longitude scale from [0, 360] to [-180, 180]...")
        ds = ds.assign_coords({lon_name: (((ds[lon_name] + 180) % 360) - 180)})
        ds = ds.sortby(lon_name)

    # If dataset has multiple vertical levels/depths, select surface level (0)
    depth_name = _find_coord(ds, ['depth', 'lev', 'level', 'z'])
    if depth_name and depth_name in ds.dims and ds.sizes[depth_name] > 1:
        print(f" -> Multi-level dataset detected. Selecting surface layer ({depth_name}=0)...")
        ds = ds.isel({depth_name: 0})

    from opendrift.readers import reader_netCDF_CF_generic
    name = reader_name or os.path.basename(filepath)
    reader = reader_netCDF_CF_generic.Reader(
        filename=ds,
        name=name,
        standard_name_mapping=detected_mapping
    )

    print(f" -> Successfully initialized OpenDrift reader '{reader.name}'")
    print(f" -> Variables served: {reader.variables}")
    return reader


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
    print(f"\n[Data Loader] Generating NetCDFs for Mumbai / Bombay High [71.0-73.5E, 18.0-20.0N]...")
    lons = np.linspace(71.0, 73.5, 51)
    lats = np.linspace(18.0, 20.0, 41)
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
