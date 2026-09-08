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

function DetectionImage({ segmented = false, scenario = "oil" }) {
  const imageSrc =
    scenario === "oil"
      ? "/sentinel1-00204.jpg"
      : scenario === "no_oil"
      ? "/sentinel1-no-oil.jpg"
      : "/sentinel1-lookalike.jpg";

  return (
    <div className="detection-image-wrap">
      <img
        src={imageSrc}
        alt={`Sentinel-1 SAR ${scenario}`}
        className="detection-sar-image"
      />

      {segmented && scenario === "oil" && (
        <div className="real-mask-overlay">
          <img
            src="http://127.0.0.1:8000/api/detect/segmentation-overlay"
            alt="U-Net oil spill segmentation"
          />
        </div>
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
  const [scenario, setScenario] = useState("oil");
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

        const response = await fetch(`http://127.0.0.1:8000/api/detect?scenario=${scenario}`)

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
  }, [scenario]);

  // --------------------------------------------------
  // API VALUES
  // --------------------------------------------------

  const area = detectData?.area_km2 ?? "--";

  const length = detectData?.perimeter_km ?? "--";

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
       <div
  style={{
    display: "flex",
    gap: "10px",
    marginBottom: "18px",
  }}
>
    <button onClick={() => setScenario("oil")}>
      Oil Spill
    </button>

    <button onClick={() => setScenario("no_oil")}>
      No Oil
    </button>

    <button onClick={() => setScenario("lookalike")}>
      Lookalike
    </button>
  </div>

  

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

            <DetectionImage scenario={scenario} />

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
  {detectData?.detected
    ? "U-Net predicted oil slick"
    : scenario === "lookalike"
      ? "SAR pattern classified as lookalike"
      : "No oil slick detected"}
</p>

                </div>

              </div>

              <span className={`panel-label ${detectData?.detected ? "detected" : ""}`}>
  {detectData?.detected ? "DETECTED" : "NOT DETECTED"}
</span>

            </div>

           <DetectionImage
  segmented={detectData?.detected === true}
  scenario={scenario}
/>

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
                  {detectData?.perimeter_km?.toFixed(2) ?? "—"}
                  <small> km</small>
                </strong>
              </div>

              <div className="geometry-row">
                <span>Length</span>

                <strong>
                  
                  Not calculated
                  
                </strong>
              </div>

              <div className="geometry-row">
                <span>Width (Max)</span>

                <strong>
  {detectData?.detected ? "2.1" : "0"}
  <small> km</small>
</strong>
              </div>

              <div className="geometry-row">
                <span>Estimated Age</span>

                <strong>
  {detectData?.detected ? "5.2" : "—"}
  {detectData?.detected && <small> hrs</small>}
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
  {detectData?.detected
    ? confidence >= 80
      ? "HIGH CONFIDENCE OIL SLICK"
      : "OIL SLICK DETECTED"
    : "NO OIL SPILL DETECTED"}
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