import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import struct
from typing import Any, Dict, Optional, Union

try:
    import cv2
except ImportError:
    cv2 = None

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform
except ImportError:
    rasterio = None
    transform = None

try:
    import torch
    import torch.nn as nn
    _ModuleBase = nn.Module
except ImportError:
    torch = None
    nn = None
    _ModuleBase = object

try:
    from shapely.geometry import Polygon
except ImportError:
    Polygon = None



# ============================================================
# CONFIGURATION
# ============================================================

MODEL_PATH = os.getenv(
    "OIL_SPILL_MODEL_PATH",
    "aegisslick_v2_finetuned_best.pth"
)

PATCH_SIZE = 256
STRIDE = 256
THRESHOLD = 0.80
BATCH_SIZE = 4


# ============================================================
# U-NET MODEL
# IMPORTANT:
# This architecture matches the trained AegisSlick V2 model.
# ============================================================

class DoubleConv(_ModuleBase):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        self.block = nn.Sequential(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=3,
                padding=1
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),

            nn.Conv2d(
                out_channels,
                out_channels,
                kernel_size=3,
                padding=1
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.block(x)


class UNet(_ModuleBase):
    def __init__(self):
        super().__init__()

        # Encoder
        self.enc1 = DoubleConv(2, 64)
        self.pool1 = nn.MaxPool2d(2)

        self.enc2 = DoubleConv(64, 128)
        self.pool2 = nn.MaxPool2d(2)

        self.enc3 = DoubleConv(128, 256)
        self.pool3 = nn.MaxPool2d(2)

        self.enc4 = DoubleConv(256, 512)
        self.pool4 = nn.MaxPool2d(2)

        # Bottleneck
        self.bottleneck = DoubleConv(512, 1024)

        # Decoder
        self.up4 = nn.ConvTranspose2d(
            1024, 512, kernel_size=2, stride=2
        )
        self.dec4 = DoubleConv(1024, 512)

        self.up3 = nn.ConvTranspose2d(
            512, 256, kernel_size=2, stride=2
        )
        self.dec3 = DoubleConv(512, 256)

        self.up2 = nn.ConvTranspose2d(
            256, 128, kernel_size=2, stride=2
        )
        self.dec2 = DoubleConv(256, 128)

        self.up1 = nn.ConvTranspose2d(
            128, 64, kernel_size=2, stride=2
        )
        self.dec1 = DoubleConv(128, 64)

        # Output
        self.final = nn.Conv2d(64, 1, kernel_size=1)

    def forward(self, x):

        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        e3 = self.enc3(self.pool2(e2))
        e4 = self.enc4(self.pool3(e3))

        b = self.bottleneck(self.pool4(e4))

        d4 = self.up4(b)
        d4 = torch.cat([d4, e4], dim=1)
        d4 = self.dec4(d4)

        d3 = self.up3(d4)
        d3 = torch.cat([d3, e3], dim=1)
        d3 = self.dec3(d3)

        d2 = self.up2(d3)
        d2 = torch.cat([d2, e2], dim=1)
        d2 = self.dec2(d2)

        d1 = self.up1(d2)
        d1 = torch.cat([d1, e1], dim=1)
        d1 = self.dec1(d1)

        return self.final(d1)


# ============================================================
# MODEL LOADING
# ============================================================

_model = None
if torch is not None:
    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
else:
    _device = "cpu"


def load_model():

    global _model

    if _model is not None:
        return _model

    model_file = Path(MODEL_PATH)

    if not model_file.exists():
        raise FileNotFoundError(
            f"Oil spill model not found: {model_file}"
        )

    model = UNet()

    checkpoint = torch.load(
        model_file,
        map_location=_device
    )

    # Supports both a raw state_dict and a checkpoint dictionary.
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
    elif isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state_dict = checkpoint["state_dict"]
    else:
        state_dict = checkpoint

    model.load_state_dict(state_dict)

    model.to(_device)
    model.eval()

    _model = model

    return _model


# ============================================================
# IMAGE NORMALIZATION
# Matches the training/inference pipeline used for AegisSlick.
# ============================================================

def normalize_band(band):

    band = band.astype(np.float32)

    valid = np.isfinite(band)

    if not np.any(valid):
        return np.zeros_like(band, dtype=np.float32)

    values = band[valid]

    p2 = np.percentile(values, 2)
    p98 = np.percentile(values, 98)

    if p98 <= p2:
        return np.zeros_like(band, dtype=np.float32)

    normalized = (band - p2) / (p98 - p2)

    normalized = np.clip(
        normalized,
        0.0,
        1.0
    )

    normalized[~valid] = 0.0

    return normalized.astype(np.float32)


# ============================================================
# PATCH GENERATION
# ============================================================

def generate_patches(image):

    height, width = image.shape[1:]

    patches = []
    positions = []

    for y in range(0, height, STRIDE):

        for x in range(0, width, STRIDE):

            y2 = min(y + PATCH_SIZE, height)
            x2 = min(x + PATCH_SIZE, width)

            patch = image[
                :,
                y:y2,
                x:x2
            ]

            # Pad edge patches.
            padded = np.zeros(
                (2, PATCH_SIZE, PATCH_SIZE),
                dtype=np.float32
            )

            padded[
                :,
                :patch.shape[1],
                :patch.shape[2]
            ] = patch

            patches.append(padded)
            positions.append(
                (x, y, patch.shape[2], patch.shape[1])
            )

    return patches, positions


# ============================================================
# MODEL INFERENCE
# ============================================================

def predict_probability_map(image):

    model = load_model()

    patches, positions = generate_patches(image)

    height, width = image.shape[1:]

    probability_sum = np.zeros(
        (height, width),
        dtype=np.float32
    )

    probability_count = np.zeros(
        (height, width),
        dtype=np.float32
    )

    with torch.no_grad():

        for start in range(
            0,
            len(patches),
            BATCH_SIZE
        ):

            batch = np.stack(
                patches[start:start + BATCH_SIZE]
            )

            tensor = torch.from_numpy(
                batch
            ).to(_device)

            logits = model(tensor)

            probabilities = torch.sigmoid(
                logits
            )

            probabilities = (
                probabilities
                .cpu()
                .numpy()
                [:, 0]
            )

            for i, probability in enumerate(
                probabilities
            ):

                x, y, w, h = positions[
                    start + i
                ]

                probability_sum[
                    y:y+h,
                    x:x+w
                ] += probability[:h, :w]

                probability_count[
                    y:y+h,
                    x:x+w
                ] += 1.0

    probability_map = (
        probability_sum /
        np.maximum(probability_count, 1e-8)
    )

    return probability_map


# ============================================================
# MASK POST-PROCESSING
# ============================================================

def clean_mask(probability_map):

    mask = (
        probability_map >= THRESHOLD
    ).astype(np.uint8) * 255

    # Morphological closing removes small gaps.
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (15, 15)
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    return mask


# ============================================================
# MAIN SPILL COMPONENT
# ============================================================

def extract_main_spill(mask):

    binary = (
        mask > 0
    ).astype(np.uint8)

    num_labels, labels, stats, _ = (
        cv2.connectedComponentsWithStats(
            binary,
            connectivity=8
        )
    )

    if num_labels <= 1:
        return np.zeros_like(binary)

    # Ignore background label 0.
    largest_label = 1 + np.argmax(
        stats[1:, cv2.CC_STAT_AREA]
    )

    main_component = (
        labels == largest_label
    ).astype(np.uint8)

    return main_component


# ============================================================
# PIXEL → LONGITUDE/LATITUDE
# ============================================================

def pixel_to_lonlat(transform_obj, crs, x, y):

    px, py = rasterio.transform.xy(
        transform_obj,
        y,
        x,
        offset="center"
    )

    lon, lat = transform(
        crs,
        "EPSG:4326",
        [px],
        [py]
    )

    return float(lon[0]), float(lat[0])


# ============================================================
# MASK → GEOGRAPHIC POLYGON
# ============================================================

def mask_to_polygon(
    mask,
    transform_obj,
    crs
):

    contours, _ = cv2.findContours(
        mask.astype(np.uint8),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    contour = max(
        contours,
        key=cv2.contourArea
    )

    if len(contour) < 3:
        return None

    coordinates = []

    for point in contour[:, 0, :]:

        x = int(point[0])
        y = int(point[1])

        lon, lat = pixel_to_lonlat(
            transform_obj,
            crs,
            x,
            y
        )

        coordinates.append(
            (lon, lat)
        )

    polygon = Polygon(coordinates)

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        return None

    return polygon


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def detect_spill(image_path):

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Satellite image not found: {image_path}"
        )

    with rasterio.open(image_path) as src:

        if src.count < 2:
            raise ValueError(
                "Sentinel-1 image must contain "
                "at least VV and VH bands."
            )

        image = src.read(
            [1, 2]
        ).astype(np.float32)

        transform_obj = src.transform
        crs = src.crs

    # Normalize each SAR channel independently.
    image[0] = normalize_band(image[0])
    image[1] = normalize_band(image[1])

    # Model inference.
    probability_map = (
        predict_probability_map(image)
    )

    # Threshold.
    mask = clean_mask(
        probability_map
    )

    # Select dominant connected component.
    main_mask = extract_main_spill(
        mask
    )

    pixel_count = int(
        np.sum(main_mask)
    )

    if pixel_count == 0:

        return {
            "detected": False,
            "confidence": 0.0,
            "area_km2": 0.0,
            "geometry": None,
            "centroid": None,
            "pixel_count": 0,
            "source_image": image_path.name
        }

    # Convert mask to polygon.
    polygon = mask_to_polygon(
        main_mask,
        transform_obj,
        crs
    )

    if polygon is None:

        return {
            "detected": False,
            "confidence": 0.0,
            "area_km2": 0.0,
            "geometry": None,
            "centroid": None,
            "pixel_count": pixel_count,
            "source_image": image_path.name
        }

    # --------------------------------------------------------
    # Area calculation
    # --------------------------------------------------------
    from shapely.ops import transform as shapely_transform
    from pyproj import Transformer

    to_metric = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3857",
        always_xy=True
    ).transform

    metric_polygon = shapely_transform(
        to_metric,
        polygon
    )

    area_km2 = (
        metric_polygon.area /
        1_000_000.0
    )

    perimeter_km = (
        metric_polygon.length /
        1000.0
    )

    # --------------------------------------------------------
    # Centroid
    # --------------------------------------------------------
    centroid = polygon.centroid

    # --------------------------------------------------------
    # Model confidence
    # Mean predicted probability inside
    # the selected spill component.
    # --------------------------------------------------------
    confidence = float(
        probability_map[
            main_mask > 0
        ].mean()
    )

    # --------------------------------------------------------
    # GeoJSON geometry
    # --------------------------------------------------------
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [float(x), float(y)]
                for x, y in polygon.exterior.coords
            ]
        ]
    }

    return {
        "detected": True,

        "confidence": confidence,

        "area_km2": float(area_km2),

        "perimeter_km": float(perimeter_km),

        "geometry": geometry,

        "centroid": {
            "longitude": float(centroid.x),
            "latitude": float(centroid.y)
        },

        "pixel_count": pixel_count,

        "source_image": image_path.name
    }


