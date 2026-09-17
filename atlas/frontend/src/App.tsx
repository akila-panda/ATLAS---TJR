/**
 * frontend/src/App.tsx
 * ATLAS app root — sidebar navigation, routing, WebSocket init.
 */
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { useSocket }    from "./hooks/useSocket";
import { useAtlasData } from "./hooks/useAtlasData";
import { RiskMeter }    from "./components/session/RiskMeter";
import { Dashboard }    from "./pages/Dashboard";
import { Journal }      from "./pages/Journal";
import { Settings }     from "./pages/Settings";
import "./App.css";

function Sidebar() {
  return (
    <aside className="atlas-sidebar">
      {/* Logo */}
      <div className="atlas-logo">
        <span className="atlas-logo-name">ATLAS</span>
        <span className="atlas-logo-sub">TJR EUR/USD</span>
      </div>

      {/* Nav */}
      <nav className="atlas-nav">
        <NavLink to="/"        end className={({ isActive }) => `atlas-nav-link${isActive ? " active" : ""}`}>Dashboard</NavLink>
        <NavLink to="/journal"     className={({ isActive }) => `atlas-nav-link${isActive ? " active" : ""}`}>Journal</NavLink>
        <NavLink to="/settings"    className={({ isActive }) => `atlas-nav-link${isActive ? " active" : ""}`}>Settings</NavLink>
      </nav>

      {/* Risk meter compact */}
      <div className="atlas-sidebar-footer">
        <RiskMeter compact />
      </div>
    </aside>
  );
}

function AppInner() {
  useSocket();
  useAtlasData();

  return (
    <div className="atlas-root">
      <Sidebar />
      <div className="atlas-content">
        <Routes>
          <Route path="/"        element={<Dashboard />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}
