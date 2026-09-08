"""
Unit tests for Member 1 Contract A Adapter and GeoTIFF metadata extraction.

Verifies:
- Detection output formatting into official Contract A payload for Member 2.
- Validation of slick_id, timestamp_utc, and GeoJSON geometry.
- Strict rejection of missing, invalid, naive, or non-UTC timestamps.
- Zero automatic timestamp invention (system time is never used).
- Optional metadata extraction from GeoTIFF tags (ACQUISITION_START_TIME, TIFFTAG_DATETIME).
- Compatibility with Member 2's ContractARequest schema.
"""

from pathlib import Path
import struct
import pytest

from backend.oil_spill_detector import (
    format_contract_a,
    extract_geotiff_timestamp,
    validate_slick_id,
    validate_timestamp_utc,
)


def _make_mock_tiff_with_tag(tag_id: int, text_value: str) -> bytes:
    """Helper to create a minimal in-memory TIFF byte string with a specified ASCII tag."""
    val_bytes = text_value.encode("ascii") + b"\x00"
    val_len = len(val_bytes)
    # Header: II (little-endian), magic 42, IFD offset = 8
    header = b"II\x2a\x00\x08\x00\x00\x00"
    ifd_count = struct.pack("<H", 1)
    val_offset = 8 + 2 + 12 + 4
    tag_entry = struct.pack("<HHI I", tag_id, 2, val_len, val_offset)
    next_ifd = b"\x00\x00\x00\x00"
    return header + ifd_count + tag_entry + next_ifd + val_bytes


@pytest.fixture
def sample_detection_result():
    """Realistic detection dictionary matching detect_spill() output."""
    return {
        "detected": True,
        "confidence": 0.935,
        "area_km2": 1.48,
        "perimeter_km": 5.12,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [72.820, 18.910],
                    [72.835, 18.910],
                    [72.840, 18.925],
                    [72.825, 18.930],
                    [72.820, 18.910],
                ]
            ],
        },
        "centroid": {
            "longitude": 72.830,
            "latitude": 18.919,
        },
        "pixel_count": 1280,
        "source_image": "S1A_IW_GRDH_1SDV_20260904.tif",
    }


# ===========================================================================
# 1. Contract A Conversion & Field Preservation
# ===========================================================================

def test_valid_detection_converts_to_contract_a(sample_detection_result):
    slick_id = "SLICK-AS-MUMBAI-20260904-001"
    timestamp_utc = "2026-09-04T12:00:00Z"

    contract_a = format_contract_a(
        detection_result=sample_detection_result,
        slick_id=slick_id,
        timestamp_utc=timestamp_utc,
    )

    # Core required fields
    assert contract_a["slick_id"] == slick_id
    assert contract_a["timestamp_utc"] == timestamp_utc
    assert contract_a["geometry"] == sample_detection_result["geometry"]

    # Optional fields preserved
    assert contract_a["area_km2"] == pytest.approx(1.48)
    assert contract_a["confidence"] == pytest.approx(0.935)

    # Internal / non-Contract A fields MUST be stripped
    forbidden_keys = {"detected", "perimeter_km", "centroid", "pixel_count", "source_image"}
    for key in forbidden_keys:
        assert key not in contract_a

    # Verify only Contract A keys are present
    assert set(contract_a.keys()) == {"slick_id", "timestamp_utc", "geometry", "area_km2", "confidence"}


def test_contract_a_interoperability_with_member2_schema(sample_detection_result):
    """Verify that Member 2's ContractARequest accepts the formatted Contract A payload."""
    from module2_drift.api import ContractARequest

    slick_id = "SLICK-TEST-VERIFIED-001"
    timestamp_utc = "2026-09-04T14:30:00Z"

    contract_a = format_contract_a(
        detection_result=sample_detection_result,
        slick_id=slick_id,
        timestamp_utc=timestamp_utc,
    )

    # Parse using Member 2's official Pydantic model
    m2_request = ContractARequest(**contract_a)
    assert m2_request.slick_id == slick_id
    assert m2_request.timestamp_utc == timestamp_utc
    assert m2_request.area_km2 == pytest.approx(1.48)
    assert m2_request.confidence == pytest.approx(0.935)
    assert len(m2_request.geometry.coordinates[0]) == 5


