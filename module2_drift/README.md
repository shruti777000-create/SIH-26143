# Module 2: Geospatial & Drift Modeling Engine

Autonomous Lagrangian oil spill trajectory modeling and origin attribution system built on **OpenDrift (OpenOil)**, **xarray**, and **Shapely**.

This module ingests metocean NetCDF data (currents and winds), executes reverse backtracking to determine spill origins and discharge timestamps for vessel attribution, and models forward trajectory dispersion envelopes at +6h and +24h horizons.

---

## 1. Directory Structure

```text
module2_drift/
├── README.md               # Module overview, API contracts, and usage guide
├── requirements.txt        # Python package dependencies
├── data_loader.py          # NetCDF inspection, variable synonym translation, and reader initialization
├── backtrack.py           # Reverse Lagrangian trajectory backtracking (-12h) to origin point
├── forecast.py            # Forward dispersion and concave hull polygon envelope generator (+6h, +24h)
├── drift_model.py         # Unified pipeline entrypoint producing Contract B JSON output
├── validate_schema.py     # Strict schema and GeoJSON topology validator for Contract B
├── plots/                 # Sanity-check visualization scripts and test PNGs (gitignored)
│   └── plot_drift.py
└── tests/                 # Automated test suite (Arabian Sea, Bay of Bengal, Schema)
    ├── test_arabian_sea.py
    ├── test_bay_of_bengal.py
    └── test_schema.py
```

---

## 2. Inputs & Outputs (Data Contracts)

### Input: Contract A (Slick Detection GeoJSON / Dict)
Received from the upstream SAR / Optical detection pipeline:
```json
{
  "slick_id": "SLICK-AS-MUMBAI-20260904-001",
  "timestamp_utc": "2026-09-04T12:00:00Z",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[72.82, 18.95], [72.85, 18.96], [72.84, 18.92], [72.82, 18.95]]]
  }
}
```

### Output: Contract B (Unified Drift Output)
Standardized output used by downstream AIS vessel attribution and emergency response:
```json
{
  "slick_id": "SLICK-AS-MUMBAI-20260904-001",
  "region": "Arabian Sea (Maharashtra / Mumbai)",
  "estimated_origin": {
    "point": [71.86696, 19.2849],
    "time_utc": "2026-09-04T00:00:00Z"
  },
  "backtrack_track": {
    "type": "LineString",
    "coordinates": [
      [71.86696, 19.2849],
      [72.1054, 19.1234],
      [72.82, 18.95]
    ]
  },
  "forecast_polygons": [
    {
      "hours_ahead": 6,
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[72.85, 18.92], ... [72.85, 18.92]]]
      }
    },
    {
      "hours_ahead": 24,
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[72.95, 18.88], ... [72.95, 18.88]]]
      }
    }
  ]
}
```
A complete, validated sample is stored in the repository root at:
`contracts/sample_drift_output.json`.

---

## 3. Installation

Ensure you have a Python environment (Python 3.10 - 3.12 recommended; or 3.13):

```bash
pip install -r module2_drift/requirements.txt
```

---

## 4. How to Run

### Python API Usage

```python
from module2_drift import forecast_drift

# Member 1 Detection GeoJSON Polygon output
slick_polygon = {
    "type": "Polygon",
    "coordinates": [[[72.74775, 18.84775], [72.75225, 18.84775], [72.75225, 18.85225], [72.74775, 18.85225], [72.74775, 18.84775]]]
}
detection_time = "2026-09-04T12:00:00Z"

# Strategy A: Distributed seeding (Default - most realistic, spreads particles across polygon area)
result_dist = forecast_drift(
    slick_polygon=slick_polygon,
    timestamp=detection_time,
    seed_mode="distributed",     # "distributed" | "centroid"
    current_nc_path="arabian_sea_currents.nc",
    wind_nc_path="arabian_sea_winds.nc",
    backtrack_hours=12,
    forecast_hours=[6, 24],
    num_particles=100
)

# Strategy B: Centroid seeding (Fast, simple - all particles originate at single polygon centroid)
result_cent = forecast_drift(
    slick_polygon=slick_polygon,
    timestamp=detection_time,
    seed_mode="centroid",
    current_nc_path="arabian_sea_currents.nc",
    wind_nc_path="arabian_sea_winds.nc",
    backtrack_hours=12,
    forecast_hours=[6, 24],
    num_particles=100
)

print("Origin:", result_dist["estimated_origin"])
```