# ============================================================
# CONTRACT A ADAPTER & METADATA EXTRACTION (PHASE 1A)
# ============================================================

def validate_slick_id(slick_id: str) -> str:
    """Validate that slick_id is a non-empty string."""
    if not isinstance(slick_id, str):
        raise TypeError(f"slick_id must be a string, got {type(slick_id).__name__}")
    cleaned = slick_id.strip()
    if not cleaned:
        raise ValueError("slick_id cannot be empty or whitespace.")
    return cleaned


def validate_timestamp_utc(timestamp_utc: str) -> str:
    """
    Validate that timestamp_utc is a valid ISO-8601 UTC timestamp string.
    Rejects missing, malformed, naive, or non-UTC timestamps.
    """
    if not isinstance(timestamp_utc, str):
        raise TypeError(f"timestamp_utc must be a string, got {type(timestamp_utc).__name__}")
    cleaned = timestamp_utc.strip()
    if not cleaned:
        raise ValueError("timestamp_utc cannot be empty or whitespace.")

    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except Exception as e:
        raise ValueError(
            f"'{timestamp_utc}' is not a valid ISO 8601 timestamp: {e}"
        ) from e

    if dt.tzinfo is None:
        raise ValueError(
            f"'{timestamp_utc}' lacks timezone information; must specify UTC (e.g. 'Z' or '+00:00')."
        )

    offset = dt.utcoffset()
    if offset is not None and offset.total_seconds() != 0:
        raise ValueError(
            f"'{timestamp_utc}' has non-zero UTC offset ({offset}); must be UTC ('Z' or '+00:00')."
        )

    return cleaned


