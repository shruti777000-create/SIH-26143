import { useNavigate } from "react-router-dom";
import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  Tooltip,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "../vessel-behavior.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`behavior-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="behavior-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function VesselBehavior() {
  const navigate = useNavigate();

  /*
   * MOCK AIS DATA
   * Later replace this with Member 3's real AIS response.
   */

  const vesselTrack = [
    [13.225, 80.315],
    [13.205, 80.325],
    [13.185, 80.340],
    [13.165, 80.355],
    [13.145, 80.365],
    [13.125, 80.375],
    [13.105, 80.390],
  ];

  // Gap section
  const gapTrack = [
    [13.105, 80.390],
    [13.075, 80.405],
  ];

  // Track after AIS signal returns
  const resumedTrack = [
    [13.075, 80.405],
    [13.055, 80.420],
    [13.035, 80.438],
    [13.015, 80.458],
    [12.995, 80.480],
  ];

  const spillOrigin = [13.08, 80.27];

  const courseDeviation = [13.125, 80.375];

  const speedAnomaly = [13.055, 80.42];

  return (
    <div className="behavior-page">

      {/* =========================================
          SIDEBAR
          ========================================= */}

      <aside className="behavior-sidebar">

        <div className="behavior-brand">

          <div className="behavior-brand-mark">
            M
          </div>

          <div>
            <div className="behavior-brand-name">
              MARIS
            </div>

            <div className="behavior-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>
          </div>

        </div>


        <div className="behavior-nav">

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
            active
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
            icon="△"
            label="Alerts"
            onClick={() => navigate("/alerts")}
          />

          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />

        </div>


        <div className="behavior-system">

          <span className="behavior-status-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>AIS behavior analysis ready</small>
          </div>

        </div>

      </aside>


      {/* =========================================
          MAIN
          ========================================= */}

      <main className="behavior-main">

        {/* HEADER */}

        <header className="behavior-header">

          <div>

            <div className="behavior-kicker">
              INVESTIGATION / VESSEL / BEHAVIOR
            </div>

            <h1>
              Vessel Behavior
            </h1>

            <p>
              AIS track analysis and anomalous movement detection
            </p>

          </div>


          <div className="behavior-header-right">

            <div className="behavior-live">
              <span></span>
              BEHAVIOR ANALYSIS
            </div>

            <div className="behavior-time">
              19 MAR 2019 · 18:11 UTC
            </div>

          </div>

        </header>


        {/* =========================================
            VESSEL IDENTIFICATION
            ========================================= */}

        <section className="behavior-vessel-header">

          <div className="behavior-vessel-id">

            <div className="behavior-vessel-number">
              01
            </div>

            <div>

              <span>
                SELECTED VESSEL
              </span>

              <h2>
                Tanker A
              </h2>

              <small>
                MMSI 636019847 · Oil / Chemical Tanker
              </small>

            </div>

          </div>


          <div className="behavior-vessel-status">

            <span>
              CURRENT STATUS
            </span>

            <strong>
              ANALYSIS FLAGGED
            </strong>

          </div>


          <div className="behavior-score">

            <span>
              ATTRIBUTION SCORE
            </span>

            <strong>
              87
            </strong>

            <small>
              / 100
            </small>

          </div>

        </section>


        {/* =========================================
            MAP + VESSEL DATA
            ========================================= */}

        <section className="behavior-layout">


          {/* MAP */}

          <div className="behavior-map-panel">

            <div className="behavior-map">

              <MapContainer
                center={[13.10, 80.38]}
                zoom={11}
                scrollWheelZoom={true}
                zoomControl={true}
              >

                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />


                {/* Spill origin */}

                <CircleMarker
                  center={spillOrigin}
                  radius={8}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#d95d5d",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Estimated spill origin
                  </Tooltip>
                </CircleMarker>


                {/* Normal AIS track */}

                <Polyline
                  positions={vesselTrack}
                  pathOptions={{
                    color: "#62c5cc",
                    weight: 4,
                  }}
                />


                {/* AIS gap */}

                <Polyline
                  positions={gapTrack}
                  pathOptions={{
                    color: "#d56f6f",
                    weight: 3,
                    dashArray: "6 7",
                  }}
                />


                {/* Resumed track */}

                <Polyline
                  positions={resumedTrack}
                  pathOptions={{
                    color: "#62c5cc",
                    weight: 4,
                  }}
                />


                {/* Course deviation */}

                <CircleMarker
                  center={courseDeviation}
                  radius={7}
                  pathOptions={{
                    color: "#d6b66c",
                    weight: 2,
                    fillColor: "#d6b66c",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Course deviation detected
                  </Tooltip>
                </CircleMarker>


                {/* Speed anomaly */}

                <CircleMarker
                  center={speedAnomaly}
                  radius={7}
                  pathOptions={{
                    color: "#d56f6f",
                    weight: 2,
                    fillColor: "#d56f6f",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Speed anomaly detected
                  </Tooltip>
                </CircleMarker>


                {/* Current vessel */}

                <CircleMarker
                  center={resumedTrack[resumedTrack.length - 1]}
                  radius={9}
                  pathOptions={{
                    color: "#ffffff",
                    weight: 2,
                    fillColor: "#62c5cc",
                    fillOpacity: 1,
                  }}
                >
                  <Tooltip>
                    Tanker A — current analyzed position
                  </Tooltip>
                </CircleMarker>

              </MapContainer>


              {/* MAP TITLE */}

              <div className="behavior-map-title">

                <span>
                  AIS TRACK ANALYSIS
                </span>

                <strong>
                  TANKER A
                </strong>

              </div>


              {/* MAP LEGEND */}

              <div className="behavior-map-legend">

                <div className="behavior-legend-title">
                  TRACK INDICATORS
                </div>

                <div className="behavior-legend-row">
                  <span className="behavior-legend-line normal"></span>
                  AIS track
                </div>

                <div className="behavior-legend-row">
                  <span className="behavior-legend-line gap"></span>
                  AIS signal gap
                </div>

                <div className="behavior-legend-row">
                  <span className="behavior-legend-dot course"></span>
                  Course deviation
                </div>

                <div className="behavior-legend-row">
                  <span className="behavior-legend-dot speed"></span>
                  Speed anomaly
                </div>

                <div className="behavior-legend-row">
                  <span className="behavior-legend-dot origin"></span>
                  Spill origin
                </div>

              </div>


              <div className="behavior-map-coordinates">
                BAY OF BENGAL · CHENNAI
              </div>

            </div>

          </div>


          {/* =========================================
              RIGHT VESSEL INFORMATION
              ========================================= */}

          <aside className="behavior-info">

            <div className="behavior-info-header">

              <div>

                <span>
                  02
                </span>

                <h2>
                  Vessel Parameters
                </h2>

              </div>

              <small>
                AIS
              </small>

            </div>


            <div className="behavior-param">

              <span>
                VESSEL TYPE
              </span>

              <strong>
                Oil / Chemical Tanker
              </strong>

            </div>


            <div className="behavior-param">

              <span>
                SPEED
              </span>

              <strong>
                11.8 kn
              </strong>

              <small>
                4.2 kn above expected range
              </small>

            </div>


            <div className="behavior-param">

              <span>
                COURSE
              </span>

              <strong>
                118°
              </strong>

              <small>
                34° deviation from expected route
              </small>

            </div>


            <div className="behavior-param">

              <span>
                PROXIMITY TO ORIGIN
              </span>

              <strong>
                2.4 km
              </strong>

              <small>
                Closest recorded approach
              </small>

            </div>


            <div className="behavior-param">

              <span>
                AIS GAP
              </span>

              <strong>
                18 min
              </strong>

              <small>
                Signal unavailable during investigation window
              </small>

            </div>


            <div className="behavior-confidence">

              <div>

                <span>
                  BEHAVIOR ANOMALY
                </span>

                <strong>
                  HIGH
                </strong>

              </div>

              <div className="behavior-confidence-bar">
                <div></div>
              </div>

              <small>
                3 significant movement indicators detected
              </small>

            </div>

          </aside>

        </section>


        {/* =========================================
            ANOMALIES
            ========================================= */}

        <section className="behavior-anomalies">

          <div className="behavior-section-heading">

            <div>

              <span>
                03
              </span>

              <div>

                <h2>
                  Behavior Anomalies
                </h2>

                <p>
                  Detected deviations within the investigation window
                </p>

              </div>

            </div>

            <small>
              3 FLAGS
            </small>

          </div>


          <div className="anomaly-grid">


            {/* AIS GAP */}

            <div className="anomaly-card danger">

              <div className="anomaly-number">
                01
              </div>

              <div className="anomaly-content">

                <span>
                  AIS SIGNAL
                </span>

                <h3>
                  AIS Gap
                </h3>

                <strong>
                  18 min
                </strong>

                <p>
                  Vessel transmission was unavailable during a portion of
                  the suspected release window.
                </p>

              </div>

              <div className="anomaly-status">
                FLAGGED
              </div>

            </div>


            {/* COURSE */}

            <div className="anomaly-card warning">

              <div className="anomaly-number">
                02
              </div>

              <div className="anomaly-content">

                <span>
                  NAVIGATION
                </span>

                <h3>
                  Course Deviation
                </h3>

                <strong>
                  34°
                </strong>

                <p>
                  Recorded heading deviated from the expected transit
                  corridor near the estimated spill origin.
                </p>

              </div>

              <div className="anomaly-status">
                FLAGGED
              </div>

            </div>


            {/* SPEED */}

            <div className="anomaly-card warning">

              <div className="anomaly-number">
                03
              </div>

              <div className="anomaly-content">

                <span>
                  MOVEMENT
                </span>

                <h3>
                  Speed Anomaly
                </h3>

                <strong>
                  11.8 kn
                </strong>

                <p>
                  Vessel speed increased above the expected range during
                  the analyzed movement window.
                </p>

              </div>

              <div className="anomaly-status">
                FLAGGED
              </div>

            </div>

          </div>

        </section>


        {/* =========================================
            TIMELINE
            ========================================= */}

        <section className="behavior-timeline">

          <div className="behavior-section-heading">

            <div>

              <span>
                04
              </span>

              <div>

                <h2>
                  Movement Timeline
                </h2>

                <p>
                  AIS events surrounding the suspected release window
                </p>

              </div>

            </div>

            <small>
              UTC
            </small>

          </div>


          <div className="movement-events">

            <div className="movement-event">

              <span>
                12:36
              </span>

              <div className="movement-event-dot normal"></div>

              <div>
                <strong>
                  Normal transit
                </strong>

                <small>
                  Vessel following expected route
                </small>
              </div>

            </div>


            <div className="movement-event">

              <span>
                13:02
              </span>

              <div className="movement-event-dot warning"></div>

              <div>
                <strong>
                  Course deviation
                </strong>

                <small>
                  Heading changed by 34°
                </small>
              </div>

            </div>


            <div className="movement-event">

              <span>
                13:17
              </span>

              <div className="movement-event-dot danger"></div>

              <div>
                <strong>
                  AIS signal lost
                </strong>

                <small>
                  Transmission unavailable for 18 minutes
                </small>
              </div>

            </div>


            <div className="movement-event">

              <span>
                13:35
              </span>

              <div className="movement-event-dot danger"></div>

              <div>
                <strong>
                  AIS signal restored
                </strong>

                <small>
                  Vessel resumed transmission
                </small>
              </div>

            </div>


            <div className="movement-event">

              <span>
                13:49
              </span>

              <div className="movement-event-dot warning"></div>

              <div>
                <strong>
                  Speed anomaly
                </strong>

                <small>
                  Speed reached 11.8 knots
                </small>
              </div>

            </div>

          </div>

        </section>


        {/* =========================================
            FOOTER SUMMARY
            ========================================= */}

        <section className="behavior-footer">

          <div>

            <span>
              VESSEL
            </span>

            <strong>
              Tanker A
            </strong>

          </div>

          <div>

            <span>
              ANOMALIES
            </span>

            <strong>
              3
            </strong>

          </div>

          <div>

            <span>
              AIS COVERAGE
            </span>

            <strong>
              94%
            </strong>

          </div>

          <div>

            <span>
              PRIORITY
            </span>

            <strong className="high-priority">
              HIGH
            </strong>

          </div>


          <button
            onClick={() => navigate("/environmental-impact")}
          >
  Continue to Environmental Impact
  <span>→</span>
</button>

        </section>

      </main>

    </div>
  );
}

export default VesselBehavior;