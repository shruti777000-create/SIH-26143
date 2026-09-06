import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../incident-report.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`report-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="report-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function IncidentReport() {
  const navigate = useNavigate();

  const [detect, setDetect] = useState(null);
  const [drift, setDrift] = useState(null);
  const [attribute, setAttribute] = useState(null);
  function downloadGeoJSON() {
    if (!detection?.geometry) {
      alert("No spill geometry available.");
      return;
    }

    const geometry =
      detection.geometry.type === "Feature"
        ? detection.geometry.geometry
        : detection.geometry;

    const geojson = {
      type: "Feature",
      properties: {
        slick_id: detection.slick_id,
        timestamp_utc: detection.timestamp_utc,
        area_km2: detection.area_km2,
        length_km: detection.length_km,
        confidence: detection.confidence,
        source_image: detection.source_image,
      },
      geometry,
    };

    const blob = new Blob(
      [JSON.stringify(geojson, null, 2)],
      { type: "application/geo+json" }
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `${detection.slick_id || "maris-spill"}.geojson`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  }

  function downloadCSV() {
    const vesselList = Array.isArray(attribute)
      ? attribute
      : attribute?.suspects ?? [];

    if (vesselList.length === 0) {
      alert("No vessel attribution data available.");
      return;
    }

    const headers = [
      "Rank",
      "Vessel Name",
      "MMSI",
      "Score",
      "Proximity (km)",
      "Anomaly Flags",
      "Evidence",
    ];

    const rows = vesselList.map((vessel, index) => {
      let score = Number(vessel.score ?? 0);

      if (score > 0 && score <= 1) {
        score = score * 100;
      }

      return [
        index + 1,
        vessel.vessel_name ?? vessel.name ?? "",
        vessel.mmsi ?? "",
        Math.round(score),
        vessel.proximity_km ?? "",
        Array.isArray(vessel.anomaly_flags)
          ? vessel.anomaly_flags.join("; ")
          : vessel.anomaly_flags ?? "",
        vessel.evidence_text ?? "",
      ];
    });

    const csvEscape = (value) => {
      const text = String(value ?? "");
      return `"${text.replace(/"/g, '""')}"`;
    };

    const csv = [
      headers.map(csvEscape).join(","),
      ...rows.map((row) => row.map(csvEscape).join(",")),
    ].join("\n");

    const blob = new Blob(
      [csv],
      { type: "text/csv;charset=utf-8;" }
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `${detection?.slick_id || "maris-vessels"}.csv`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  }

  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  // =========================================================
  // LOAD ALL MARIS INTELLIGENCE
  // =========================================================

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
          throw new Error("One or more MARIS APIs failed");
        }

        const detectData = await detectResponse.json();
        const driftData = await driftResponse.json();
        const attributeData = await attributeResponse.json();

        setDetect(detectData);
        setDrift(driftData);
        setAttribute(attributeData);
      } catch (error) {
        console.error("MARIS Report API Error:", error);

        setApiError(
          "Unable to load investigation data from the MARIS FastAPI service."
        );
      } finally {
        setLoading(false);
      }
    }

    loadInvestigationData();
  }, []);

  // =========================================================
  // NORMALIZE DETECTION DATA
  // =========================================================

  const detection = Array.isArray(detect)
    ? detect[0] ?? {}
    : detect ?? {};

  const spillArea =
    detection.area_km2 ?? 12.4;

  const spillLength =
    detection.length_km ?? 21.3;

  const detectionConfidenceRaw =
    Number(detection.confidence ?? 0.91);

  const detectionConfidence =
    detectionConfidenceRaw <= 1
      ? Math.round(detectionConfidenceRaw * 100)
      : Math.round(detectionConfidenceRaw);

  const incidentId =
    detection.slick_id ?? "SLICK-MARIS-001";

  const detectionTime =
    detection.timestamp_utc ?? "19 MAR 2019 · 18:11 UTC";

  const sourceImage =
    detection.source_image ?? "Sentinel-1 GRD";

  // =========================================================
  // NORMALIZE DRIFT DATA
  // =========================================================

  const driftData = drift ?? {};

  const estimatedOrigin =
    driftData.estimated_origin ?? {};

  const originCoordinates =
    estimatedOrigin.coordinates ??
    driftData.origin_coordinates ??
    [13.08, 80.27];

  const originLat =
    Array.isArray(originCoordinates)
      ? originCoordinates[1] ?? 13.08
      : estimatedOrigin.lat ?? 13.08;

  const originLng =
    Array.isArray(originCoordinates)
      ? originCoordinates[0] ?? 80.27
      : estimatedOrigin.lng ?? 80.27;

  const displacement =
    driftData.expected_displacement_km ??
    driftData.displacement_km ??
    18.7;

  const forecastConfidenceRaw =
    Number(driftData.forecast_confidence ?? 0.78);

  const forecastConfidence =
    forecastConfidenceRaw <= 1
      ? Math.round(forecastConfidenceRaw * 100)
      : Math.round(forecastConfidenceRaw);

  // =========================================================
  // NORMALIZE ATTRIBUTION DATA
  // =========================================================

  const suspects = Array.isArray(attribute)
    ? attribute
    : attribute?.suspects ?? [];

  const sortedSuspects = [...suspects].sort(
    (a, b) =>
      Number(b.score ?? 0) -
      Number(a.score ?? 0)
  );

  const topSuspect =
    sortedSuspects[0] ?? {};

  let suspectScore =
    Number(topSuspect.score ?? 0);

  if (suspectScore > 0 && suspectScore <= 1) {
    suspectScore *= 100;
  }

  suspectScore = Math.round(suspectScore);

  const suspectName =
    topSuspect.vessel_name ??
    topSuspect.name ??
    "Unknown Vessel";

  const suspectMmsi =
    topSuspect.mmsi ??
    "--";

  const suspectType =
    topSuspect.vessel_type ??
    topSuspect.type ??
    "Vessel";

  const suspectProximity =
    topSuspect.proximity_km ??
    "--";

  const anomalyFlags =
    Array.isArray(topSuspect.anomaly_flags)
      ? topSuspect.anomaly_flags
      : [];

  const evidenceText =
    topSuspect.evidence_text ??
    "No additional attribution evidence available.";

  // =========================================================
  // LOADING SCREEN
  // =========================================================

  if (loading) {
    return (
      <div className="report-page">

        <main
          className="report-main"
          style={{
            marginLeft: 0,
            width: "100%",
          }}
        >
          <div
            style={{
              padding: "80px",
              color: "#22bfdc",
              fontSize: "14px",
            }}
          >
            Loading MARIS investigation report...
          </div>
        </main>

      </div>
    );
  }

  return (
    <div className="report-page">

      {/* =====================================================
          SIDEBAR
          ===================================================== */}

      <aside className="report-sidebar">

        <div className="report-brand">

          <div className="report-brand-mark">
            M
          </div>

          <div>
            <div className="report-brand-name">
              MARIS
            </div>

            <div className="report-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>
          </div>

        </div>

        <div className="report-nav">

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
            active
            onClick={() => navigate("/reports")}
          />

          <SidebarItem
            icon="⚙"
            label="Settings"
            onClick={() => navigate("/settings")}
          />

        </div>

        <div className="report-system">

          <span className="report-system-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>Report generation ready</small>
          </div>

        </div>

      </aside>

      {/* =====================================================
          MAIN
          ===================================================== */}

      <main className="report-main">

        {/* HEADER */}

        <header className="report-header">

          <div>

            <div className="report-kicker">
              MARIS / INVESTIGATION / INCIDENT REPORT
            </div>

            <h1>
              Incident Report
            </h1>

            <p>
              Consolidated intelligence report for detected maritime oil spill
            </p>

          </div>

          <div className="report-header-right">

            <div className="report-status">

              <span></span>

              {apiError
                ? "API WARNING"
                : "REPORT READY"}

            </div>

            <div className="report-time">
              {detectionTime}
            </div>

          </div>

        </header>

        {/* API WARNING */}

        {apiError && (
          <div
            style={{
              marginBottom: "16px",
              padding: "12px 16px",
              border: "1px solid #6b3030",
              background: "#201416",
              color: "#ff7777",
              fontSize: "12px",
            }}
          >
            {apiError}
          </div>
        )}

        {/* =====================================================
            01 INCIDENT IDENTIFICATION
            ===================================================== */}

        <section className="report-identity">

          <div className="report-section-title">

            <span>01</span>

            <div>
              <h2>Incident Identification</h2>
              <p>Primary event information</p>
            </div>

          </div>

          <div className="report-identity-grid">

            <div>
              <span>INCIDENT ID</span>
              <strong>{incidentId}</strong>
            </div>

            <div>
              <span>DETECTION TIME</span>
              <strong>{detectionTime}</strong>
            </div>

            <div>
              <span>LOCATION</span>
              <strong>
                {Number(originLat).toFixed(2)}° N ·{" "}
                {Number(originLng).toFixed(2)}° E
              </strong>
            </div>

            <div>
              <span>DATA SOURCE</span>
              <strong>{sourceImage}</strong>
            </div>

          </div>

        </section>

        {/* =====================================================
            02 DETECTION SUMMARY
            ===================================================== */}

        <section className="report-detection">

          <div className="report-section-title">

            <span>02</span>

            <div>
              <h2>Detection Summary</h2>
              <p>Automated satellite-based spill analysis</p>
            </div>

          </div>

          <div className="report-stat-grid">

            <div className="report-stat">

              <span>SPILL AREA</span>

              <strong>
                {spillArea} <small>km²</small>
              </strong>

              <p>
                Detected slick extent
              </p>

            </div>

            <div className="report-stat">

              <span>PERIMETER</span>

              <strong>
                {detection.perimeter_km ?? 48.7}{" "}
                <small>km</small>
              </strong>

              <p>
                Estimated slick perimeter
              </p>

            </div>

            <div className="report-stat">

              <span>ESTIMATED LENGTH</span>

              <strong>
                {spillLength} <small>km</small>
              </strong>

              <p>
                Maximum longitudinal extent
              </p>

            </div>

            <div className="report-stat">

              <span>ESTIMATED AGE</span>

              <strong>
                {detection.estimated_age_hours ?? 5.2}{" "}
                <small>hrs</small>
              </strong>

              <p>
                Estimated from origin analysis
              </p>

            </div>

          </div>

          <div className="report-confidence">

            <div className="report-confidence-head">

              <div>

                <span>DETECTION CONFIDENCE</span>

                <strong>
                  {detectionConfidence}%
                </strong>

              </div>

              <small>
                {detectionConfidence >= 80
                  ? "HIGH CONFIDENCE"
                  : "MODERATE CONFIDENCE"}
              </small>

            </div>

            <div className="report-confidence-track">

              <div
                style={{
                  width: `${detectionConfidence}%`,
                }}
              />

            </div>

          </div>

        </section>

        {/* =====================================================
            03 INVESTIGATION FINDINGS
            ===================================================== */}

        <section className="report-findings">

          <div className="report-section-title">

            <span>03</span>

            <div>
              <h2>Investigation Findings</h2>
              <p>Drift, vessel and environmental intelligence</p>
            </div>

          </div>

          <div className="report-findings-grid">

            {/* DRIFT */}

            <div className="report-finding">

              <div className="finding-number">
                01
              </div>

              <span>
                DRIFT ANALYSIS
              </span>

              <h3>
                Origin & Movement
              </h3>

              <div className="finding-value">

                {displacement}

                <small>
                  km
                </small>

              </div>

              <p>
                Estimated displacement over the 24-hour
                forecast period based on ocean current
                and wind-driven transport.
              </p>

              <div className="finding-meta">

                <span>
                  MODEL
                </span>

                <strong>
                  {driftData.model ?? "OpenDrift"}
                </strong>

              </div>

            </div>

            {/* VESSEL */}

            <div className="report-finding">

              <div className="finding-number">
                02
              </div>

              <span>
                VESSEL ATTRIBUTION
              </span>

              <h3>
                Top Suspect
              </h3>

              <div className="finding-vessel">
                {suspectName}
              </div>

              <p>
                Highest correlation with the estimated spill
                origin and suspected release window.
              </p>

              <div className="finding-meta">

                <span>
                  ATTRIBUTION SCORE
                </span>

                <strong className="report-red">
                  {suspectScore} / 100
                </strong>

              </div>

            </div>

            {/* ENVIRONMENT */}

            <div className="report-finding">

              <div className="finding-number">
                03
              </div>

              <span>
                ENVIRONMENT
              </span>

              <h3>
                Impact Assessment
              </h3>

              <div className="finding-value">
                HIGH
              </div>

              <p>
                Modeled impact zone indicates significant
                marine exposure with potential coastal interaction.
              </p>

              <div className="finding-meta">

                <span>
                  IMPACT ZONE
                </span>

                <strong>
                  {driftData.impact_zone_km2 ?? 42.7} km²
                </strong>

              </div>

            </div>

          </div>

        </section>

        {/* =====================================================
            04 ATTRIBUTION EVIDENCE
            ===================================================== */}

        <section className="report-evidence">

          <div className="report-section-title">

            <span>04</span>

            <div>
              <h2>Attribution Evidence</h2>
              <p>Evidence supporting the leading vessel candidate</p>
            </div>

          </div>

          <div className="report-evidence-grid">

            <div className="evidence-vessel">

              <span>
                SELECTED VESSEL
              </span>

              <h3>
                {suspectName}
              </h3>

              <small>
                MMSI {suspectMmsi} · {suspectType}
              </small>

            </div>

            <div className="evidence-list">

              {anomalyFlags.length > 0 ? (
                anomalyFlags.map((flag, index) => (

                  <div
                    className="evidence-row"
                    key={`${flag}-${index}`}
                  >

                    <span className="evidence-icon">
                      !
                    </span>

                    <div>

                      <strong>
                        {String(flag)
                          .replaceAll("_", " ")
                          .replace(/\b\w/g, (char) =>
                            char.toUpperCase()
                          )}
                      </strong>

                      <p>
                        Detected by AIS behavior analysis
                        during the investigation window.
                      </p>

                    </div>

                  </div>

                ))
              ) : (

                <div className="evidence-row">

                  <span className="evidence-icon">
                    !
                  </span>

                  <div>

                    <strong>
                      Attribution Analysis
                    </strong>

                    <p>
                      {evidenceText}
                    </p>

                  </div>

                </div>

              )}

            </div>

            <div className="evidence-score">

              <span>
                ATTRIBUTION SCORE
              </span>

              <strong>
                {suspectScore}
              </strong>

              <small>
                / 100
              </small>

              <div className="evidence-score-bar">

                <div
                  style={{
                    width: `${suspectScore}%`,
                  }}
                />

              </div>

              <p>
                {suspectScore >= 80
                  ? "High correlation"
                  : suspectScore >= 60
                  ? "Moderate correlation"
                  : "Low correlation"}
              </p>

            </div>

          </div>

        </section>

        {/* =====================================================
            05 INVESTIGATION SUMMARY
            ===================================================== */}

        <section className="report-summary">

          <div className="report-section-title">

            <span>05</span>

            <div>
              <h2>Investigation Summary</h2>
              <p>Automated intelligence assessment</p>
            </div>

          </div>

          <div className="report-summary-content">

            <div className="report-summary-main">

              <span>
                CURRENT ASSESSMENT
              </span>

              <h3>
                High-confidence oil spill detected in the Bay of Bengal
              </h3>

              <p>
                Sentinel-1 SAR analysis identified a{" "}
                {spillArea} km² slick near the Chennai
                coastline. Hindcast analysis estimates the
                spill origin and subsequent movement, while
                AIS analysis identified{" "}
                <strong>{suspectName}</strong> as the
                leading vessel candidate.
              </p>

            </div>

            <div className="report-summary-side">

              <div>

                <span>
                  CONFIDENCE
                </span>

                <strong>
                  {detectionConfidence}%
                </strong>

              </div>

              <div>

                <span>
                  TOP SUSPECT
                </span>

                <strong>
                  {suspectName}
                </strong>

              </div>

              <div>

                <span>
                  PRIORITY
                </span>

                <strong className="report-red">
                  {suspectScore >= 80
                    ? "HIGH"
                    : "MEDIUM"}
                </strong>

              </div>

            </div>

          </div>

        </section>

        {/* =====================================================
            06 RECOMMENDED ACTIONS
            ===================================================== */}

        <section className="report-actions">

          <div className="report-section-title">

            <span>06</span>

            <div>
              <h2>Recommended Actions</h2>
              <p>Initial response recommendations</p>
            </div>

          </div>

          <div className="report-action-grid">

            <div className="report-action">

              <div>
                01
              </div>

              <strong>
                Continue satellite monitoring
              </strong>

              <p>
                Acquire additional SAR observations to track
                slick evolution.
              </p>

            </div>

            <div className="report-action">

              <div>
                02
              </div>

              <strong>
                Monitor predicted drift
              </strong>

              <p>
                Compare forecast movement against subsequent
                observations.
              </p>

            </div>

            <div className="report-action">

              <div>
                03
              </div>

              <strong>
                Investigate vessel activity
              </strong>

              <p>
                Review {suspectName}'s AIS history and
                movement during the release window.
              </p>

            </div>

            <div className="report-action">

              <div>
                04
              </div>

              <strong>
                Assess coastal exposure
              </strong>

              <p>
                Prioritize environmental monitoring within
                the modeled impact zone.
              </p>

            </div>

          </div>

        </section>

        {/* =====================================================
            EXPORT
            ===================================================== */}

        <section className="report-export">

          <div>

            <span>
              REPORT OUTPUT
            </span>

            <strong>
              {incidentId}
            </strong>

            <small>
              Generated from current investigation state
            </small>

          </div>

          <div className="report-export-buttons">

            <button
  onClick={() => window.print()}
>
  <span>↓</span>
  Download PDF
</button>

            <button onClick={downloadGeoJSON}>
  <span>↓</span>
  Download GeoJSON
</button>
            <button onClick={downloadCSV}>
  <span>▣</span>
  Export CSV
</button>
          </div>

        </section>

        {/* =====================================================
            FOOTER
            ===================================================== */}

        <footer className="report-footer">

          <div>

            <span>
              INCIDENT
            </span>

            <strong>
              {incidentId}
            </strong>

          </div>

          <div>

            <span>
              DATA SOURCE
            </span>

            <strong>
              {sourceImage}
            </strong>

          </div>

          <div>

            <span>
              ANALYSIS STATUS
            </span>

            <strong>
              COMPLETE
            </strong>

          </div>

          <button
            onClick={() => navigate("/")}
          >
            Return to Dashboard
            <span>→</span>
          </button>

        </footer>

      </main>

    </div>
  );
}

export default IncidentReport;