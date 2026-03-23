/**
 * frontend/src/App.tsx
 * ATLAS app root — sidebar navigation, routing, WebSocket init.
 */
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { useSocket }     from "./hooks/useSocket";
import { useAtlasData }  from "./hooks/useAtlasData";
import { RiskMeter }     from "./components/session/RiskMeter";
import { Dashboard }     from "./pages/Dashboard";
import { Journal }       from "./pages/Journal";
import { Settings }      from "./pages/Settings";

function Sidebar() {
  const linkBase   = "block font-mono text-[10px] tracking-[3px] uppercase px-3 py-2.5 transition-colors border-l-2 ";
  const linkActive = linkBase + "text-atlas-accent border-atlas-accent bg-atlas-accent/5";
  const linkInactive = linkBase + "text-atlas-text-dim border-transparent hover:text-atlas-text-bright hover:border-atlas-border";

  return (
    <div className="w-44 flex-shrink-0 bg-atlas-surface border-r border-atlas-border flex flex-col overflow-hidden">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-atlas-border">
        <span className="font-mono text-atlas-accent font-bold tracking-[5px] text-sm">ATLAS</span>
        <span className="block font-sans text-[8px] tracking-[2px] text-atlas-text-dim mt-0.5 uppercase">TJR EUR/USD</span>
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 space-y-0.5">
        <NavLink to="/"         end className={({ isActive }) => isActive ? linkActive : linkInactive}>Dashboard</NavLink>
        <NavLink to="/journal"      className={({ isActive }) => isActive ? linkActive : linkInactive}>Journal</NavLink>
        <NavLink to="/settings"     className={({ isActive }) => isActive ? linkActive : linkInactive}>Settings</NavLink>
      </nav>

      {/* Risk meter compact */}
      <div className="px-4 py-4 border-t border-atlas-border">
        <RiskMeter compact />
      </div>
    </div>
  );
}

function AppInner() {
  // Init WebSocket and data polling at root level
  useSocket();
  useAtlasData();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-atlas-bg">
      <Sidebar />
      <div className="flex-1 min-w-0 overflow-hidden">
        <Routes>
          <Route path="/"         element={<Dashboard />} />
          <Route path="/journal"  element={<Journal />} />
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