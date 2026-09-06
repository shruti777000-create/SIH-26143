import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../detection.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`detection-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="detection-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function DetectionImage({ segmented = false }) {
  return (
    <div className="detection-image-wrap">
      <img
        src="/sentinel1-raw.jpg"
        alt="Sentinel-1 SAR oil spill"
        className="detection-sar-image"
      />

      {segmented && (
        <svg
          className="segmentation-overlay"
          viewBox="0 0 3840 2943"
          preserveAspectRatio="none"
        >
          {/* Main detected slick */}
          <path
            className="spill-fill"
            d="
              M 1900 560
              C 1780 690, 1710 850, 1660 1010
              C 1610 1160, 1510 1280, 1430 1400
              C 1340 1530, 1320 1670, 1250 1810
              C 1170 1970, 1050 2080, 1010 2200
              C 990 2290, 1070 2380, 1190 2400
              C 1340 2420, 1440 2330, 1510 2220
              C 1600 2080, 1640 1910, 1740 1780
              C 1850 1630, 1950 1510, 2050 1360
              C 2150 1210, 2230 1050, 2200 910
              C 2170 760, 2070 630, 1900 560 Z
            "
          />

          {/* Secondary slick section */}
          <path
            className="spill-fill secondary"
            d="
              M 2230 690
              C 2360 730, 2490 800, 2580 900
              C 2660 990, 2690 1090, 2630 1170
              C 2560 1260, 2430 1260, 2320 1190
              C 2210 1120, 2160 1000, 2170 890
              C 2180 800, 2190 740, 2230 690 Z
            "
          />

          {/* Boundary */}
          <path
            className="spill-outline"
            d="
              M 1900 560
              C 1780 690, 1710 850, 1660 1010
              C 1610 1160, 1510 1280, 1430 1400
              C 1340 1530, 1320 1670, 1250 1810
              C 1170 1970, 1050 2080, 1010 2200
              C 990 2290, 1070 2380, 1190 2400
              C 1340 2420, 1440 2330, 1510 2220
              C 1600 2080, 1640 1910, 1740 1780
              C 1850 1630, 1950 1510, 2050 1360
              C 2150 1210, 2230 1050, 2200 910
              C 2170 760, 2070 630, 1900 560 Z
            "
          />
        </svg>
      )}

      <div className="image-corner-tag">
        {segmented ? "AI SEGMENTATION" : "SENTINEL-1 GRD"}
      </div>
    </div>
  );
}

export default function Detection() {
  const navigate = useNavigate();

  // --------------------------------------------------
  // FASTAPI DATA
  // --------------------------------------------------

  const [detectData, setDetectData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  // --------------------------------------------------
  // LOAD DETECTION DATA FROM FASTAPI
  // --------------------------------------------------

  useEffect(() => {
    async function loadDetection() {
      try {
        setLoading(true);
        setApiError("");

        const response = await fetch(
          "http://127.0.0.1:8000/api/detect"
        );

        if (!response.ok) {
          throw new Error("Detection API request failed");
        }

        const data = await response.json();

        setDetectData(data);
      } catch (error) {
        console.error("MARIS Detection API Error:", error);

        setApiError(
          "Unable to connect to MARIS FastAPI backend."
        );
      } finally {
        setLoading(false);
      }
    }

    loadDetection();
  }, []);

  // --------------------------------------------------
  // API VALUES
  // --------------------------------------------------

  const area = detectData?.area_km2 ?? "--";

  const length = detectData?.length_km ?? "--";

  const confidence =
    detectData?.confidence != null
      ? Math.round(detectData.confidence * 100)
      : "--";

  const sourceImage =
    detectData?.source_image ?? "Sentinel-1 GRD";

  const slickId =
    detectData?.slick_id ?? "SLICK-MARIS-001";

  const timestamp = detectData?.timestamp_utc
    ? new Date(detectData.timestamp_utc)
    : null;

  const formattedTimestamp = timestamp
    ? timestamp.toLocaleString("en-GB", {
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
      <div className="detection-page">

        <aside className="detection-sidebar">

          <div className="detection-brand">
            <div className="detection-brand-mark">M</div>
            <span>MARIS</span>
          </div>

          <div className="detection-sidebar-bottom">
            <div className="system-status">
              <span className="status-dot"></span>

              <div>
                <strong>Connecting...</strong>
                <small>MARIS intelligence services</small>
              </div>
            </div>
          </div>

        </aside>

        <main className="detection-main">

          <header className="detection-header">

            <div>
              <div className="detection-kicker">
                INVESTIGATION / DETECTION
              </div>

              <h1>Oil Spill Detection</h1>

              <p>
                Connecting to Sentinel-1 detection service...
              </p>
            </div>

          </header>

          <div
            style={{
              padding: "30px",
              color: "#23c0e5",
            }}
          >
            Loading detection results...
          </div>

        </main>
      </div>
    );
  }

  return (
    <div className="detection-page">

      {/* --------------------------------------------------
          SIDEBAR
      -------------------------------------------------- */}

      <aside className="detection-sidebar">

        <div className="detection-brand">
          <div className="detection-brand-mark">M</div>
          <span>MARIS</span>
        </div>

        <div className="detection-nav">

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
            onClick={() => navigate("/forecast")}
          />

          <SidebarItem
            icon="▤"
            label="Reports"
            onClick={() => navigate("/reports")}
          />

        </div>

        <div className="detection-sidebar-bottom">

          <div className="system-status">

            <span className="status-dot"></span>

            <div>
              <strong>System Online</strong>
              <small>All services operational</small>
            </div>

          </div>

          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />

        </div>

      </aside>

      {/* --------------------------------------------------
          MAIN
      -------------------------------------------------- */}

      <main className="detection-main">

        <header className="detection-header">

          <div>

            <div className="detection-kicker">
              INVESTIGATION / DETECTION
            </div>

            <h1>Oil Spill Detection</h1>

            <p>
              Sentinel-1 SAR analysis and AI-based slick segmentation
            </p>

          </div>

          <div className="detection-header-right">

            <div className="source-status">

              <span className="status-dot"></span>

              {apiError
                ? "API CONNECTION ERROR"
                : "PROCESSING COMPLETE"}

            </div>

            <div className="timestamp">
              {formattedTimestamp}
            </div>

          </div>

        </header>

        {/* --------------------------------------------------
            API ERROR
        -------------------------------------------------- */}

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

        {/* --------------------------------------------------
            DETECTION COMPARISON
        -------------------------------------------------- */}

        <section className="detection-grid">

          {/* RAW SAR */}

          <div className="sar-panel">

            <div className="panel-heading">

              <div>

                <span className="panel-number">
                  01
                </span>

                <div>

                  <h2>
                    Raw Sentinel-1 SAR
                  </h2>

                  <p>
                    Original radar acquisition
                  </p>

                </div>

              </div>

              <span className="panel-label">
                SOURCE
              </span>

            </div>

            <DetectionImage />

          </div>

          {/* AI SEGMENTATION */}

          <div className="sar-panel">

            <div className="panel-heading">

              <div>

                <span className="panel-number">
                  02
                </span>

                <div>

                  <h2>
                    AI Detection (Segmentation)
                  </h2>

                  <p>
                    U-Net predicted oil slick
                  </p>

                </div>

              </div>

              <span className="panel-label detected">
                DETECTED
              </span>

            </div>

            <DetectionImage segmented />

          </div>

          {/* --------------------------------------------------
              GEOMETRY
          -------------------------------------------------- */}

          <div className="geometry-panel">

            <div className="panel-heading geometry-heading">

              <div>

                <span className="panel-number">
                  03
                </span>

                <div>

                  <h2>
                    Geometric Properties
                  </h2>

                  <p>
                    Detected slick characteristics
                  </p>

                </div>

              </div>

            </div>

            <div className="geometry-list">

              <div className="geometry-row">
                <span>Area</span>

                <strong>
                  {area}
                  <small> km²</small>
                </strong>
              </div>

              <div className="geometry-row">
                <span>Perimeter</span>

                <strong>
                  48.7
                  <small> km</small>
                </strong>
              </div>

              <div className="geometry-row">
                <span>Length</span>

                <strong>
                  {length}
                  <small> km</small>
                </strong>
              </div>

              <div className="geometry-row">
                <span>Width (Max)</span>

                <strong>
                  2.1
                  <small> km</small>
                </strong>
              </div>

              <div className="geometry-row">
                <span>Estimated Age</span>

                <strong>
                  5.2
                  <small> hrs</small>
                </strong>
              </div>

            </div>

            {/* CONFIDENCE */}

            <div className="confidence-block">

              <div className="confidence-top">

                <span>
                  Detection Confidence
                </span>

                <strong>
                  {confidence}%
                </strong>

              </div>

              <div className="confidence-track">

                <div
                  className="confidence-fill"
                  style={{
                    width:
                      confidence !== "--"
                        ? `${confidence}%`
                        : "0%",
                  }}
                />

              </div>

              <div className="confidence-scale">

                <span>0</span>
                <span>50</span>
                <span>100</span>

              </div>

            </div>

            {/* CLASSIFICATION */}

            <div className="classification">

              <span>
                CLASSIFICATION
              </span>

              <strong>
                {confidence !== "--" &&
                confidence >= 80
                  ? "HIGH CONFIDENCE OIL SLICK"
                  : "OIL SLICK DETECTED"}
              </strong>

            </div>

          </div>

        </section>

        {/* --------------------------------------------------
            RESULTS
        -------------------------------------------------- */}

        <section className="results-section">

          <div className="results-heading">

            <div>

              <span className="section-index">
                04
              </span>

              <div>

                <h2>
                  Detection Results &amp; Statistics
                </h2>

                <p>
                  Automated analysis summary
                </p>

              </div>

            </div>

            <span className="results-id">
              {slickId}
            </span>

          </div>

          <div className="stats-grid">

            {/* AREA */}

            <div className="stat-card">

              <span>
                DETECTED AREA
              </span>

              <strong>
                {area}
              </strong>

              <small>
                km²
              </small>

            </div>

            {/* CONFIDENCE */}

            <div className="stat-card">

              <span>
                CONFIDENCE
              </span>

              <strong>
                {confidence}
              </strong>

              <small>
                %
              </small>

            </div>

            {/* AGE */}

            <div className="stat-card">

              <span>
                ESTIMATED AGE
              </span>

              <strong>
                5.2
              </strong>

              <small>
                hours
              </small>

            </div>

            {/* SOURCE */}

            <div className="stat-card">

              <span>
                SOURCE
              </span>

              <strong className="text-stat">
                S1 GRD
              </strong>

              <small>
                {sourceImage}
              </small>

            </div>

          </div>

          {/* --------------------------------------------------
              FOOTER
          -------------------------------------------------- */}

          <div className="analysis-footer">

            <div>

              <span className="footer-label">
                PROCESSING
              </span>

              <strong>
                U-Net segmentation · Geometry extraction
              </strong>

            </div>

            <div>

              <span className="footer-label">
                STATUS
              </span>

              <strong className="success-text">
                ✓ Detection verified
              </strong>

            </div>

            <button
              className="continue-button"
              onClick={() => navigate("/forecast")}
            >
              Continue to Drift Forecast
              <span>→</span>
            </button>

          </div>

        </section>

      </main>

    </div>
  );
}