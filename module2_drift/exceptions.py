"""
Module 2: Geospatial & Drift Modeling - Shared Exception Types
Single source of truth for SimulationError.  Import from here in all submodules
to avoid duplicate class definitions across backtrack.py and forecast.py.
"""
from typing import Any, Dict, Optional


class SimulationError(Exception):
    """
    Raised when an OpenDrift simulation encounters a runtime failure.

    Attributes:
        stage (str): Pipeline stage that failed (``"backtrack"`` or ``"forecast"``).
        message (str): Human-readable description of the failure.
        details (dict): Optional structured metadata (slick_id, particle count, etc.).
    """

    def __init__(self, stage: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.details = details or {}
