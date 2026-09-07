import { useNavigate } from "react-router-dom";
import {
  MapContainer,
  TileLayer,
  Polygon,
  Circle,
  CircleMarker,
  Polyline,
  Tooltip,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "../environmental-impact.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`impact-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="impact-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function EnvironmentalImpact() {
  const navigate = useNavigate();

  // -----------------------------------------
  // MOCK ENVIRONMENTAL DATA
  // Replace later with real analysis data.
  // -----------------------------------------

  const spillArea = [
    [13.075, 80.255],
    [13.092, 80.270],
    [13.105, 80.295],
    [13.092, 80.320],
    [13.070, 80.312],
    [13.055, 80.285],
    [13.060, 80.265],
  ];

  const impactZone = [
    [13.040, 80.225],
    [13.105, 80.235],
    [13.135, 80.285],
    [13.110, 80.345],
    [13.055, 80.350],
    [13.020, 80.290],
  ];

  const coastlineTrack = [
    [13.145, 80.300],
    [13.120, 80.315],
    [13.095, 80.320],
    [13.070, 80.318],
    [13.045, 80.310],
  ];

  return (
    <div className="impact-page">

      {/* =========================================
          SIDEBAR
          ========================================= */}

      <aside className="impact-sidebar">

        <div className="impact-brand">

          <div className="impact-brand-mark">
            M
          </div>

          <div>
            <div className="impact-brand-name">
              MARIS
            </div>

            <div className="impact-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>
          </div>

        </div>


        <div className="impact-nav">

          <SidebarItem
            icon="⌂"
            label="Dashboard"
            onClick={() => navigate("/")}
          />

          <SidebarItem
            icon="◉"
            label="Incidents"
            onClick={() => navigate("/incidents")}
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
            onClick={() => navigate("/forecast")}
          />

          <SidebarItem
            icon="▤"
            label="Reports"
            onClick={() => navigate("/reports")}
          />

          

          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />

        </div>


        <div className="impact-system">

          <span className="impact-system-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>Environmental analysis ready</small>
          </div>

        </div>

      </aside>


      {/* =========================================
          MAIN
          ========================================= */}

      <main className="impact-main">

        {/* HEADER */}

        <header className="impact-header">

          <div>

            <div className="impact-kicker">
              INVESTIGATION / ENVIRONMENT / IMPACT
            </div>

            <h1>
              Environmental Impact
            </h1>

            <p>
              Estimated environmental exposure from the detected oil slick
            </p>

          </div>


          <div className="impact-header-right">

            <div className="impact-live">
              <span></span>
              IMPACT ASSESSMENT READY
            </div>

            <div className="impact-time">
              19 MAR 2019 · 18:11 UTC
            </div>

          </div>

        </header>


        {/* =========================================
            TOP SUMMARY
            ========================================= */}

        <section className="impact-summary">

          <div className="impact-summary-item">

            <span>
              DETECTED SPILL
            </span>

            <strong>
              12.4 km²
            </strong>

            <small>
              Sentinel-1 derived slick area
            </small>

          </div>


          <div className="impact-summary-item">

            <span>
              ESTIMATED IMPACT ZONE
            </span>

            <strong>
              42.7 km²
            </strong>

            <small>
              Current modeled exposure area
            </small>

          </div>


          <div className="impact-summary-item">

            <span>
              COASTAL EXPOSURE
            </span>

            <strong>
              18.6 km
            </strong>

            <small>
              Potentially exposed coastline
            </small>

          </div>


          <div className="impact-summary-item">

            <span>
              IMPACT LEVEL
            </span>

            <strong className="impact-high">
              HIGH
            </strong>

            <small>
              Based on modeled exposure
            </small>

          </div>

        </section>


        {/* =========================================
            MAP + ASSESSMENT
            ========================================= */}

        <section className="impact-layout">

          {/* MAP */}

          <div className="impact-map-panel">

            <div className="impact-map">

              <MapContainer
                center={[13.08, 80.29]}
                zoom={11}
                scrollWheelZoom={true}
                zoomControl={true}
              >

                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />


                {/* Wider environmental impact zone */}

                <Polygon
                  positions={impactZone}
                  pathOptions={{
                    color: "#c4a965",
                    weight: 2,
                    dashArray: "7 7",
                    fillColor: "#c4a965",
                    fillOpacity: 0.08,
                  }}
                >
                  <Tooltip>
                    Estimated environmental impact zone
                  </Tooltip>
                </Polygon>


                {/* Oil slick */}

                <Polygon
                  positions={spillArea}
                  pathOptions={{
                    color: "#d66c6c",
                    weight: 2,
                    fillColor: "#d66c6c",
                    fillOpacity: 0.35,
                  }}
                >
                  <Tooltip>
                    Detected oil slick — 12.4 km²
                  </Tooltip>
                </Polygon>


                {/* Coastal exposure corridor */}

                <Polyline
                  positions={coastlineTrack}
                  pathOptions={{
                    color: "#66c7cf",
                    weight: 3,
                    dashArray: "5 6",
                  }}
                />


                {/* Spill origin */}

                <CircleMarker
                  center={[13.08, 80.27]}
                  radius={8}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#d65f5f",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Estimated spill origin
                  </Tooltip>
                </CircleMarker>


                {/* Sensitive marine area */}

                <Circle
                  center={[13.105, 80.315]}
                  radius={6500}
                  pathOptions={{
                    color: "#65c5cc",
                    weight: 1,
                    dashArray: "4 6",
                    fillColor: "#65c5cc",
                    fillOpacity: 0.04,
                  }}
                >
                  <Tooltip>
                    Sensitive marine exposure area
                  </Tooltip>
                </Circle>


                {/* Impact markers */}

                <CircleMarker
                  center={[13.105, 80.315]}
                  radius={6}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 1,
                    fillColor: "#c4a965",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Marine exposure zone
                  </Tooltip>
                </CircleMarker>


                <CircleMarker
                  center={[13.065, 80.305]}
                  radius={6}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 1,
                    fillColor: "#c4a965",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Coastal exposure
                  </Tooltip>
                </CircleMarker>

              </MapContainer>


              {/* MAP HEADER */}

              <div className="impact-map-title">

                <span>
                  ENVIRONMENTAL EXPOSURE MODEL
                </span>

                <strong>
                  CHENNAI · BAY OF BENGAL
                </strong>

              </div>


              {/* LEGEND */}

              <div className="impact-map-legend">

                <div className="impact-legend-title">
                  IMPACT LAYERS
                </div>

                <div className="impact-legend-row">
                  <span className="impact-legend-box spill"></span>
                  Detected oil slick
                </div>

                <div className="impact-legend-row">
                  <span className="impact-legend-box zone"></span>
                  Impact zone
                </div>

                <div className="impact-legend-row">
                  <span className="impact-legend-line coast"></span>
                  Coastal exposure
                </div>

                <div className="impact-legend-row">
                  <span className="impact-legend-dot origin"></span>
                  Spill origin
                </div>

              </div>


              <div className="impact-map-label">
                MODELLED EXPOSURE
              </div>

            </div>

          </div>


          {/* RIGHT ASSESSMENT */}

          <aside className="impact-assessment">

            <div className="impact-panel-header">

              <div>

                <span>
                  01
                </span>

                <h2>
                  Impact Assessment
                </h2>

              </div>

              <small>
                MODEL
              </small>

            </div>


            <div className="impact-rating">

              <span>
                OVERALL IMPACT
              </span>

              <strong>
                HIGH
              </strong>

              <p>
                Significant modeled exposure within the current
                investigation area.
              </p>

            </div>


            <div className="impact-metric">

              <span>
                MARINE EXPOSURE
              </span>

              <div className="impact-metric-value">
                <strong>
                  42.7 km²
                </strong>

                <small>
                  76%
                </small>
              </div>

              <div className="impact-progress">
                <div style={{ width: "76%" }}></div>
              </div>

              <p>
                Estimated marine area within modeled impact zone.
              </p>

            </div>


            <div className="impact-metric">

              <span>
                COASTAL EXPOSURE
              </span>

              <div className="impact-metric-value">
                <strong>
                  18.6 km
                </strong>

                <small>
                  61%
                </small>
              </div>

              <div className="impact-progress">
                <div style={{ width: "61%" }}></div>
              </div>

              <p>
                Potential shoreline exposure based on current drift.
              </p>

            </div>


            <div className="impact-metric">

              <span>
                ECOLOGICAL SENSITIVITY
              </span>

              <div className="impact-metric-value">
                <strong>
                  MODERATE
                </strong>

                <small>
                  58%
                </small>
              </div>

              <div className="impact-progress">
                <div style={{ width: "58%" }}></div>
              </div>

              <p>
                Sensitive marine regions overlap with the modeled zone.
              </p>

            </div>


            <div className="impact-confidence">

              <div>

                <span>
                  MODEL CONFIDENCE
                </span>

                <strong>
                  78%
                </strong>

              </div>

              <div className="impact-confidence-bar">
                <div></div>
              </div>

              <small>
                Confidence depends on current drift and wind conditions.
              </small>

            </div>

          </aside>

        </section>


        {/* =========================================
            ENVIRONMENTAL INDICATORS
            ========================================= */}

        <section className="impact-indicators">

          <div className="impact-section-heading">

            <div>

              <span>
                02
              </span>

              <div>

                <h2>
                  Environmental Indicators
                </h2>

                <p>
                  Potentially affected environmental receptors
                </p>

              </div>

            </div>

            <small>
              4 INDICATORS
            </small>

          </div>


          <div className="impact-indicator-grid">


            <div className="impact-indicator">

              <div className="indicator-number">
                01
              </div>

              <div>

                <span>
                  MARINE
                </span>

                <h3>
                  Open Water
                </h3>

                <strong>
                  HIGH EXPOSURE
                </strong>

                <p>
                  Detected slick occupies a significant portion of the
                  modeled marine impact area.
                </p>

              </div>

            </div>


            <div className="impact-indicator">

              <div className="indicator-number">
                02
              </div>

              <div>

                <span>
                  COASTAL
                </span>

                <h3>
                  Shoreline
                </h3>

                <strong>
                  MODERATE EXPOSURE
                </strong>

                <p>
                  Current drift trajectory indicates potential coastal
                  exposure if transport continues.
                </p>

              </div>

            </div>


            <div className="impact-indicator">

              <div className="indicator-number">
                03
              </div>

              <div>

                <span>
                  ECOLOGICAL
                </span>

                <h3>
                  Sensitive Areas
                </h3>

                <strong>
                  MODERATE
                </strong>

                <p>
                  Modeled impact zone overlaps areas requiring additional
                  environmental assessment.
                </p>

              </div>

            </div>


            <div className="impact-indicator">

              <div className="indicator-number">
                04
              </div>

              <div>

                <span>
                  RESPONSE
                </span>

                <h3>
                  Priority
                </h3>

                <strong>
                  HIGH
                </strong>

                <p>
                  Early containment and continued monitoring are recommended
                  for the modeled exposure zone.
                </p>

              </div>

            </div>

          </div>

        </section>


        {/* =========================================
            RESPONSE SUMMARY
            ========================================= */}

        <section className="impact-response">

          <div className="impact-section-heading">

            <div>

              <span>
                03
              </span>

              <div>

                <h2>
                  Response Assessment
                </h2>

                <p>
                  Automated summary for incident review
                </p>

              </div>

            </div>

            <small>
              PRELIMINARY
            </small>

          </div>


          <div className="impact-response-content">

            <div className="impact-response-text">

              <span>
                CURRENT ASSESSMENT
              </span>

              <h3>
                Elevated environmental exposure detected
              </h3>

              <p>
                The detected slick and modeled drift zone indicate
                potentially significant marine exposure. Continued
                observation is recommended while the forecast evolves.
              </p>

            </div>


            <div className="impact-response-stats">

              <div>
                <span>
                  SPILL AREA
                </span>

                <strong>
                  12.4 km²
                </strong>
              </div>

              <div>
                <span>
                  IMPACT ZONE
                </span>

                <strong>
                  42.7 km²
                </strong>
              </div>

              <div>
                <span>
                  PRIORITY
                </span>

                <strong className="impact-high">
                  HIGH
                </strong>
              </div>

            </div>

          </div>

        </section>


        {/* =========================================
            FOOTER
            ========================================= */}

        <section className="impact-footer">

          <div>
            <span>
              INCIDENT
            </span>

            <strong>
              SLICK-MARIS-001
            </strong>
          </div>

          <div>
            <span>
              IMPACT LEVEL
            </span>

            <strong className="impact-high">
              HIGH
            </strong>
          </div>

          <div>
            <span>
              MODEL CONFIDENCE
            </span>

            <strong>
              78%
            </strong>
          </div>


          <button
            onClick={() => navigate("/report")}
          >
            Continue to Incident Report
            <span>→</span>
          </button>

        </section>

      </main>

    </div>
  );
}

export default EnvironmentalImpact;