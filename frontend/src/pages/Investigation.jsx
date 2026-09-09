import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MapContainer,
  TileLayer,
  Polygon,
  Polyline,
  CircleMarker,
  Popup,
  ZoomControl,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "../investigation.css";

// --------------------------------------------------
// Convert GeoJSON [longitude, latitude]
// to Leaflet [latitude, longitude]
// --------------------------------------------------
function geoJsonToLeaflet(coordinates) {
  return coordinates.map(([lng, lat]) => [lat, lng]);
}

function polygonFromGeoJSON(geometry) {
  if (!geometry || geometry.type !== "Polygon") return [];

  return geometry.coordinates.map((ring) =>
    geoJsonToLeaflet(ring)
  );
}

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function Investigation() {
  const navigate = useNavigate();

  // --------------------------------------------------
  // API DATA
  // --------------------------------------------------

  const [detectData, setDetectData] = useState(null);
  const [driftData, setDriftData] = useState(null);
  const [attributeData, setAttributeData] = useState(null);

  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  // --------------------------------------------------
  // UI STATE
  // --------------------------------------------------

  const [layers, setLayers] = useState({
    spill: true,
    drift: true,
    vessels: true,
    forecast: true,
    zones: true,
  });

  const [selectedVessel, setSelectedVessel] = useState("");
  const [time, setTime] = useState(62);

  // --------------------------------------------------
  // FETCH PIPELINE DATA (Single Request)
  // --------------------------------------------------

  useEffect(() => {
    async function loadInvestigationData() {
      try {
        setLoading(true);
        setApiError("");

        const response = await fetch("/api/pipeline?demo=true", {
          method: "POST",
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || `Pipeline request failed (${response.status})`);
        }

        const data = await response.json();

        setDetectData(data.contract_a);
        setDriftData(data.contract_b);
        setAttributeData(data.contract_c);

        // Automatically select the highest-ranked suspect
        const suspectList =
          data.contract_c?.ranked_suspects ??
          data.contract_c?.suspects ??
          [];

        if (suspectList.length > 0) {
          const topSuspect = suspectList[0];
          const topName =
            topSuspect.vessel_name ??
            topSuspect.vessel_metadata?.vessel_name ??
            `MMSI ${topSuspect.mmsi ?? 1}`;

          setSelectedVessel(topName);
        }
      } catch (error) {
        console.error("MARIS Pipeline API Error:", error);

        setApiError(
          error.message || "Unable to connect to MARIS FastAPI backend pipeline."
        );
      } finally {
        setLoading(false);
      }
    }

    loadInvestigationData();
  }, []);

  // --------------------------------------------------
  // LAYER TOGGLE
  // --------------------------------------------------

  const toggleLayer = (layer) => {
    setLayers((previous) => ({
      ...previous,
      [layer]: !previous[layer],
    }));
  };

  // --------------------------------------------------
  // DERIVED API DATA
  // --------------------------------------------------

  const spillPolygon =
    detectData?.geometry?.coordinates
      ? polygonFromGeoJSON(detectData.geometry)
      : [];

  const driftTrack =
    driftData?.backtrack_track?.coordinates
      ? geoJsonToLeaflet(driftData.backtrack_track.coordinates)
      : [];

  const forecastPolygons =
    driftData?.forecast_polygons || [];

  const suspects =
    attributeData?.ranked_suspects ??
    attributeData?.suspects ??
    [];

  const selectedSuspect =
    suspects.find((suspect) => {
      const name =
        suspect.vessel_metadata?.vessel_name ??
        suspect.vessel_name ??
        suspect.name ??
        `MMSI ${suspect.mmsi}`;
      return name === selectedVessel;
    }) || suspects[0];

  // --------------------------------------------------
  // LOADING STATE
  // --------------------------------------------------

  if (loading) {
    return (
      <div className="investigation-page">
        <aside className="investigation-sidebar">
          <div className="side-brand">
            <div className="side-brand-mark">◇</div>

            <div>
              <div className="side-brand-name">MARIS</div>
              <div className="side-brand-subtitle">
                Maritime Oil Spill Intelligence
              </div>
            </div>
          </div>
        </aside>

        <main className="investigation-main">
          <div className="investigation-header">
            <div>
              <div className="page-kicker">
                MARIS / INCIDENTS / MAP
              </div>
              <h1>Live Investigation</h1>
            </div>
          </div>

          <div
            style={{
              padding: "40px",
              color: "#23c0e5",
            }}
          >
            Connecting to MARIS intelligence services...
          </div>
        </main>
      </div>
    );
  }

  // --------------------------------------------------
  // MAIN UI
  // --------------------------------------------------

  return (
    <div className="investigation-page">

      {/* SIDEBAR */}
      <aside className="investigation-sidebar">

        <div className="side-brand">
          <div className="side-brand-mark">◇</div>

          <div>
            <div className="side-brand-name">MARIS</div>
            <div className="side-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>
          </div>
        </div>

        <div className="sidebar-menu">

          <SidebarItem
            icon="⌂"
            label="Dashboard"
            onClick={() => navigate("/")}
          />

          <SidebarItem
            icon="⌖"
            label="Map"
            active
            onClick={() => navigate("/investigation")}
          />

          <SidebarItem
            icon="≋"
            label="Pipeline"
            onClick={() => navigate("/pipeline")}
          />

          <SidebarItem
            icon="♙"
            label="Vessels"
            onClick={() => navigate("/vessels")}
          />

          <SidebarItem
            icon="◴"
            label="Forecast"
            onClick={() => navigate("/forecast")}
          />

          <SidebarItem
            icon="▤"
            label="Reports"
            onClick={() => navigate("/reports")}
          />

        </div>

        <div className="sidebar-bottom">
          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />
        </div>

      </aside>

      {/* MAIN */}
      <main className="investigation-main">

        <div className="investigation-header">

          <div>
            <div className="page-kicker">
              MARIS / INCIDENT / MAP
            </div>

            <h1>Live Investigation</h1>
          </div>

          <div className="live-status">
            <span className="live-dot" />
            LIVE
          </div>

        </div>

        {/* API ERROR */}
        {apiError && (
          <div
            style={{
              marginBottom: "10px",
              padding: "10px 14px",
              border: "1px solid #7b3030",
              background: "#211416",
              color: "#ff7777",
              fontSize: "12px",
            }}
          >
            {apiError}
          </div>
        )}

        {/* MAP */}
        <section className="map-wrapper">

          <MapContainer
            key={
              driftData?.estimated_origin?.point
                ? `${driftData.estimated_origin.point[1]}-${driftData.estimated_origin.point[0]}`
                : "investigation-map"
            }
            center={
              driftData?.estimated_origin?.point
                ? [driftData.estimated_origin.point[1], driftData.estimated_origin.point[0]]
                : [19.28, 71.86]
            }
            zoom={9}
            zoomControl={false}
            className="maris-map"
          >

            <TileLayer
              attribution="Tiles &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
            />

            <ZoomControl position="bottomleft" />

            {/* ----------------------------------------
                OIL SPILL FROM /api/detect
            ----------------------------------------- */}

            {layers.spill && spillPolygon.length > 0 && (
              <Polygon
                positions={spillPolygon}
                pathOptions={{
                  color: "#19b9df",
                  weight: 2,
                  fillColor: "#087ca0",
                  fillOpacity: 0.42,
                }}
              >
                <Popup>
                  <strong>Oil Spill Detected</strong>
                  <br />

                  Area:{" "}
                  {detectData?.area_km2 != null ? `${detectData.area_km2} km²` : "--"}

                  <br />

                  Confidence:{" "}
                  {detectData?.confidence != null
                    ? `${Math.round(
                        detectData.confidence * 100
                      )}%`
                    : "--"}

                  <br />

                  Slick ID:{" "}
                  {detectData?.slick_id ?? "--"}

                  {detectData?.demo_mode && (
                    <>
                      <br />
                      <small style={{ color: "#23c0e5" }}>Demo Contract A Fixture</small>
                    </>
                  )}
                </Popup>
              </Polygon>
            )}

            {/* ----------------------------------------
                BACKTRACK FROM /api/drift
            ----------------------------------------- */}

            {layers.drift && driftTrack.length > 0 && (
              <Polyline
                positions={driftTrack}
                pathOptions={{
                  color: "#f15b5b",
                  weight: 3,
                  dashArray: "8 8",
                }}
              >
                <Popup>
                  <strong>Estimated Spill Backtrack</strong>
                  <br />
                  Origin:{" "}
                  {driftData?.estimated_origin?.point
                    ? `${driftData.estimated_origin.point[1].toFixed(
                        2
                      )}°N, ${driftData.estimated_origin.point[0].toFixed(
                        2
                      )}°E`
                    : "--"}
                  <br />
                  Time:{" "}
                  {driftData?.estimated_origin?.time_utc ?? "--"}
                </Popup>
              </Polyline>
            )}

            {/* ----------------------------------------
                FORECAST POLYGONS FROM /api/drift
            ----------------------------------------- */}

            {layers.forecast &&
              forecastPolygons.map((forecast) => {
                const positions = polygonFromGeoJSON(
                  forecast.geometry
                );

                return (
                  <Polygon
                    key={forecast.hours_ahead}
                    positions={positions}
                    pathOptions={{
                      color:
                        forecast.hours_ahead === 6
                          ? "#4ed6e8"
                          : "#8a9cff",
                      weight: 1.5,
                      fillOpacity: 0.12,
                      dashArray: "5 5",
                    }}
                  >
                    <Popup>
                      <strong>
                        Predicted Drift +{forecast.hours_ahead}h
                      </strong>
                      <br />
                      Forecast zone
                    </Popup>
                  </Polygon>
                );
              })}

            {/* ----------------------------------------
                VESSELS FROM CONTRACT C
                Real CPA coordinates and vessel ranking
            ----------------------------------------- */}

            {layers.vessels &&
              suspects.map((suspect, idx) => {
                const cpa = suspect.closest_encounter?.vessel_point_at_cpa;
                if (!cpa || !Array.isArray(cpa) || cpa.length < 2) return null;
                const pos = [cpa[1], cpa[0]];

                const vName =
                  suspect.vessel_metadata?.vessel_name ??
                  suspect.vessel_name ??
                  suspect.name ??
                  `MMSI ${suspect.mmsi ?? idx + 1}`;

                const vType =
                  suspect.vessel_metadata?.vessel_type ??
                  suspect.vessel_type ??
                  suspect.type ??
                  "Vessel";

                const rawScore =
                  suspect.composite_threat_score ?? suspect.score ?? 0;
                const score =
                  rawScore <= 1
                    ? Math.round(rawScore * 100)
                    : Math.round(rawScore);

                const isSelected = vName === selectedVessel;

                const proximity =
                  suspect.closest_encounter?.min_distance_to_origin_km != null
                    ? `${suspect.closest_encounter.min_distance_to_origin_km.toFixed(1)} km`
                    : suspect.proximity_km != null
                    ? `${suspect.proximity_km} km`
                    : "--";

                const flags =
                  suspect.anomaly_indicators ??
                  (Array.isArray(suspect.anomaly_flags)
                    ? suspect.anomaly_flags
                    : []);

                return (
                  <CircleMarker
                    key={`vessel-${suspect.mmsi ?? idx}`}
                    center={pos}
                    radius={isSelected ? 8 : 5}
                    pathOptions={{
                      color: isSelected
                        ? "#ff5252"
                        : "#23c0e5",

                      fillColor: isSelected
                        ? "#ff5252"
                        : "#23c0e5",

                      fillOpacity: 0.9,
                    }}
                    eventHandlers={{
                      click: () =>
                        setSelectedVessel(vName),
                    }}
                  >

                    <Popup>

                      <strong>
                        {vName}
                      </strong>

                      <br />

                      MMSI: {suspect.mmsi ?? "--"}

                      <br />

                      Type: {vType}

                      <br />

                      Attribution Score:{" "}
                      {score}/100 ({suspect.threat_level ?? "ASSESSED"})

                      <br />

                      Proximity to Origin:{" "}
                      {proximity}

                      <br />

                      Flags:{" "}
                      {flags.length ? flags.join(", ") : "None"}

                    </Popup>

                  </CircleMarker>
                );
              })}

            {/* ----------------------------------------
                VESSEL TRAJECTORIES FROM CONTRACT C
            ----------------------------------------- */}

            {layers.vessels &&
              suspects.map((suspect, idx) => {
                const trajCoords =
                  suspect.trajectory_geojson?.geometry?.coordinates ??
                  suspect.trajectory_geojson?.coordinates;
                if (!trajCoords || !Array.isArray(trajCoords) || trajCoords.length < 2) return null;
                const latLngs = geoJsonToLeaflet(trajCoords);
                return (
                  <Polyline
                    key={`traj-${suspect.mmsi ?? idx}`}
                    positions={latLngs}
                    pathOptions={{
                      color: suspect.threat_level === "HIGH" ? "#ff4d4d" : "#4ed6e8",
                      weight: 1.5,
                      dashArray: "4 6",
                      opacity: 0.7,
                    }}
                  >
                    <Popup>
                      <strong>
                        AIS Track:{" "}
                        {suspect.vessel_name ??
                          suspect.vessel_metadata?.vessel_name ??
                          `MMSI ${suspect.mmsi}`}
                      </strong>
                    </Popup>
                  </Polyline>
                );
              })}

          </MapContainer>

          {/* ----------------------------------------
              MAP LAYERS
          ----------------------------------------- */}

          <div className="map-layers-panel">

            <div className="panel-heading">
              <span>Map Layers</span>
              <span className="close-layer">×</span>
            </div>

            {[
              ["spill", "Oil Spill"],
              ["drift", "Backtrack Track"],
              ["vessels", "AIS Vessels"],
              ["forecast", "Predicted Drift"],
              ["zones", "Protected Zones"],
            ].map(([key, label]) => (
              <label
                className="layer-row"
                key={key}
              >

                <input
                  type="checkbox"
                  checked={layers[key]}
                  onChange={() =>
                    toggleLayer(key)
                  }
                />

                <span>{label}</span>

              </label>
            ))}

          </div>

          {/* ----------------------------------------
              QUICK INFO
          ----------------------------------------- */}

          <div className="quick-info-panel">

            <div className="panel-heading">
              Quick Info
            </div>

            <div className="info-row">
              <span>Spill Area</span>
              <strong>
                {detectData?.area_km2 ?? "--"} km²
              </strong>
            </div>

            <div className="info-row">
              <span>Confidence</span>
              <strong>
                {detectData?.confidence != null
                  ? `${Math.round(
                      detectData.confidence * 100
                    )}%`
                  : "--"}
              </strong>
            </div>

            <div className="info-row">
              <span>Detected</span>
              <strong>
                {detectData?.timestamp_utc
                  ? new Date(
                      detectData.timestamp_utc
                    ).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "--"}
              </strong>
            </div>

            <div className="info-row">
              <span>Location</span>
              <strong>
                {driftData?.estimated_origin?.point
                  ? `${driftData.estimated_origin.point[1].toFixed(
                      2
                    )}°N, ${driftData.estimated_origin.point[0].toFixed(
                      2
                    )}°E`
                  : "--"}
              </strong>
            </div>

          </div>

          {/* ----------------------------------------
              SELECTED VESSEL
          ----------------------------------------- */}

          <div className="selected-vessel">

            <div className="selected-label">
              TOP SUSPECT
            </div>

            <div className="selected-name">
              {selectedSuspect?.vessel_name ??
                selectedSuspect?.vessel_metadata?.vessel_name ??
                selectedVessel}
            </div>

            <div className="selected-score">
              Score{" "}
              {selectedSuspect
                ? Math.round(
                    (selectedSuspect.composite_threat_score ??
                      selectedSuspect.score ??
                      0) <= 1
                      ? (selectedSuspect.composite_threat_score ??
                          selectedSuspect.score ??
                          0) * 100
                      : (selectedSuspect.composite_threat_score ??
                          selectedSuspect.score ??
                          0)
                  )
                : "--"}
              /100
            </div>

          </div>

          {/* ----------------------------------------
              MAP LEGEND
          ----------------------------------------- */}

          <div className="map-legend">

            <div>
              <span className="legend-dot spill-dot" />
              Oil Spill
            </div>

            <div>
              <span className="legend-line" />
              Backtrack
            </div>

            <div>
              <span className="legend-dot vessel-dot" />
              Vessel
            </div>

          </div>

        </section>

        {/* ----------------------------------------
            TIMELINE
        ----------------------------------------- */}

        <section className="timeline-panel">

          <div className="timeline-top">

            <span>
              {detectData?.timestamp_utc
                ? new Date(
                    detectData.timestamp_utc
                  ).toLocaleDateString(
                    "en-GB",
                    {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    }
                  )
                : "--"}
            </span>

            <span className="timeline-current">
              {time}%
            </span>

            <span>+24h</span>

          </div>

          <input
            type="range"
            min="0"
            max="100"
            value={time}
            onChange={(event) =>
              setTime(event.target.value)
            }
            className="timeline-slider"
          />

          <div className="timeline-labels">
            <span>08:00</span>
            <span>10:00</span>
            <span>12:00</span>
            <span>14:23</span>
            <span>+6h</span>
            <span>+12h</span>
            <span>+18h</span>
            <span>+24h</span>
          </div>

        </section>

      </main>
    </div>
  );
}

export default Investigation;