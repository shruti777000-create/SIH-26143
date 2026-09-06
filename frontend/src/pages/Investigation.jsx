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

  const [selectedVessel, setSelectedVessel] = useState("Tanker A");
  const [time, setTime] = useState(62);

  // --------------------------------------------------
  // DEMO VESSEL POSITIONS
  //
  // Contract C provides vessel identity/ranking but
  // does NOT contain latitude/longitude.
  // So these positions remain temporary demo positions.
  // Later they can be replaced by Member 3's AIS data.
  // --------------------------------------------------

  const vesselPositions = [
    {
      name: "Tanker A",
      lat: 13.18,
      lng: 80.43,
      type: "Tanker",
    },
    {
      name: "Cargo B",
      lat: 13.26,
      lng: 80.18,
      type: "Cargo",
    },
    {
      name: "Tanker C",
      lat: 12.91,
      lng: 80.38,
      type: "Tanker",
    },
    {
      name: "Fishing D",
      lat: 13.31,
      lng: 80.51,
      type: "Fishing",
    },
  ];

  // --------------------------------------------------
  // FETCH FASTAPI DATA
  // --------------------------------------------------

  useEffect(() => {
    async function loadInvestigationData() {
      try {
        setLoading(true);
        setApiError("");

        const [detectResponse, driftResponse, attributeResponse] =
          await Promise.all([
            fetch("http://127.0.0.1:8000/api/detect"),
            fetch("http://127.0.0.1:8000/api/drift"),
            fetch("http://127.0.0.1:8000/api/attribute"),
          ]);

        if (
          !detectResponse.ok ||
          !driftResponse.ok ||
          !attributeResponse.ok
        ) {
          throw new Error("FastAPI request failed");
        }

        const detect = await detectResponse.json();
        const drift = await driftResponse.json();
        const attribute = await attributeResponse.json();

        setDetectData(detect);
        setDriftData(drift);
        setAttributeData(attribute);

        // Automatically select the highest-ranked suspect
        if (attribute?.suspects?.length > 0) {
          const topSuspect = [...attribute.suspects].sort(
            (a, b) => b.score - a.score
          )[0];

          setSelectedVessel(topSuspect.vessel_name);
        }
      } catch (error) {
        console.error("MARIS API Error:", error);

        setApiError(
          "Unable to connect to MARIS FastAPI backend."
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
    attributeData?.suspects || [];

  const selectedSuspect =
    suspects.find(
      (suspect) => suspect.vessel_name === selectedVessel
    ) || suspects[0];

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
            center={[13.10, 80.30]}
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
                  {detectData?.area_km2 ?? "--"} km²

                  <br />

                  Length:{" "}
                  {detectData?.length_km ?? "--"} km

                  <br />

                  Confidence:{" "}
                  {detectData?.confidence != null
                    ? `${Math.round(
                        detectData.confidence * 100
                      )}%`
                    : "--"}

                  <br />

                  Source:{" "}
                  {detectData?.source_image ?? "--"}
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
                VESSELS
                Ranking comes from /api/attribute.
                Positions are temporary demo AIS positions.
            ----------------------------------------- */}

            {layers.vessels &&
              vesselPositions.map((vessel) => {

                const suspect = suspects.find(
                  (item) =>
                    item.vessel_name === vessel.name
                );

                const score = suspect
                  ? Math.round(suspect.score * 100)
                  : 0;

                const isSelected =
                  vessel.name === selectedVessel;

                return (
                  <CircleMarker
                    key={vessel.name}
                    center={[
                      vessel.lat,
                      vessel.lng,
                    ]}
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
                        setSelectedVessel(
                          vessel.name
                        ),
                    }}
                  >

                    <Popup>

                      <strong>
                        {vessel.name}
                      </strong>

                      <br />

                      Type: {vessel.type}

                      <br />

                      Attribution Score:{" "}
                      {score}/100

                      {suspect && (
                        <>
                          <br />
                          Proximity:{" "}
                          {suspect.proximity_km} km

                          <br />

                          Flags:{" "}
                          {suspect.anomaly_flags?.length
                            ? suspect.anomaly_flags.join(
                                ", "
                              )
                            : "None"}
                        </>
                      )}

                    </Popup>

                  </CircleMarker>
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
              {selectedSuspect?.vessel_name ||
                selectedVessel}
            </div>

            <div className="selected-score">
              Score{" "}
              {selectedSuspect
                ? Math.round(
                    selectedSuspect.score * 100
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