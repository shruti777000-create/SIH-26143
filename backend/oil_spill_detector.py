import os
from pathlib import Path

import cv2
import numpy as np
import rasterio
import torch
import torch.nn as nn
from shapely.geometry import Polygon
from rasterio.warp import transform


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

class DoubleConv(nn.Module):
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


class UNet(nn.Module):
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
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


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

        "length_km": float(perimeter_km),

        "geometry": geometry,

        "centroid": {
            "longitude": float(centroid.x),
            "latitude": float(centroid.y)
        },

        "pixel_count": pixel_count,

        "source_image": image_path.name
    }
