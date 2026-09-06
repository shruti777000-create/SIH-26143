import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MapContainer,
  TileLayer,
  Polygon,
  Polyline,
  CircleMarker,
  Tooltip,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "../forecast.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`forecast-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="forecast-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

// GeoJSON uses [longitude, latitude]
// Leaflet uses [latitude, longitude]
function geoJsonToLeaflet(coordinates) {
  return coordinates.map(([lng, lat]) => [lat, lng]);
}

function polygonFromGeoJSON(geometry) {
  if (!geometry || geometry.type !== "Polygon") {
    return [];
  }

  return geometry.coordinates.map((ring) =>
    geoJsonToLeaflet(ring)
  );
}

// Calculate a simple center for a polygon.
// Used only to place the +6h / +24h markers.
function getPolygonCenter(positions) {
  if (!positions || positions.length === 0) {
    return null;
  }

  // GeoJSON Polygon becomes an array of rings.
  // Use the first ring for the center calculation.
  const ring = Array.isArray(positions[0][0])
    ? positions[0]
    : positions;

  if (!ring || ring.length === 0) {
    return null;
  }

  const lat =
    ring.reduce((sum, point) => sum + point[0], 0) /
    ring.length;

  const lng =
    ring.reduce((sum, point) => sum + point[1], 0) /
    ring.length;

  return [lat, lng];
}
function Forecast() {
  const navigate = useNavigate();

  // --------------------------------------------------
  // FASTAPI DATA
  // --------------------------------------------------

  const [driftData, setDriftData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  // --------------------------------------------------
  // FETCH /api/drift
  // --------------------------------------------------

  useEffect(() => {
    async function loadDriftData() {
      try {
        setLoading(true);
        setApiError("");

        const response = await fetch(
          "http://127.0.0.1:8000/api/drift"
        );

        if (!response.ok) {
          throw new Error("Drift API request failed");
        }

        const data = await response.json();

        setDriftData(data);
      } catch (error) {
        console.error("MARIS Drift API Error:", error);

        setApiError(
          "Unable to connect to MARIS FastAPI backend."
        );
      } finally {
        setLoading(false);
      }
    }

    loadDriftData();
  }, []);

  // --------------------------------------------------
  // API DATA
  // --------------------------------------------------

  const originPoint =
    driftData?.estimated_origin?.point;

  const origin = originPoint
    ? [originPoint[1], originPoint[0]]
    : [13.08, 80.27];

  const backtrack =
    driftData?.backtrack_track?.coordinates
      ? geoJsonToLeaflet(
          driftData.backtrack_track.coordinates
        )
      : [];

  const forecastPolygons =
    driftData?.forecast_polygons || [];

  const forecast6Data = forecastPolygons.find(
    (item) => item.hours_ahead === 6
  );

  const forecast24Data = forecastPolygons.find(
    (item) => item.hours_ahead === 24
  );

  const forecast6h = forecast6Data
    ? polygonFromGeoJSON(forecast6Data.geometry)
    : [];

  const forecast24h = forecast24Data
    ? polygonFromGeoJSON(forecast24Data.geometry)
    : [];

  const forecast6Position =
    getPolygonCenter(forecast6h);

  const forecast24Position =
    getPolygonCenter(forecast24h);

  const originTime =
    driftData?.estimated_origin?.time_utc
      ? new Date(
          driftData.estimated_origin.time_utc
        )
      : null;

  const formattedOriginTime = originTime
    ? originTime.toLocaleString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : "--";

  // --------------------------------------------------
  // LOADING
  // --------------------------------------------------

  if (loading) {
    return (
      <div className="forecast-page">

        <aside className="forecast-sidebar">

          <div className="forecast-brand">

            <div className="forecast-brand-mark">
              M
            </div>

            <div>
              <div className="forecast-brand-name">
                MARIS
              </div>

              <div className="forecast-brand-subtitle">
                Maritime Oil Spill Intelligence
              </div>
            </div>

          </div>

          <div className="forecast-system">

            <span className="forecast-status-dot"></span>

            <div>
              <strong>Connecting...</strong>
              <small>MARIS intelligence services</small>
            </div>

          </div>

        </aside>

        <main className="forecast-main">

          <header className="forecast-header">

            <div>

              <div className="forecast-kicker">
                INVESTIGATION / DRIFT / FORECAST
              </div>

              <h1>
                Drift Forecast
              </h1>

              <p>
                Connecting to MARIS drift intelligence service...
              </p>

            </div>

          </header>

          <div
            style={{
              padding: "30px",
              color: "#23c0e5",
            }}
          >
            Loading forecast data...
          </div>

        </main>

      </div>
    );
  }

  return (
    <div className="forecast-page">

      {/* ==================================================
          SIDEBAR
      ================================================== */}

      <aside className="forecast-sidebar">

        <div className="forecast-brand">

          <div className="forecast-brand-mark">
            M
          </div>

          <div>

            <div className="forecast-brand-name">
              MARIS
            </div>

            <div className="forecast-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>

          </div>

        </div>

        <div className="forecast-nav">

          <SidebarItem
            icon="⌂"
            label="Dashboard"
            onClick={() => navigate("/")}
          />

          <SidebarItem
            icon="⌖"
            label="Map"
            onClick={() => navigate("/investigation")}
          />

          <SidebarItem
            icon="≋"
            label="Pipeline"
            onClick={() => navigate("/pipeline")}
          />

          <SidebarItem
            icon="♢"
            label="Vessels"
            onClick={() => navigate("/vessels")}
          />

          <SidebarItem
            icon="◌"
            label="Forecast"
            active
            onClick={() => navigate("/forecast")}
          />

          <SidebarItem
            icon="▤"
            label="Reports"
            onClick={() => navigate("/reports")}
          />

        </div>

        <div className="forecast-system">

          <span className="forecast-status-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>Forecast engine ready</small>
          </div>

        </div>

        <div style={{ marginTop: "auto" }}>

          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />

        </div>

      </aside>

      {/* ==================================================
          MAIN
      ================================================== */}

      <main className="forecast-main">

        {/* HEADER */}

        <header className="forecast-header">

          <div>

            <div className="forecast-kicker">
              INVESTIGATION / DRIFT / FORECAST
            </div>

            <h1>
              Drift Forecast
            </h1>

            <p>
              Predicted oil slick movement based on estimated origin and ocean dynamics
            </p>

          </div>

          <div className="forecast-header-status">

            <div className="forecast-live">

              <span></span>

              {apiError
                ? "API ERROR"
                : "FORECAST READY"}

            </div>

            <div className="forecast-time">

              {formattedOriginTime}

            </div>

          </div>

        </header>

        {/* API ERROR */}

        {apiError && (
          <div
            style={{
              marginBottom: "14px",
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

        {/* ==================================================
            MAP + INFORMATION
        ================================================== */}

        <section className="forecast-layout">

          {/* MAP */}

          <div className="forecast-map-panel">

            <div className="forecast-map">

              <MapContainer
                center={origin}
                zoom={11}
                scrollWheelZoom={true}
                zoomControl={true}
              >

                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                {/* ==========================================
                    +24 HOUR FORECAST ZONE
                ========================================== */}

                {forecast24h.length > 0 && (
                  <Polygon
                    positions={forecast24h}
                    pathOptions={{
                      color: "#d56b6b",
                      weight: 1.5,
                      fillColor: "#d56b6b",
                      fillOpacity: 0.10,
                      dashArray: "7 5",
                    }}
                  >
                    <Tooltip>
                      +24 hour forecast zone
                    </Tooltip>
                  </Polygon>
                )}

                {/* ==========================================
                    +6 HOUR FORECAST ZONE
                ========================================== */}

                {forecast6h.length > 0 && (
                  <Polygon
                    positions={forecast6h}
                    pathOptions={{
                      color: "#63c6cc",
                      weight: 1.5,
                      fillColor: "#63c6cc",
                      fillOpacity: 0.20,
                    }}
                  >
                    <Tooltip>
                      +6 hour forecast zone
                    </Tooltip>
                  </Polygon>
                )}

                {/* ==========================================
                    HINDCAST / BACKTRACK
                ========================================== */}

                {backtrack.length > 0 && (
                  <Polyline
                    positions={backtrack}
                    pathOptions={{
                      color: "#c96a6a",
                      weight: 2,
                      dashArray: "5 7",
                    }}
                  >
                    <Tooltip>
                      Estimated backtrack trajectory
                    </Tooltip>
                  </Polyline>
                )}

                {/* ==========================================
                    ORIGIN
                ========================================== */}

                <CircleMarker
                  center={origin}
                  radius={8}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#e05252",
                    fillOpacity: 1,
                  }}
                >

                  <Tooltip direction="top">

                    <strong>
                      Estimated Spill Origin
                    </strong>

                    <br />

                    {origin[0].toFixed(2)}° N ·{" "}
                    {origin[1].toFixed(2)}° E

                  </Tooltip>

                </CircleMarker>

                {/* ==========================================
                    +6 HOUR POSITION
                ========================================== */}

                {forecast6Position && (
                  <CircleMarker
                    center={forecast6Position}
                    radius={6}
                    pathOptions={{
                      color: "#ffffff",
                      weight: 2,
                      fillColor: "#63c6cc",
                      fillOpacity: 1,
                    }}
                  >

                    <Tooltip>
                      +6 hour forecast zone
                    </Tooltip>

                  </CircleMarker>
                )}

                {/* ==========================================
                    +24 HOUR POSITION
                ========================================== */}

                {forecast24Position && (
                  <CircleMarker
                    center={forecast24Position}
                    radius={6}
                    pathOptions={{
                      color: "#ffffff",
                      weight: 2,
                      fillColor: "#d56b6b",
                      fillOpacity: 1,
                    }}
                  >

                    <Tooltip>
                      +24 hour forecast zone
                    </Tooltip>

                  </CircleMarker>
                )}

              </MapContainer>

              {/* MAP TITLE */}

              <div className="map-overlay-title">

                <span>
                  OIL SLICK DRIFT MODEL
                </span>

                <strong>
                  BAY OF BENGAL
                </strong>

              </div>

              {/* LEGEND */}

              <div className="forecast-legend">

                <div className="legend-title">
                  FORECAST LAYERS
                </div>

                <div className="legend-row">

                  <span className="legend-line origin-line"></span>

                  Estimated origin

                </div>

                <div className="legend-row">

                  <span className="legend-line forecast-line"></span>

                  Predicted track

                </div>

                <div className="legend-row">

                  <span className="legend-box six-hour"></span>

                  +6h zone

                </div>

                <div className="legend-row">

                  <span className="legend-box twenty-four-hour"></span>

                  +24h zone

                </div>

              </div>

              {/* COORDINATES */}

              <div className="map-coordinates">

                {origin[0].toFixed(2)}° N&nbsp;&nbsp;
                {origin[1].toFixed(2)}° E

              </div>

            </div>

          </div>

          {/* ==================================================
              RIGHT INFORMATION PANEL
          ================================================== */}

          <aside className="forecast-info">

            <div className="forecast-info-header">

              <div>

                <span>
                  01
                </span>

                <h2>
                  Origin Estimate
                </h2>

              </div>

              <small>
                HINDCAST
              </small>

            </div>

            <div className="origin-coordinate">

              <strong>
                {origin[0].toFixed(2)}° N
              </strong>

              <strong>
                {origin[1].toFixed(2)}° E
              </strong>

            </div>

            <div className="origin-time">

              Estimated origin ·{" "}
              {originTime
                ? originTime.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "UTC",
                  }) + " UTC"
                : "--"}

            </div>

            <div className="info-divider"></div>

            <div className="forecast-metric">

              <span>
                MODEL
              </span>

              <strong>
                OpenDrift
              </strong>

              <small>
                Ocean current and wind driven transport
              </small>

            </div>

            <div className="forecast-metric">

              <span>
                INITIAL AREA
              </span>

              <strong>
                12.4 km²
              </strong>

              <small>
                Detected Sentinel-1 slick
              </small>

            </div>

            <div className="forecast-metric">

              <span>
                FORECAST HORIZON
              </span>

              <strong>
                +24 hours
              </strong>

              <small>
                Drift prediction available
              </small>

            </div>

            <div className="confidence-card">

              <div>

                <span>
                  FORECAST STATUS
                </span>

                <strong>
                  READY
                </strong>

              </div>

              <div className="forecast-confidence-track">

                <div
                  style={{
                    width: "78%",
                  }}
                ></div>

              </div>

              <small>
                Forecast zones received from drift service
              </small>

            </div>

          </aside>

        </section>

        {/* ==================================================
            TIMELINE
        ================================================== */}

        <section className="forecast-timeline">

          <div className="timeline-header">

            <div>

              <span>
                02
              </span>

              <div>

                <h2>
                  Drift Forecast Timeline
                </h2>

                <p>
                  Select forecast horizon to inspect predicted slick position
                </p>

              </div>

            </div>

            <div className="timeline-source">
              OPENDRIFT MODEL
            </div>

          </div>

          <div className="timeline">

            <div className="timeline-line"></div>

            <div className="timeline-point current">

              <div className="timeline-dot"></div>

              <strong>
                NOW
              </strong>

              <span>
                {originTime
                  ? originTime.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: "UTC",
                    })
                  : "--"}
              </span>

            </div>

            <div className="timeline-point">

              <div className="timeline-dot"></div>

              <strong>
                +6 H
              </strong>

              <span>
                FORECAST
              </span>

            </div>

            <div className="timeline-point selected">

              <div className="timeline-dot"></div>

              <strong>
                +12 H
              </strong>

              <span>
                INTERMEDIATE
              </span>

            </div>

            <div className="timeline-point">

              <div className="timeline-dot"></div>

              <strong>
                +24 H
              </strong>

              <span>
                FORECAST
              </span>

            </div>

          </div>

          {/* TIMELINE SUMMARY */}

          <div className="timeline-summary">

            <div>

              <span>
                AVAILABLE HORIZONS
              </span>

              <strong>
                +6H · +24H
              </strong>

            </div>

            <div>

              <span>
                ORIGIN
              </span>

              <strong>
                {origin[0].toFixed(2)}° N ·{" "}
                {origin[1].toFixed(2)}° E
              </strong>

            </div>

            <div>

              <span>
                SLICK ID
              </span>

              <strong>
                {driftData?.slick_id || "--"}
              </strong>

            </div>

            <button
              onClick={() => navigate("/vessels")}
            >

              Continue to Vessel Analysis

              <span>
                →
              </span>

            </button>

          </div>

        </section>

      </main>

    </div>
  );
}

export default Forecast;