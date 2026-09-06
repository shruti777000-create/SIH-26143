import Detection from "./pages/Detection";
import Forecast from "./pages/Forecast";
import Vessels from "./pages/Vessels";
import VesselBehavior from "./pages/VesselBehavior";
import EnvironmentalImpact from "./pages/EnvironmentalImpact";
import IncidentReport from "./pages/IncidentReport";
import Pipeline from "./pages/Pipeline";

import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";

import Investigation from "./pages/Investigation";
import "./index.css";
function PlaceholderPage({ title }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#06131b",
        color: "#edf4f6",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        fontFamily: "Arial, Helvetica, sans-serif",
      }}
    >
      <div
        style={{
          color: "#25bde5",
          fontSize: "12px",
          letterSpacing: "1.5px",
          marginBottom: "10px",
        }}
      >
        MARIS
      </div>

      <h1
        style={{
          fontSize: "32px",
          margin: 0,
        }}
      >
        {title}
      </h1>

      <p
        style={{
          marginTop: "12px",
          color: "#8fa5ae",
          fontSize: "14px",
        }}
      >
        This MARIS module will be built next.
      </p>

      <button
        onClick={() => (window.location.href = "/investigation")}
        style={{
          marginTop: "20px",
          padding: "12px 22px",
          background: "#078dca",
          color: "white",
          border: "1px solid #20bce3",
          borderRadius: "4px",
          cursor: "pointer",
        }}
      >
        Back to Investigation
      </button>
    </div>
  );
}
function StatCard({ icon, value, label, accent = false }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>

      <div>
        <div className={`stat-value ${accent ? "accent" : ""}`}>
          {value}
        </div>

        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
}

function Landing() {
  return (
    <div className="maris-page">
      <div className="hero-background" />

      <header className="navbar">
        <div className="brand">
          <div className="brand-mark">
            <span>◈</span>
          </div>

          <div className="brand-text">
            <div className="brand-name">MARIS</div>

            <div className="brand-subtitle">
              Maritime Oil Spill Intelligence System
            </div>
          </div>
        </div>

        <nav className="nav-links">
          <a className="active" href="/">
            Home
          </a>

          <a href="#features">
            Features
          </a>

          <a href="#how">
            How It Works
          </a>

          <a href="/investigation">
            Dashboard
          </a>

          <a href="#about">
            About
          </a>
        </nav>

        <button className="login-button">
          Login
        </button>
      </header>

      <main className="hero">
        <div className="hero-content">
          <h1>
            Detect. Trace. Predict.{" "}
            <span>Identify.</span>
          </h1>

          <p>
            AI-powered platform to detect oil spills from satellite
            imagery, trace their origin, predict future drift, and
            identify the most likely polluting vessel.
          </p>

          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={() =>
                (window.location.href = "/investigation")
              }
            >
              Start Investigation
            </button>

            <button className="secondary-button">
              View Live Demo
            </button>
          </div>
        </div>

        <div className="stats-row">
          <StatCard
            icon="♧"
            value="12.4 km²"
            label="Spill Area"
            accent
          />

          <StatCard
            icon="◷"
            value="5.2 hrs"
            label="Estimated Age"
          />

          <StatCard
            icon="♢"
            value="91%"
            label="Confidence"
            accent
          />

          <div className="stat-card suspect-card">
            <div className="stat-icon suspect-icon">
              ♙
            </div>

            <div>
              <div className="stat-value">
                Tanker A
              </div>

              <div className="stat-label">
                Top Suspect
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
     <Routes>
  <Route path="/" element={<Landing />} />
  <Route
  path="/vessel-behavior"
  element={<VesselBehavior />}
/>

  <Route
    path="/investigation"
    element={<Investigation />}
  />
  <Route path="/forecast" element={<Forecast />} />
  <Route
  path="/pipeline"
  element={<Pipeline />}
/>
<Route
  path="/report"
  element={<IncidentReport />}
/>
<Route
  path="/environmental-impact"
  element={<EnvironmentalImpact />}
/>
<Route path="/vessels" element={<Vessels />} />
  <Route path="/detection" element={<Detection />} />
  <Route
    path="/dashboard"
    element={<PlaceholderPage title="Dashboard" />}
  />

  <Route
    path="/incidents"
    element={<PlaceholderPage title="Incidents" />}
  />

 
<Route path="/reports" element={<IncidentReport />} />

  

  <Route
    path="/settings"
    element={<PlaceholderPage title="Settings" />}
  />

  <Route
    path="*"
    element={<Navigate to="/" replace />}
  />
</Routes>
    </BrowserRouter>
  );
}

export default App;