def _parse_metadata_timestamp(val: str) -> Optional[str]:
    """
    Parse timestamp string from metadata tags into a standard ISO-8601 UTC string.
    Returns None if parsing fails.
    """
    if not val or not isinstance(val, str):
        return None
    s = val.strip().strip("\x00")
    if not s:
        return None

    # Format: TIFFTAG_DATETIME "YYYY:MM:DD HH:MM:SS"
    tiff_match = re.match(r"^(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$", s)
    if tiff_match:
        year, month, day, hour, minute, second = tiff_match.groups()
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}Z"

    # Try ISO-8601 directly
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # Try common formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue

    return None


def _read_tiff_tag_fallback(file_path: Path, target_tag: int) -> Optional[str]:
    """
    Pure Python fallback reader for ASCII tags from classic TIFF headers.
    Supports little-endian ('II') and big-endian ('MM') TIFF files.
    """
    try:
        if not file_path.exists() or not file_path.is_file():
            return None
        with open(file_path, "rb") as f:
            header = f.read(8)
            if len(header) < 8:
                return None
            order_bytes = header[:2]
            if order_bytes == b"II":
                endian = "<"
            elif order_bytes == b"MM":
                endian = ">"
            else:
                return None
            magic = struct.unpack(endian + "H", header[2:4])[0]
            if magic != 42:
                return None
            ifd_offset = struct.unpack(endian + "I", header[4:8])[0]
            f.seek(ifd_offset)
            num_entries_bytes = f.read(2)
            if len(num_entries_bytes) < 2:
                return None
            num_entries = struct.unpack(endian + "H", num_entries_bytes)[0]
            for _ in range(num_entries):
                entry = f.read(12)
                if len(entry) < 12:
                    break
                tag, dtype, count, val_or_offset = struct.unpack(endian + "HHI I", entry)
                if tag == target_tag and dtype == 2:  # ASCII
                    if count <= 4:
                        val_raw = entry[8:8 + count]
                        return val_raw.decode("latin1", errors="ignore").rstrip("\x00")
                    else:
                        cur_pos = f.tell()
                        f.seek(val_or_offset)
                        val_raw = f.read(count)
                        f.seek(cur_pos)
                        return val_raw.decode("latin1", errors="ignore").rstrip("\x00")
    except Exception:
        return None
    return None


