"""
Module 2: Geospatial & Drift Modeling Package

Lazy-loads OpenDrift-dependent submodules so that tests for schema
validation, error handling, and geometry helpers can run in environments
where OpenDrift is not installed.
"""

from .exceptions import SimulationError
from .validate_schema import validate_drift_output
from .data_loader import (
    inspect_netcdf,
    detect_variable_mapping,
    DEFAULT_BBOX,
    DEFAULT_ARABIAN_SEA_BBOX,
    MetoceanDateOutOfRangeError,
    MetoceanSpatialOutOfRangeError,
)


def __getattr__(name):
    """Lazy-load symbols that depend on opendrift to avoid import errors
    in environments where opendrift is not installed."""
    if name == "forecast_drift":
        from .drift_model import forecast_drift
        return forecast_drift
    if name == "app":
        from .api import app
        return app
    if name == "load_metocean_reader":
        from .data_loader import load_metocean_reader
        return load_metocean_reader
    if name == "load_environment_data":
        from .data_loader import load_environment_data
        return load_environment_data
    if name == "run_backtrack":
        from .backtrack import run_backtrack
        return run_backtrack
    if name == "run_forecast":
        from .forecast import run_forecast
        return run_forecast
    raise AttributeError(f"module 'module2_drift' has no attribute {name!r}")


__all__ = [
    "app",
    "forecast_drift",
    "load_metocean_reader",
    "inspect_netcdf",
    "detect_variable_mapping",
    "load_environment_data",
    "DEFAULT_BBOX",
    "DEFAULT_ARABIAN_SEA_BBOX",
    "MetoceanDateOutOfRangeError",
    "MetoceanSpatialOutOfRangeError",
    "run_backtrack",
    "run_forecast",
    "SimulationError",
    "validate_drift_output",
]
