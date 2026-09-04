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

slick_input = {
    "slick_id": "SLICK-001",
    "timestamp_utc": "2026-09-04T12:00:00Z",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[72.0, 19.0], [72.02, 19.02], [72.01, 18.98], [72.0, 19.0]]]
    }
}

# Run drift simulation using local NetCDF forcing files
result = forecast_drift(
    slick_json=slick_input,
    current_nc_path="arabian_sea_currents.nc",
    wind_nc_path="arabian_sea_winds.nc",
    backtrack_hours=12,
    forecast_hours=[6, 24],
    num_particles=100
)

print(result["estimated_origin"])
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