def extract_geotiff_timestamp(image_path: Optional[Union[str, Path]]) -> Optional[str]:
    """
    Extract acquisition timestamp from GeoTIFF metadata if reliable tags exist.

    Checks:
    - ACQUISITION_START_TIME
    - TIFFTAG_DATETIME

    Returns ISO-8601 UTC string (e.g. '2026-09-04T12:00:00Z') or None if not found/unreliable.
    Does NOT invent timestamps or use current system time.
    """
    if image_path is None:
        return None

    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return None

    # 1. Try rasterio if available
    if rasterio is not None:
        try:
            with rasterio.open(path) as src:
                tags = src.tags() or {}
                for key in (
                    "ACQUISITION_START_TIME",
                    "acquisition_start_time",
                    "TIFFTAG_DATETIME",
                    "tifftag_datetime",
                    "DATETIME",
                ):
                    val = tags.get(key)
                    if val:
                        parsed = _parse_metadata_timestamp(val)
                        if parsed:
                            return parsed

                if hasattr(src, "tag_namespaces"):
                    for ns in src.tag_namespaces():
                        ns_tags = src.tags(ns=ns) or {}
                        for key in (
                            "ACQUISITION_START_TIME",
                            "acquisition_start_time",
                            "TIFFTAG_DATETIME",
                            "tifftag_datetime",
                        ):
                            val = ns_tags.get(key)
                            if val:
                                parsed = _parse_metadata_timestamp(val)
                                if parsed:
                                    return parsed
        except Exception:
            pass

    # 2. Try pure Python TIFF parser fallback
    # Check standard TIFFTAG_DATETIME (tag 306 / 0x0132)
    val_dt = _read_tiff_tag_fallback(path, 0x0132)
    if val_dt:
        parsed = _parse_metadata_timestamp(val_dt)
        if parsed:
            return parsed

    # Check GDAL metadata XML (tag 42112 / 0xA480)
    gdal_meta = _read_tiff_tag_fallback(path, 0xA480)
    if gdal_meta:
        m = re.search(r'name=["\'](?:ACQUISITION_START_TIME|acquisition_start_time)["\']>([^<]+)<', gdal_meta)
        if m:
            parsed = _parse_metadata_timestamp(m.group(1))
            if parsed:
                return parsed
        m2 = re.search(r'name=["\'](?:TIFFTAG_DATETIME|tifftag_datetime)["\']>([^<]+)<', gdal_meta)
        if m2:
            parsed = _parse_metadata_timestamp(m2.group(1))
            if parsed:
                return parsed

    return None


