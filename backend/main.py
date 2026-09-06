from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
def detect_spill():
    return {
        "slick_id": "slick_001",
        "timestamp_utc": "2026-09-04T02:13:00Z",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [80.20, 13.05],
                [80.25, 13.05],
                [80.30, 13.10],
                [80.25, 13.15],
                [80.20, 13.10],
                [80.20, 13.05]
            ]]
        },
        "area_km2": 12.4,
        "length_km": 21.3,
        "confidence": 0.91,
        "source_image": "sentinel-1-demo.tif"
    }


# --------------------------------------------------
# Contract B — Drift / Hindcast / Forecast
# --------------------------------------------------

@app.get("/api/drift")
def drift_forecast():
    return {
        "slick_id": "slick_001",

        "estimated_origin": {
            "point": [80.27, 13.08],
            "time_utc": "2026-09-03T20:00:00Z"
        },

        "backtrack_track": {
            "type": "LineString",
            "coordinates": [
                [80.27, 13.08],
                [80.25, 13.10],
                [80.23, 13.12],
                [80.21, 13.14]
            ]
        },

        "forecast_polygons": [
            {
                "hours_ahead": 6,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [80.28, 13.10],
                        [80.34, 13.10],
                        [80.35, 13.15],
                        [80.29, 13.16],
                        [80.28, 13.10]
                    ]]
                }
            },
            {
                "hours_ahead": 24,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [80.30, 13.12],
                        [80.42, 13.12],
                        [80.44, 13.22],
                        [80.32, 13.24],
                        [80.30, 13.12]
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