"""
Member 1 Deterministic Demo Fixture Provider

NOTICE:
This fixture is synthetic demonstration/test data. It is not output from the
trained Member 1 U-Net model. It does not claim or represent a real detected
oil spill.
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict

# Path to the JSON fixture
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_contract_a.json"

# Static deterministic Contract A payload
# Location: Open water in the Arabian Sea (offshore Bombay High / Maharashtra corridor)
DEMO_CONTRACT_A: Dict[str, Any] = {
    "slick_id": "DEMO-SLICK-001",
    "timestamp_utc": "2026-09-04T12:00:00Z",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [71.850, 19.270],
                [71.865, 19.270],
                [71.868, 19.282],
                [71.852, 19.285],
                [71.850, 19.270],
            ]
        ],
    },
    "area_km2": 2.45,
    "confidence": 0.92,
}


def get_demo_contract_a() -> Dict[str, Any]:
    """
    Return a copy of the deterministic Contract A demo fixture.

    NOTICE:
    This fixture is synthetic demonstration/test data. It is not output from the
    trained Member 1 U-Net model.
    """
    return copy.deepcopy(DEMO_CONTRACT_A)


def load_demo_contract_a_from_file(path: Path = FIXTURE_PATH) -> Dict[str, Any]:
    """
    Load the Contract A demo fixture from its canonical JSON file.

    NOTICE:
    This fixture is synthetic demonstration/test data. It is not output from the
    trained Member 1 U-Net model.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_demo_raw_detection() -> Dict[str, Any]:
    """
    Return a synthetic raw detector result dictionary matching detect_spill() output.
    Useful for testing the full Member 1 detect -> format_contract_a pipeline.

    NOTICE:
    This fixture is synthetic demonstration/test data. It is not output from the
    trained Member 1 U-Net model.
    """
    return {
        "detected": True,
        "confidence": 0.92,
        "area_km2": 2.45,
        "perimeter_km": 6.84,
        "geometry": copy.deepcopy(DEMO_CONTRACT_A["geometry"]),
        "centroid": {
            "longitude": 71.859,
            "latitude": 19.277,
        },
        "pixel_count": 2450,
        "source_image": "DEMO_S1A_SYNTHETIC_ARABIAN_SEA_20260904.tif",
    }