def test_optional_fields_handling(sample_detection_result):
    """Verify that area_km2 and confidence are optional in Contract A."""
    det = sample_detection_result.copy()
    det["area_km2"] = None
    det["confidence"] = None

    contract_a = format_contract_a(
        detection_result=det,
        slick_id="SLICK-NO-OPTIONAL-001",
        timestamp_utc="2026-09-04T12:00:00Z",
    )

    assert "area_km2" not in contract_a
    assert "confidence" not in contract_a
    assert set(contract_a.keys()) == {"slick_id", "timestamp_utc", "geometry"}

    # Must still be valid in Member 2 schema
    from module2_drift.api import ContractARequest
    req = ContractARequest(**contract_a)
    assert req.area_km2 is None
    assert req.confidence is None


# ===========================================================================
# 2. Validation: slick_id
# ===========================================================================

def test_slick_id_validation_success():
    assert validate_slick_id("SLICK-001") == "SLICK-001"
    assert validate_slick_id("  SLICK-SPACED-002  ") == "SLICK-SPACED-002"


@pytest.mark.parametrize("invalid_id", ["", "   ", "\t\n"])
def test_empty_or_whitespace_slick_id_rejected(sample_detection_result, invalid_id):
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        format_contract_a(sample_detection_result, slick_id=invalid_id, timestamp_utc="2026-09-04T12:00:00Z")


@pytest.mark.parametrize("non_string_id", [None, 12345, ["id"], {"id": 1}])
def test_non_string_slick_id_rejected(sample_detection_result, non_string_id):
    with pytest.raises(TypeError, match="slick_id must be a string"):
        format_contract_a(sample_detection_result, slick_id=non_string_id, timestamp_utc="2026-09-04T12:00:00Z")


# ===========================================================================
# 3. Validation: timestamp_utc
# ===========================================================================

@pytest.mark.parametrize("valid_ts", [
    "2026-09-04T12:00:00Z",
    "2026-09-04T12:00:00+00:00",
    "2026-09-04T12:00:00.500000Z",
    "2026-09-04T12:00:00.123+00:00",
])
def test_valid_iso_utc_timestamps_accepted(valid_ts):
    clean = validate_timestamp_utc(valid_ts)
    assert clean == valid_ts


@pytest.mark.parametrize("invalid_ts, match_err", [
    ("", "cannot be empty"),
    ("   ", "cannot be empty"),
    ("yesterday", "not a valid ISO 8601"),
    ("2026/09/04 12:00:00", "not a valid ISO 8601"),
    ("2026-09-04 12:00:00", "lacks timezone information"),  # naive
    ("2026-09-04T12:00:00", "lacks timezone information"),  # naive ISO
    ("2026-09-04T12:00:00+05:30", "non-zero UTC offset"),   # non-UTC timezone
    ("2026-09-04T12:00:00-04:00", "non-zero UTC offset"),   # non-UTC timezone
])
def test_invalid_timestamps_rejected(invalid_ts, match_err):
    with pytest.raises(ValueError, match=match_err):
        validate_timestamp_utc(invalid_ts)


def test_missing_timestamp_without_image_rejected(sample_detection_result):
    """When caller omits timestamp_utc and no valid image is supplied, raise ValueError."""
    with pytest.raises(ValueError, match="timestamp_utc is required"):
        format_contract_a(
            detection_result=sample_detection_result,
            slick_id="SLICK-NO-TIME-001",
            timestamp_utc=None,
            image_path=None,
        )


def test_no_system_time_fallback(sample_detection_result):
    """Verify that timestamp is never automatically invented from current clock."""
    with pytest.raises(ValueError, match="timestamp_utc is required"):
        format_contract_a(
            detection_result=sample_detection_result,
            slick_id="SLICK-NO-CLOCK-001",
        )


# ===========================================================================
# 4. Validation: Geometry and Detection Result
# ===========================================================================

