import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../vessels.css";

function SidebarItem({ icon, label, active, onClick }) {
  return (
    <button
      className={`vessel-sidebar-item ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="vessel-sidebar-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

// Convert official Contract C vessel data into the format used by the UI
function normalizeVessel(vessel, index) {
  const rawScore = Number(vessel.composite_threat_score ?? vessel.score ?? 0);
  const score = rawScore <= 1 ? Math.round(rawScore * 100) : Math.round(rawScore);

  const status =
    vessel.threat_level ??
    (score >= 80 ? "HIGH" : score >= 60 ? "MEDIUM" : "LOW");

  const metadata = vessel.vessel_metadata || {};
  const name =
    vessel.vessel_name ??
    metadata.vessel_name ??
    `MMSI ${vessel.mmsi ?? "--"}`;

  const mmsi = vessel.mmsi ?? "--";

  const type =
    vessel.vessel_type ??
    metadata.vessel_type ??
    "Vessel";

  const encounter = vessel.closest_encounter || {};
  const proximity =
    encounter.min_distance_to_origin_km != null
      ? `${encounter.min_distance_to_origin_km.toFixed(1)} km`
      : vessel.proximity_km != null
      ? `${vessel.proximity_km} km`
      : "--";

  const flags =
    Array.isArray(vessel.anomaly_indicators)
      ? vessel.anomaly_indicators
      : Array.isArray(vessel.anomaly_flags)
      ? vessel.anomaly_flags
      : [];

  const evidencePkg = vessel.evidence_package || {};
  const evidence =
    evidencePkg.summary ??
    vessel.evidence_text ??
    "No evidence text available from the attribution service.";

  const recommendation = evidencePkg.recommended_action ?? "";

  return {
    rank: String(vessel.rank ?? (index + 1)).padStart(2, "0"),
    name,
    mmsi,
    type,
    score,
    proximity,
    status,
    flags,
    evidence,
    recommendation,
    cpaPoint: encounter.vessel_point_at_cpa,
    trajectory: vessel.trajectory_geojson,
  };
}

function Vessels() {
  const navigate = useNavigate();

  const [vessels, setVessels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  // ==================================================
  // PIPELINE ATTRIBUTION /api/pipeline
  // ==================================================

  useEffect(() => {
    async function loadAttribution() {
      try {
        setLoading(true);
        setApiError("");

        const response = await fetch("/api/pipeline?demo=true", {
          method: "POST",
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || `Attribution API request failed (${response.status})`);
        }

        const data = await response.json();
        const contractC = data.contract_c ?? data;

        // Use official Contract C ranked_suspects
        const suspects = Array.isArray(contractC.ranked_suspects)
          ? contractC.ranked_suspects
          : Array.isArray(contractC.suspects)
          ? contractC.suspects
          : [];

        const normalized = suspects.map((vessel, index) =>
          normalizeVessel(vessel, index)
        );

        setVessels(normalized);

      } catch (error) {
        console.error(
          "MARIS Attribution API Error:",
          error
        );

        setApiError(
          error.message || "Unable to connect to MARIS FastAPI attribution service."
        );
      } finally {
        setLoading(false);
      }
    }

    loadAttribution();
  }, []);

  // ==================================================
  // TOP VESSEL
  // ==================================================

  const topVessel = vessels[0];

  // ==================================================
  // LOADING
  // ==================================================

  if (loading) {
    return (
      <div className="vessel-page">

        <aside className="vessel-sidebar">

          <div className="vessel-brand">

            <div className="vessel-brand-mark">
              M
            </div>

            <div>
              <div className="vessel-brand-name">
                MARIS
              </div>

              <div className="vessel-brand-subtitle">
                Maritime Oil Spill Intelligence
              </div>
            </div>

          </div>

          <div className="vessel-system">

            <span className="vessel-status-dot"></span>

            <div>
              <strong>Connecting...</strong>
              <small>AIS attribution service</small>
            </div>

          </div>

        </aside>

        <main className="vessel-main">

          <header className="vessel-header">

            <div>

              <div className="vessel-kicker">
                INVESTIGATION / AIS / ATTRIBUTION
              </div>

              <h1>
                Vessel Ranking
              </h1>

              <p>
                Connecting to MARIS vessel attribution service...
              </p>

            </div>

          </header>

          <div
            style={{
              padding: "30px",
              color: "#23c0e5",
            }}
          >
            Loading vessel attribution data...
          </div>

        </main>

      </div>
    );
  }

  // ==================================================
  // MAIN PAGE
  // ==================================================

  return (
    <div className="vessel-page">

      {/* ==================================================
          SIDEBAR
      ================================================== */}

      <aside className="vessel-sidebar">

        <div className="vessel-brand">

          <div className="vessel-brand-mark">
            M
          </div>

          <div>

            <div className="vessel-brand-name">
              MARIS
            </div>

            <div className="vessel-brand-subtitle">
              Maritime Oil Spill Intelligence
            </div>

          </div>

        </div>

        <div className="vessel-nav">

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

        </div>

        <div className="vessel-system">

          <span className="vessel-status-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>AIS analysis ready</small>
          </div>

        </div>

      </aside>

      {/* ==================================================
          MAIN
      ================================================== */}

      <main className="vessel-main">

        {/* HEADER */}

        <header className="vessel-header">

          <div>

            <div className="vessel-kicker">
              INVESTIGATION / AIS / ATTRIBUTION
            </div>

            <h1>
              Vessel Ranking
            </h1>

            <p>
              AIS-based vessel analysis and suspected spill-source attribution
            </p>

          </div>

          <div className="vessel-header-right">

            <div className="vessel-live">

              <span></span>

              {apiError
                ? "API ERROR"
                : "AIS ANALYSIS COMPLETE"}

            </div>

            <div className="vessel-time">
              MARIS ATTRIBUTION SERVICE
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
            TOP SUSPECT
        ================================================== */}

        {topVessel && (
          <section className="top-suspect">

            <div className="suspect-heading">

              <div>

                <span>01</span>

                <div>

                  <h2>
                    Top Suspect
                  </h2>

                  <p>
                    Highest correlation with spill origin
                  </p>

                </div>

              </div>

              <div className="preliminary">
                PRELIMINARY
              </div>

            </div>

            <div className="suspect-main">

              <div className="suspect-vessel">

                <div className="vessel-rank">
                  {topVessel.rank}
                </div>

                <div>

                  <span className="vessel-type">
                    {topVessel.type}
                  </span>

                  <h3>
                    {topVessel.name}
                  </h3>

                  <span className="vessel-mmsi">
                    MMSI {topVessel.mmsi}
                  </span>

                </div>

              </div>

              <div className="suspect-distance">

                <span>
                  PROXIMITY TO ORIGIN
                </span>

                <strong>
                  {topVessel.proximity}
                </strong>

              </div>

              <div className="suspect-score-large">

                <span>
                  ATTRIBUTION SCORE
                </span>

                <div>

                  <strong>
                    {topVessel.score}
                  </strong>

                  <small>
                    /100
                  </small>

                </div>

              </div>

            </div>

            <div className="score-bar">

              <div
                style={{
                  width: `${topVessel.score}%`,
                }}
              ></div>

            </div>

          </section>
        )}

        {/* ==================================================
            RANKING + EVIDENCE
        ================================================== */}

        <section className="vessel-content">

          {/* RANKING */}

          <div className="ranking-panel">

            <div className="section-heading">

              <div>

                <span>
                  02
                </span>

                <div>

                  <h2>
                    Vessel Ranking
                  </h2>

                  <p>
                    Ranked by attribution likelihood
                  </p>

                </div>

              </div>

              <small>
                {vessels.length} TRACKS
              </small>

            </div>

            <div className="ranking-table">

              <div className="table-header">

                <span>RANK</span>
                <span>VESSEL</span>
                <span>PROXIMITY</span>
                <span>SCORE</span>
                <span>STATUS</span>

              </div>

              {vessels.map((vessel) => (

                <div
                  className={`ranking-row ${
                    vessel.rank === "01"
                      ? "top-row"
                      : ""
                  }`}
                  key={vessel.mmsi}
                >

                  <span className="rank-number">
                    {vessel.rank}
                  </span>

                  <div className="ranking-vessel">

                    <strong>
                      {vessel.name}
                    </strong>

                    <small>
                      {vessel.type}
                    </small>

                  </div>

                  <span className="proximity">
                    {vessel.proximity}
                  </span>

                  <div className="ranking-score">

                    <strong>
                      {vessel.score}
                    </strong>

                    <div className="mini-score">

                      <div
                        style={{
                          width: `${vessel.score}%`,
                        }}
                      ></div>

                    </div>

                  </div>

                  <span
                    className={`risk-status ${vessel.status.toLowerCase()}`}
                  >
                    {vessel.status}
                  </span>

                </div>

              ))}

            </div>

          </div>

          {/* ==================================================
              EVIDENCE
          ================================================== */}

          {topVessel && (
            <aside className="evidence-panel">

              <div className="section-heading">

                <div>

                  <span>
                    03
                  </span>

                  <div>

                    <h2>
                      Attribution Evidence
                    </h2>

                    <p>
                      AIS behavior indicators
                    </p>

                  </div>

                </div>

              </div>

              <div className="evidence-vessel">

                <span>
                  SELECTED VESSEL
                </span>

                <strong>
                  {topVessel.name}
                </strong>

                <small>
                  MMSI {topVessel.mmsi}
                </small>

              </div>

              <div className="evidence-flags">

                {topVessel.flags.map((flag) => (

                  <div
                    className="evidence-flag"
                    key={flag}
                  >

                    <span>
                      !
                    </span>

                    {flag}

                  </div>

                ))}

              </div>

              <div className="evidence-text">

                <span>
                  ANALYSIS
                </span>

                <p>
                  {topVessel.evidence}
                </p>

              </div>

              <div className="evidence-metrics">

                <div>

                  <span>
                    ORIGIN DISTANCE
                  </span>

                  <strong>
                    {topVessel.proximity}
                  </strong>

                </div>

                <div>

                  <span>
                    ATTRIBUTION SCORE
                  </span>

                  <strong>
                    {topVessel.score}%
                  </strong>

                </div>

              </div>

            </aside>
          )}

        </section>

        {/* ==================================================
            BOTTOM
        ================================================== */}

        <section className="vessel-summary">

          <div>

            <span>
              ANALYSIS WINDOW
            </span>

            <strong>
              AIS INVESTIGATION
            </strong>

          </div>

          <div>

            <span>
              VESSELS ANALYZED
            </span>

            <strong>
              {vessels.length}
            </strong>

          </div>

          <div>

            <span>
              HIGH PRIORITY
            </span>

            <strong>
              {vessels.filter(
                (vessel) => vessel.status === "HIGH"
              ).length} vessel
              {vessels.filter(
                (vessel) => vessel.status === "HIGH"
              ).length === 1
                ? ""
                : "s"}
            </strong>

          </div>

          <div>

            <span>
              MODEL
            </span>

            <strong>
              AIS anomaly + proximity
            </strong>

          </div>

          <button
            onClick={() => navigate("/vessel-behavior")}
          >

            Continue to Vessel Behavior

            <span>
              →
            </span>

          </button>

        </section>

      </main>

    </div>
  );
}

export default Vessels;