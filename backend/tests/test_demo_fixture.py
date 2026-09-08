"""
Unit tests for Member 1 Deterministic Demo Fixture.

Validates that:
- The demo fixture can be loaded from both the module provider and the JSON file.
- The fixture is valid according to Member 2's ContractARequest schema.
- slick_id is strictly 'DEMO-SLICK-001'.
- timestamp_utc is an explicit fixed UTC timestamp (not dynamically generated).
- geometry is a valid GeoJSON Polygon with coordinates in [longitude, latitude] order.
- coordinates reside in the open-water Arabian Sea off the coast of western India.
- area_km2 >= 0 and confidence is within [0.0, 1.0].
- raw demo detection dictionary converts cleanly via format_contract_a().
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from shapely.geometry import shape

from backend.demo_fixture import (
    FIXTURE_PATH,
    get_demo_contract_a,
    load_demo_contract_a_from_file,
    get_demo_raw_detection,
)
from backend.oil_spill_detector import format_contract_a


def test_demo_fixture_file_exists():
    """Verify that the JSON fixture file exists on disk."""
    assert FIXTURE_PATH.exists()
    assert FIXTURE_PATH.is_file()


def test_load_demo_contract_a():
    """Verify that both loading methods return identical valid fixtures."""
    from_provider = get_demo_contract_a()
    from_file = load_demo_contract_a_from_file()

    assert from_provider == from_file
    assert from_provider["slick_id"] == "DEMO-SLICK-001"


def test_validate_with_member2_contract_a_request():
    """Verify that Member 2's ContractARequest model accepts the demo fixture."""
    from module2_drift.api import ContractARequest

    payload = get_demo_contract_a()
    m2_request = ContractARequest(**payload)

    assert m2_request.slick_id == "DEMO-SLICK-001"
    assert m2_request.timestamp_utc == "2026-09-04T12:00:00Z"
    assert m2_request.area_km2 == pytest.approx(2.45)
    assert m2_request.confidence == pytest.approx(0.92)


def test_slick_id_is_identifiable_demo():
    """Verify that slick_id is clearly labeled as DEMO."""
    payload = get_demo_contract_a()
    assert payload["slick_id"] == "DEMO-SLICK-001"
    assert payload["slick_id"].startswith("DEMO-")


def test_timestamp_utc_is_fixed_explicit_utc():
    """Verify that timestamp_utc is a fixed UTC string and not dynamically generated."""
    payload = get_demo_contract_a()
    ts = payload["timestamp_utc"]

    # Explicit fixed timestamp check
    assert ts == "2026-09-04T12:00:00Z"

    # Strict UTC parsing
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)


def test_geometry_is_valid_geojson_polygon():
    """Verify that geometry is a valid, closed GeoJSON Polygon with >= 4 coordinate pairs."""
    payload = get_demo_contract_a()
    geom = payload["geometry"]

    assert geom["type"] == "Polygon"
    assert isinstance(geom["coordinates"], list)
    assert len(geom["coordinates"]) >= 1

    ring = geom["coordinates"][0]
    assert len(ring) >= 4, f"Ring must have >= 4 coordinates, got {len(ring)}"
    assert ring[0] == ring[-1], f"Ring must be closed: {ring[0]} != {ring[-1]}"

    # Verify with Shapely
    poly = shape(geom)
    assert poly.is_valid
    assert not poly.is_empty
    assert poly.geom_type == "Polygon"


def test_coordinates_are_lon_lat_in_arabian_sea():
    """
    Verify coordinates are [longitude, latitude] ordered and situated in the
    open-water Arabian Sea off Maharashtra / Bombay High.
    """
    payload = get_demo_contract_a()
    ring = payload["geometry"]["coordinates"][0]

    for pt in ring:
        lon, lat = pt[0], pt[1]
        # Coordinate ranges: Longitude 70°E to 73°E, Latitude 18°N to 20°N
        assert 70.0 <= lon <= 73.0, f"Longitude {lon} out of Arabian Sea corridor"
        assert 18.0 <= lat <= 20.0, f"Latitude {lat} out of Arabian Sea corridor"


def test_area_and_confidence_bounds():
    """Verify numerical bounds on area_km2 and confidence."""
    payload = get_demo_contract_a()

    assert payload["area_km2"] >= 0.0
    assert payload["area_km2"] == pytest.approx(2.45)

    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["confidence"] == pytest.approx(0.92)


def test_raw_demo_detection_adapter_integration():
    """Verify that the synthetic raw detector result converts cleanly via format_contract_a."""
    from module2_drift.api import ContractARequest

    raw_det = get_demo_raw_detection()
    contract_a = format_contract_a(
        detection_result=raw_det,
        slick_id="DEMO-SLICK-001",
        timestamp_utc="2026-09-04T12:00:00Z",
    )

    # Validate against Member 2
    req = ContractARequest(**contract_a)
    assert req.slick_id == "DEMO-SLICK-001"
    assert req.timestamp_utc == "2026-09-04T12:00:00Z"
    assert req.area_km2 == pytest.approx(2.45)
    assert req.confidence == pytest.approx(0.92)
