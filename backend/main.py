import os
from shapely.geometry import shape
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .oil_spill_detector import detect_spill

app = FastAPI(title="MARIS API")

# Allow your React/Vite frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Contract A — Oil Spill Detection
# --------------------------------------------------

@app.get("/api/detect")
def detect_spill_endpoint():

    geometry = json.load(
        open("backend/aegisslick_spill_00204.geojson", "r", encoding="utf-8")
    )["features"][0]["geometry"]

    return {
        "slick_id": "aegisslick_00204",
        "timestamp_utc": "2026-09-04T02:13:00Z",
        "detected": True,
        "geometry": geometry,
        "perimeter_km": 7.9779,
        "area_km2": 2.4954863597639005,
        "length_km": 17.504977691821573,
        "confidence": 0.9602252244949341,
        "source_image": "00204.tif"
    }

# --------------------------------------------------
# Contract B — Drift / Hindcast / Forecast
# --------------------------------------------------

@app.get("/api/drift")
def drift_forecast():
    return {
        "slick_id": "slick_001",

        "estimated_origin": {
            "point": [30.30075, 33.16940],
            "time_utc": "2026-09-03T20:00:00Z"
        },

        "backtrack_track": {
            "type": "LineString",
            "coordinates": [
    [30.30075, 33.16940],
    [30.29, 33.17],
    [30.28, 33.18],
    [30.27, 33.19]
]
        },

        "forecast_polygons": [
            {
                "hours_ahead": 6,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        
    [30.28, 33.17],
    [30.34, 33.17],
    [30.35, 33.22],
    [30.29, 33.23],
    [30.28, 33.17]
                        
                    ]]
                }
            },
            {
                "hours_ahead": 24,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        
    [30.30, 33.20],
    [30.42, 33.20],
    [30.44, 33.30],
    [30.32, 33.32],
    [30.30, 33.20]

                    ]]
                }
            }
        ]
    }


# --------------------------------------------------
# Contract C — Vessel Attribution
# --------------------------------------------------

@app.get("/api/attribute")
def vessel_attribution():
    return {
        "slick_id": "slick_001",
        "suspects": [
            {
                "mmsi": "412345678",
                "vessel_name": "Tanker A",
                "score": 0.87,
                "proximity_km": 2.1,
                "anomaly_flags": [
                    "loitering",
                    "ais_gap_10min"
                ],
                "evidence_text": (
                    "Loitered 2.1 km from estimated origin; "
                    "AIS gap of 10 min matching backtrack window."
                )
            },
            {
                "mmsi": "412345679",
                "vessel_name": "Cargo B",
                "score": 0.64,
                "proximity_km": 5.8,
                "anomaly_flags": [
                    "speed_change"
                ],
                "evidence_text": (
                    "Vessel passed near the backtrack corridor "
                    "with an unusual speed change."
                )
            },
            {
                "mmsi": "412345680",
                "vessel_name": "Tanker C",
                "score": 0.41,
                "proximity_km": 9.4,
                "anomaly_flags": [],
                "evidence_text": (
                    "Vessel was within the investigation window "
                    "but showed limited correlation with the spill."
                )
            }
        ]
    }


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "online",
        "system": "MARIS",
        "message": "MARIS FastAPI backend is running"
    }