### Dynamic Metocean NetCDF Loading (`load_environment_data`)

Instead of hardcoding a single NetCDF file, `load_environment_data()` dynamically scans local directories, catalogs available ocean current (`uo`, `vo`) and wind (`u10`, `v10`) datasets, and auto-selects the files matching the requested date and bounding box.

```python
from module2_drift import load_environment_data, DEFAULT_BBOX, MetoceanDateOutOfRangeError

# 1. Load forcing data for a given date (defaults to Arabian Sea bbox: [71.0, 18.0, 73.5, 20.0])
try:
    env = load_environment_data(
        date="2026-09-04T12:00:00Z",
        bbox=DEFAULT_BBOX  # [min_lon, min_lat, max_lon, max_lat]
    )
    current_reader = env["current_reader"]
    wind_reader = env["wind_reader"]
    print("Loaded currents from:", env["current_file"])
    print("Loaded winds from:", env["wind_file"])

except MetoceanDateOutOfRangeError as e:
    # Clear error showing which date ranges are actually available locally
    print(f"Error: {e}")
    for r in e.available_ranges:
        print(f"  Available: {r['filename']} ({r['var_type']}) from {r['start_str']} to {r['end_str']}")
```

### Validate Output Schema

```bash
python -m module2_drift.validate_schema contracts/sample_drift_output.json
```

### Run Automated Tests

```bash
python -m unittest discover -s module2_drift/tests
```

### Generate Sanity-Check Plots

```bash
python module2_drift/plots/plot_drift.py
```
*(Generated PNGs are saved to `module2_drift/plots/` and are excluded by `.gitignore`)*

---

## 5. REST API (`POST /api/drift`)

The drift engine is also served as a FastAPI REST service, ready for integration with Member 4's dashboard.

### Start the API Server

```bash
# From the project root:
python api.py
# or directly:
uvicorn module2_drift.api:app --reload --port 8000
```

The server starts at **http://localhost:8000**. Interactive docs (Swagger UI) are at **http://localhost:8000/docs**.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — confirms service is up |
| `POST` | `/api/drift` | Run full drift pipeline (Contract A → Contract B) |

### `POST /api/drift` — Request Body (Contract A)

```json
{
  "slick_id": "SLICK-AS-MUMBAI-20260904-001",
  "timestamp_utc": "2026-09-04T12:00:00Z",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [72.748, 18.848],
      [72.752, 18.848],
      [72.752, 18.852],
      [72.748, 18.852],
      [72.748, 18.848]
    ]]
  },
  "area_km2": 0.25,
  "confidence": 0.94,
  "seed_mode": "distributed",
  "backtrack_hours": 12,
  "forecast_hours": [6, 24],
  "num_particles": 100
}
```

### Test with curl

```bash
curl -X POST http://localhost:8000/api/drift \
  -H "Content-Type: application/json" \
  -d '{
    "slick_id": "SLICK-AS-MUMBAI-20260904-001",
    "timestamp_utc": "2026-09-04T12:00:00Z",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[72.748,18.848],[72.752,18.848],[72.752,18.852],[72.748,18.852],[72.748,18.848]]]
    },
    "area_km2": 0.25,
    "confidence": 0.94,
    "seed_mode": "distributed",
    "backtrack_hours": 12,
    "forecast_hours": [6, 24],
    "num_particles": 100
  }'
```

### HTTP Error Codes

| Code | Meaning |
|------|---------|
| `200` | Success — Contract B payload returned |
| `400` | Invalid input: malformed polygon, out-of-range date, land/bbox violation |
| `502` | Pipeline failure: metocean reader error or OpenDrift simulation crash near coastline |

All errors return a structured JSON body:
```json
{
  "error": true,
  "error_type": "TEMPORAL_OUT_OF_BOUNDS",
  "reason": "Requested date '2020-01-01' falls outside available local NetCDF data. Available local dataset ranges: ['arabian_sea_currents.nc' ...]",
  "details": { "requested_date": "...", "available_ranges": [...] }
}
```