def test_reject_non_dict_detection_result():
    with pytest.raises(TypeError, match="detection_result must be a dict"):
        format_contract_a(
            detection_result="not a dict",
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_when_no_spill_detected(sample_detection_result):
    det = sample_detection_result.copy()
    det["detected"] = False
    det["geometry"] = None

    with pytest.raises(ValueError, match="no oil spill was detected"):
        format_contract_a(
            detection_result=det,
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_missing_geometry(sample_detection_result):
    det = sample_detection_result.copy()
    del det["geometry"]

    with pytest.raises(ValueError, match="must contain a valid GeoJSON 'geometry'"):
        format_contract_a(
            detection_result=det,
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_non_polygon_geometry(sample_detection_result):
    det = sample_detection_result.copy()
    det["geometry"] = {"type": "Point", "coordinates": [72.82, 18.91]}

    with pytest.raises(ValueError, match="requires a GeoJSON Polygon"):
        format_contract_a(
            detection_result=det,
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_unclosed_polygon_ring(sample_detection_result):
    det = sample_detection_result.copy()
    det["geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [[72.8, 18.9], [72.9, 18.9], [72.9, 19.0], [72.85, 18.95]]  # open ring
        ],
    }

    with pytest.raises(ValueError, match="outer ring must be closed"):
        format_contract_a(
            detection_result=det,
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_degenerate_polygon_ring(sample_detection_result):
    det = sample_detection_result.copy()
    det["geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [[72.8, 18.9], [72.9, 18.9], [72.8, 18.9]]  # only 3 coords (2 unique)
        ],
    }

    with pytest.raises(ValueError, match="at least 4 coordinate pairs"):
        format_contract_a(
            detection_result=det,
            slick_id="SLICK-001",
            timestamp_utc="2026-09-04T12:00:00Z",
        )


def test_reject_invalid_numerical_bounds(sample_detection_result):
    det_bad_area = sample_detection_result.copy()
    det_bad_area["area_km2"] = -1.0
    with pytest.raises(ValueError, match="area_km2 cannot be negative"):
        format_contract_a(det_bad_area, slick_id="SLICK-001", timestamp_utc="2026-09-04T12:00:00Z")

    det_bad_conf = sample_detection_result.copy()
    det_bad_conf["confidence"] = 1.5
    with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
        format_contract_a(det_bad_conf, slick_id="SLICK-001", timestamp_utc="2026-09-04T12:00:00Z")


# ===========================================================================
# 5. GeoTIFF Metadata Extraction Helper
# ===========================================================================

def test_extract_geotiff_timestamp_tifftag_datetime(tmp_path):
    """Test extracting standard TIFFTAG_DATETIME (tag 306)."""
    mock_tiff = tmp_path / "mock_tifftag.tif"
    mock_tiff.write_bytes(_make_mock_tiff_with_tag(0x0132, "2026:09:04 12:00:00"))

    ts = extract_geotiff_timestamp(mock_tiff)
    assert ts == "2026-09-04T12:00:00Z"


def test_extract_geotiff_timestamp_acquisition_start_time(tmp_path):
    """Test extracting ACQUISITION_START_TIME from GDAL metadata XML tag (tag 42112)."""
    mock_tiff = tmp_path / "mock_gdal.tif"
    gdal_xml = (
        '<GDALMetadata>'
        '<Item name="ACQUISITION_START_TIME">2026-09-04T14:45:00Z</Item>'
        '</GDALMetadata>'
    )
    mock_tiff.write_bytes(_make_mock_tiff_with_tag(0xA480, gdal_xml))

    ts = extract_geotiff_timestamp(mock_tiff)
    assert ts == "2026-09-04T14:45:00Z"


def test_format_contract_a_auto_extracts_timestamp_from_image(tmp_path, sample_detection_result):
    """When timestamp_utc is omitted, adapter extracts it from valid GeoTIFF."""
    mock_tiff = tmp_path / "sentinel1_test.tif"
    mock_tiff.write_bytes(_make_mock_tiff_with_tag(0x0132, "2026:09:04 08:30:00"))

    contract_a = format_contract_a(
        detection_result=sample_detection_result,
        slick_id="SLICK-AUTO-TIME-001",
        timestamp_utc=None,
        image_path=mock_tiff,
    )

    assert contract_a["timestamp_utc"] == "2026-09-04T08:30:00Z"
    assert contract_a["slick_id"] == "SLICK-AUTO-TIME-001"


def test_extract_geotiff_timestamp_nonexistent_and_invalid_files(tmp_path):
    assert extract_geotiff_timestamp(None) is None
    assert extract_geotiff_timestamp(tmp_path / "non_existent.tif") is None

    empty_file = tmp_path / "empty.tif"
    empty_file.write_bytes(b"")
    assert extract_geotiff_timestamp(empty_file) is None

    not_tiff = tmp_path / "not_tiff.txt"
    not_tiff.write_text("just text")
    assert extract_geotiff_timestamp(not_tiff) is None
