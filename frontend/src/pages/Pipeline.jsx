import { useNavigate } from "react-router-dom";
import "../pipeline.css";

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

const stages = [
  {
    number: "01",
    title: "SAR ACQUISITION",
    detail: "Sentinel-1 GRD",
  },
  {
    number: "02",
    title: "SPILL DETECTION",
    detail: "U-Net segmentation",
  },
  {
    number: "03",
    title: "HINDCASTING",
    detail: "Origin estimation",
  },
  {
    number: "04",
    title: "AIS ANALYSIS",
    detail: "18 vessel tracks",
  },
  {
    number: "05",
    title: "ATTRIBUTION",
    detail: "Suspect ranking",
  },
];

function Pipeline() {
  const navigate = useNavigate();

  return (
    <div className="pipeline-page">

      <aside className="pipeline-sidebar">

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

          <SidebarItem icon="⌂" label="Dashboard" onClick={() => navigate("/")} />
          <SidebarItem icon="▣" label="Incidents" onClick={() => navigate("/incidents")} />
          <SidebarItem icon="⌖" label="Map" onClick={() => navigate("/investigation")} />
          <SidebarItem icon="≋" label="Pipeline" active onClick={() => navigate("/pipeline")} />
          <SidebarItem icon="♙" label="Vessels" onClick={() => navigate("/vessels")} />
          <SidebarItem icon="◴" label="Forecast" onClick={() => navigate("/forecast")} />
          <SidebarItem icon="▤" label="Reports" onClick={() => navigate("/reports")} />
          <SidebarItem icon="!" label="Alerts" onClick={() => navigate("/alerts")} />

        </div>

        <div className="sidebar-bottom">
          <SidebarItem icon="⚙" label="Settings" onClick={() => navigate("/settings")} />
        </div>

      </aside>

      <main className="pipeline-main">

        <header className="pipeline-header">

          <div>
            <div className="page-kicker">
              MARIS / INTELLIGENCE / PIPELINE
            </div>

            <h1>AI Pipeline Visualization</h1>

            <p>
              Satellite detection → origin analysis → vessel attribution
            </p>
          </div>

          <div className="system-state">
            <span className="state-dot"></span>
            SYSTEM OPERATIONAL
          </div>

        </header>

        <section className="mission-view">

          <div className="mission-overlay"></div>
          <div className="scan-lines"></div>

          <div className="mission-top-left">
            <span>MISSION</span>
            <strong>MARIS-2026-0830</strong>
          </div>

          <div className="mission-top-right">
            <span>DATA SOURCE</span>
            <strong>SENTINEL-1 SAR</strong>
          </div>

          <div className="pipeline-center">

            <div className="pipeline-label">
              INTELLIGENCE PROCESSING CHAIN
            </div>

            <div className="stage-flow">

              {stages.map((stage, index) => (
                <div className="stage-unit" key={stage.number}>

                  <div className="stage-node">
                    {stage.number}
                  </div>

                  <div className="stage-text">
                    <strong>{stage.title}</strong>
                    <small>{stage.detail}</small>
                  </div>

                  {index < stages.length - 1 && (
                    <div className="stage-line"></div>
                  )}

                </div>
              ))}

            </div>

          </div>

          <div className="analysis-panel">

            <div className="panel-kicker">
              CURRENT ANALYSIS
            </div>

            <div className="analysis-title">
              OIL SPILL INCIDENT
            </div>

            <div className="analysis-grid">

              <div>
                <span>SPILL AREA</span>
                <strong>12.4 km²</strong>
              </div>

              <div>
                <span>CONFIDENCE</span>
                <strong>91%</strong>
              </div>

              <div>
                <span>ESTIMATED AGE</span>
                <strong>5.2 hrs</strong>
              </div>

              <div>
                <span>VESSELS</span>
                <strong>18</strong>
              </div>

            </div>

          </div>

          <div className="satellite-marker">

            <div className="marker-ring"></div>
            <div className="marker-center"></div>

            <div className="marker-label">
              <span>DETECTED REGION</span>
              <strong>OIL SLICK</strong>
            </div>

          </div>

          <div className="coordinates">
            13.08° N &nbsp; 80.27° E
          </div>

        </section>

        <section className="pipeline-lower">

          <div className="process-log">

            <div className="section-heading">
              <span>PROCESS LOG</span>
              <small>LIVE</small>
            </div>

            <div className="log-row">
              <time>14:23</time>
              <span className="log-dot"></span>
              <p>Sentinel-1 SAR scene received</p>
            </div>

            <div className="log-row">
              <time>14:25</time>
              <span className="log-dot"></span>
              <p>Oil slick segmentation completed</p>
            </div>

            <div className="log-row">
              <time>14:29</time>
              <span className="log-dot"></span>
              <p>Spill origin estimated through hindcasting</p>
            </div>

            <div className="log-row active-log">
              <time>14:34</time>
              <span className="log-dot"></span>
              <p>AIS vessel attribution in progress</p>
            </div>

          </div>

          <div className="attribution-result">

            <div className="section-heading">
              <span>ATTRIBUTION RESULT</span>
              <small>PRELIMINARY</small>
            </div>

            <div className="suspect-content">

              <div>

                <span className="suspect-label">
                  TOP SUSPECT
                </span>

                <strong className="suspect-name">
                  Tanker A
                </strong>

                <span className="suspect-description">
                  Highest correlation with estimated spill origin and movement window.
                </span>

              </div>

              <div className="suspect-score">
                <strong>87</strong>
                <span>/100</span>
              </div>

            </div>

          </div>

        </section>

      </main>

    </div>
  );
}

export default Pipeline;