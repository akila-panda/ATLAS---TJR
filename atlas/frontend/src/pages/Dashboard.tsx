/**
 * frontend/src/pages/Dashboard.tsx
 * Main ATLAS dashboard — chart left, controls right, status bottom.
 */
import { useState, useEffect } from "react";
import { useAtlasStore }       from "../store/atlasStore";
import { AtlasChart }          from "../components/chart/AtlasChart";
import { SignalCard }           from "../components/signals/SignalCard";
import { ConfluenceScorecard } from "../components/signals/ConfluenceScorecard";
import { SessionStatus }       from "../components/session/SessionStatus";
import { OpenPositions }       from "../components/trades/OpenPositions";
import { AutoTradeToggle }     from "../components/controls/AutoTradeToggle";
import { formatEST }           from "../lib/formatters";
import "./Dashboard.css";

export function Dashboard() {
  const mode             = useAtlasStore((s) => s.mode);
  const connectionStatus = useAtlasStore((s) => s.connectionStatus);
  const [estTime, setEstTime] = useState<string>(formatEST(new Date()));

  useEffect(() => {
    const id = setInterval(() => setEstTime(formatEST(new Date())), 1_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="dashboard">

      {/* ── Topbar ── */}
      <header className="dashboard-topbar">
        <span className="dashboard-topbar-brand">ATLAS</span>

        <div className="dashboard-topbar-right">
          <span className="dashboard-time">{estTime} EST</span>

          <div className="dashboard-conn">
            <div className={`dashboard-conn-dot ${connectionStatus}`} />
            <span className="dashboard-conn-label">{connectionStatus}</span>
          </div>

          <span className={`dashboard-mode-badge ${mode === "AUTO" ? "auto" : "manual"}`}>
            {mode}
          </span>
        </div>
      </header>

      {/* ── Main body ── */}
      <div className="dashboard-body">

        {/* Chart — 65% */}
        <div className="dashboard-chart">
          <AtlasChart />
        </div>

        {/* Right panel — 35% */}
        <div className="dashboard-right">
          <div className="dashboard-toggle-zone">
            <AutoTradeToggle />
          </div>
          <div className="dashboard-signal-zone">
            <SignalCard />
          </div>
          <div className="dashboard-confluence-zone">
            <ConfluenceScorecard />
          </div>
        </div>
      </div>

      {/* ── Bottom bar ── */}
      <div className="dashboard-bottom">
        <div className="dashboard-session">
          <SessionStatus />
        </div>
        <div className="dashboard-positions">
          <OpenPositions />
        </div>
      </div>

    </div>
  );
}