def format_contract_a(
    detection_result: Dict[str, Any],
    slick_id: str,
    timestamp_utc: Optional[str] = None,
    image_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Format a Member 1 detection dictionary into the official Contract A payload
    required by Member 2 (module2_drift).

    Parameters
    ----------
    detection_result : dict
        Output dictionary from detect_spill() or a detection pipeline.
    slick_id : str
        Unique slick identifier. Must be non-empty string.
    timestamp_utc : str, optional
        ISO-8601 UTC timestamp of detection (e.g. '2026-09-04T12:00:00Z').
        If None, attempts to extract reliable timestamp from image_path or
        detection_result['source_image'].
    image_path : str or Path, optional
        Path to source GeoTIFF image to extract timestamp from if timestamp_utc is not provided.

    Returns
    -------
    dict
        Official Contract A payload containing only:
        - slick_id: str
        - timestamp_utc: str
        - geometry: GeoJSON Polygon
        - area_km2: Optional[float]
        - confidence: Optional[float]

    Raises
    ------
    ValueError
        If slick_id is empty, timestamp_utc is missing or invalid, or detection_result
        lacks a valid Polygon geometry.
    TypeError
        If detection_result is not a dictionary or slick_id is not a string.
    """
    if not isinstance(detection_result, dict):
        raise TypeError(f"detection_result must be a dict, got {type(detection_result).__name__}")

    clean_slick_id = validate_slick_id(slick_id)

    resolved_ts = timestamp_utc
    if not resolved_ts:
        target_img = image_path
        if not target_img:
            target_img = detection_result.get("source_image")
        if target_img:
            resolved_ts = extract_geotiff_timestamp(target_img)

    if not resolved_ts:
        raise ValueError(
            "timestamp_utc is required for Contract A and could not be determined "
            "from image metadata. Caller must provide an explicit timestamp_utc."
        )

    clean_ts = validate_timestamp_utc(resolved_ts)

    if detection_result.get("detected") is False:
        raise ValueError(
            "Cannot produce Contract A: detection_result indicates no oil spill was detected."
        )

    raw_geometry = detection_result.get("geometry")
    if not raw_geometry or not isinstance(raw_geometry, dict):
        raise ValueError(
            "detection_result must contain a valid GeoJSON 'geometry' dictionary."
        )

    geom_type = raw_geometry.get("type")
    if geom_type != "Polygon":
        raise ValueError(
            f"Contract A requires a GeoJSON Polygon geometry; got '{geom_type}'."
        )

    coords = raw_geometry.get("coordinates")
    if not coords or not isinstance(coords, list) or len(coords) < 1:
        raise ValueError("Polygon geometry must contain at least one linear ring.")

    outer_ring = coords[0]
    if not isinstance(outer_ring, list) or len(outer_ring) < 4:
        raise ValueError(
            f"Polygon outer ring must contain at least 4 coordinate pairs; got {len(outer_ring) if isinstance(outer_ring, list) else 0}."
        )
    if outer_ring[0] != outer_ring[-1]:
        raise ValueError("Polygon outer ring must be closed (first coordinate equals last coordinate).")

    contract_a: Dict[str, Any] = {
        "slick_id": clean_slick_id,
        "timestamp_utc": clean_ts,
        "geometry": copy.deepcopy(raw_geometry),
    }

    if "area_km2" in detection_result and detection_result["area_km2"] is not None:
        area_val = float(detection_result["area_km2"])
        if area_val < 0.0:
            raise ValueError(f"area_km2 cannot be negative; got {area_val}.")
        contract_a["area_km2"] = area_val

    if "confidence" in detection_result and detection_result["confidence"] is not None:
        conf_val = float(detection_result["confidence"])
        if not (0.0 <= conf_val <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0; got {conf_val}.")
        contract_a["confidence"] = conf_val

    return contract_a

