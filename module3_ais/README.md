# Module 3: AIS & Intelligence Engine (Vessel Attribution)

**SIH Problem Statement 26143**  
Autonomous marine vessel attribution engine correlating reverse Lagrangian oil spill backtrack origins (Contract B) with terrestrial/satellite AIS feeds to identify, rank, and generate legal evidence against discharging ships.

---

## 1. Directory Structure

```text
module3_ais/
├── README.md                 # Architecture, specifications, and execution instructions
├── requirements.txt          # Python package requirements (pandas, numpy, scikit-learn, etc.)
├── __init__.py               # Package public API exports
├── config.py                 # Configuration parameters, physical limits, and scoring weights
├── schemas.py                # Pydantic schemas for Contract B and Contract C
├── preprocessor.py           # AIS loading, UTC timestamp normalization, data cleaning, and filtering
├── trajectory.py             # Per-vessel trajectory reconstruction and GeoJSON generation
├── features.py               # Kinematic feature engineering (accel, rate of turn, speed deviations)
├── anomaly_model.py          # Isolation Forest behavioral anomaly detection (Phase 2)
├── attribution_engine.py     # Multi-criteria suspect ranking engine (Phase 2)
├── evidence_generator.py     # Legal evidence packaging and narrative reporting (Phase 2)
├── validate_schema.py        # Strict Contract C schema and topology validator
├── api.py                    # FastAPI application serving /api/attribute (Phase 2)
├── data/                     # Benchmark AIS feeds
│   └── synthetic_ais.csv     # Multi-vessel synthetic dataset with dirty records & edge cases
└── tests/                    # Unit and integration test suite
    ├── __init__.py
    └── test_preprocessor.py  # Unit tests for preprocessing, cleaning, Haversine, and filtering
```

---

## 2. Phase 1 Implementation Highlights

### A. Strict Coordinate Convention
- **Raw AIS & DataFrames**: Ingests and stores coordinates in named columns: `latitude` and `longitude`.
- **Contract B & Contract C / GeoJSON**: Coordinates are strictly formatted as `[longitude, latitude]`.

### B. Haversine Great-Circle Distance
Distances are computed using the spherical Haversine formula (mean Earth radius $R = 6371.0088\text{ km}$), avoiding linear Euclidean approximations:

$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)$$
$$c = 2 \cdot \operatorname{atan2}\left(\sqrt{a}, \sqrt{1 - a}\right)$$
$$d = R \cdot c$$

Both scalar `haversine_distance_km()` and high-throughput NumPy `haversine_vectorized_km()` implementations are provided.

### C. Data Validation & Cleaning
The preprocessor enforces:
1. **Timestamp Normalization**: All incoming timestamps are parsed and converted to timezone-aware UTC datetime. Missing/unparseable timestamps are dropped.
2. **MMSI Validation**: MMSI must be a valid positive integer. Non-positive or NaN values are dropped.
3. **Coordinate Bounds**: Latitude constrained to $[-90.0, 90.0]$, Longitude constrained to $[-180.0, 180.0]$.
4. **Kinematic Bounds**: Speed Over Ground (SOG) constrained to $[0.0, 102.2\text{ knots}]$. Negative speeds are dropped. Course Over Ground (COG) constrained to $[0.0, 360.0^\circ]$.
5. **Deduplication**: Identical `(mmsi, timestamp)` pings are deduplicated, preserving the first occurrence.

### D. Spatio-temporal Corridor Filtering
Using Contract B's `estimated_origin`:
- **Spatial Radius**: Default $\le 50\text{ km}$ from `estimated_origin.point` ($[lon, lat]$).
- **Temporal Window**: Default $\pm 12\text{ hours}$ from `estimated_origin.time_utc`.

---

## 3. Phase 2 Implementation Highlights

### A. Per-Vessel Trajectory Reconstruction (`trajectory.py`)
- Groups cleaned AIS records by MMSI and sorts all points chronologically.
- Preserves internal dataframe coordinates as `latitude` and `longitude`.
- Gracefully handles single-point trajectories (`Point` geometry) and multi-point tracks (`LineString` geometry).
- Exports standard GeoJSON features and `FeatureCollection` with strict `[longitude, latitude]` coordinate ordering.

### B. Vessel-Level Feature Engineering (`features.py`)
Computes 14 core attribution features per vessel:
1. `mmsi`: Vessel identifier.
2. `min_distance_to_origin_km`: Closest Point of Approach (CPA) to `estimated_origin.point` using spherical Haversine distance.
3. `avg_speed_knots`: Mean Speed Over Ground (SOG).
4. `max_speed_knots`: Maximum SOG observed.
5. `speed_std`: Standard deviation of SOG (measures speed instability).
6. `total_track_distance_km`: Cumulative great-circle distance along consecutive track waypoints.
7. `ais_observation_count`: Total AIS pings for the vessel in the window.
8. `stop_count`: Near-zero speed count ($SOG \le 0.5\text{ kn}$, loitering indicator).
9. `avg_heading_change_deg`: Average Course Over Ground change with $360^\circ$ wraparound.
10. `max_heading_change_deg`: Maximum acute heading deviation with $360^\circ$ wraparound.
11. `closest_point_time_utc`: ISO-8601 UTC timestamp when vessel was at CPA.
12. `time_difference_minutes`: Signed temporal delta $(T_{\text{CPA}} - T_{\text{origin}})$ in minutes.
13. `cross_track_distance_km`: Minimum spherical perpendicular distance from vessel to Contract B backtrack corridor line segments.
14. `trajectory_alignment_score`: Directional cosine alignment $\in [0.0, 1.0]$ between vessel movement vector / COG and net spill drift vector.

### C. Heading Wraparound Formulation
Computes acute compass angular changes across the North boundary ($359^\circ \to 1^\circ = 2^\circ$):
$$\Delta h = |(h_2 - h_1 + 180) \pmod{360} - 180|$$

### D. Backtrack Waypoint Time Interpolation
Linearly interpolates timestamps for waypoints along the Contract B backtrack corridor without inventing data:
$$T_k = T_{\text{origin}} + \frac{k}{N - 1}(T_{\text{det}} - T_{\text{origin}})$$

---

## 4. How to Run Tests

From the repository root:

```bash
python -m unittest discover -s module3_ais/tests
```
