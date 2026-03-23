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

const STATUS_DOT: Record<string, string> = {
  connected:    "bg-atlas-long",
  reconnecting: "bg-atlas-neutral animate-pulse",
  disconnected: "bg-atlas-short",
};

export function Dashboard() {
  const mode             = useAtlasStore((s) => s.mode);
  const connectionStatus = useAtlasStore((s) => s.connectionStatus);
  const [estTime, setEstTime] = useState<string>(formatEST(new Date()));

  useEffect(() => {
    const id = setInterval(() => setEstTime(formatEST(new Date())), 1_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col h-screen bg-atlas-bg overflow-hidden">

      {/* ── Top bar ── */}
      <div className="h-10 flex-shrink-0 flex items-center justify-between px-4 border-b border-atlas-border bg-atlas-surface">
        <span className="font-mono text-atlas-accent font-bold tracking-[4px] text-sm uppercase">
          ATLAS
        </span>
        <div className="flex items-center gap-4">
          <span className="font-mono text-xs text-atlas-text-dim">{estTime} EST</span>
          <div className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${STATUS_DOT[connectionStatus] ?? "bg-atlas-border"}`} />
            <span className="font-mono text-[10px] text-atlas-text-dim uppercase tracking-widest">
              {connectionStatus}
            </span>
          </div>
          <span className={`font-mono text-[10px] font-bold px-2 py-0.5 border uppercase tracking-widest
            ${mode === "AUTO"
              ? "text-atlas-accent border-atlas-accent"
              : "text-atlas-neutral border-atlas-neutral"
            }`}>
            {mode}
          </span>
        </div>
      </div>

      {/* ── Main content ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — chart 65% */}
        <div className="flex-[65] min-w-0 border-r border-atlas-border overflow-hidden">
          <AtlasChart />
        </div>

        {/* Right — controls 35% */}
        <div className="flex-[35] min-w-0 flex flex-col overflow-hidden">
          {/* Mode toggle */}
          <div className="flex-shrink-0 p-2 border-b border-atlas-border">
            <AutoTradeToggle />
          </div>

          {/* Signal card — 50% of remaining */}
          <div className="flex-1 min-h-0 border-b border-atlas-border overflow-hidden">
            <SignalCard />
          </div>

          {/* Confluence scorecard — 50% of remaining */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <ConfluenceScorecard />
          </div>
        </div>
      </div>

      {/* ── Bottom bar — 200px ── */}
      <div className="h-[200px] flex-shrink-0 flex border-t border-atlas-border overflow-hidden">
        {/* Session status — 40% */}
        <div className="flex-[40] border-r border-atlas-border overflow-hidden">
          <SessionStatus />
        </div>
        {/* Open positions — 60% */}
        <div className="flex-[60] overflow-hidden">
          <OpenPositions />
        </div>
      </div>
    </div>
  );
}