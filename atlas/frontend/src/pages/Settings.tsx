/**
 * frontend/src/pages/Settings.tsx
 * Read-only strategy constants and system status.
 */
import { useEffect, useState } from "react";
import { useAtlasStore }       from "../store/atlasStore";
import { getStatus }           from "../lib/api";

const CONSTANTS = [
  { label: "Asia Range Min",       value: "10 pips",      rule: "Rule 1.2" },
  { label: "Asia Range Max",       value: "40 pips",      rule: "Rule 1.2" },
  { label: "Wide Range Threshold", value: "38 pips",      rule: "Rule 1.4" },
  { label: "Sweep Min Extension",  value: "3 pips",       rule: "Rule 2.2" },
  { label: "Sweep Max Extension",  value: "8 pips",       rule: "Rule 2.2" },
  { label: "SL Buffer (standard)", value: "3 pips",       rule: "Rule 5.1" },
  { label: "SL Buffer (elevated)", value: "5 pips",       rule: "Rule 5.1c" },
  { label: "SL Max Distance",      value: "15 pips",      rule: "Rule 5.2" },
  { label: "Min R:R (standard)",   value: "2.0",          rule: "Rule 7.5" },
  { label: "Min R:R (wide range)", value: "2.5",          rule: "Rule 1.4" },
  { label: "Max Risk / Trade",     value: "1.0%",         rule: "Rule 7.2" },
  { label: "Late LKZ Risk",        value: "0.5%",         rule: "Rule 2.1a" },
  { label: "Max Daily Loss",       value: "2.0%",         rule: "Rule 7.3" },
  { label: "Min Confluence Score", value: "10 / 21",      rule: "Section 10" },
  { label: "TP1 Close %",          value: "40%",          rule: "Rule 6.2c" },
  { label: "TP2 Close %",          value: "35%",          rule: "Rule 6.3" },
  { label: "TP3 Runner %",         value: "25%",          rule: "Rule 6.4" },
  { label: "Entry Expiry",         value: "05:30 EST",    rule: "Rule 4.2d" },
  { label: "NY Open Kill",         value: "08:00 EST",    rule: "Rule 8.2.4" },
  { label: "LKZ Window",          value: "02:00–05:00 EST", rule: "Section 8" },
  { label: "Asia Window",         value: "20:00–00:00 EST", rule: "Rule 1.1" },
  { label: "Displacement Mult",   value: "1.5×",         rule: "Rule 4.1b" },
  { label: "Magic Number",        value: "20240101",      rule: "EA Config" },
];

export function Settings() {
  const lastUpdated      = useAtlasStore((s) => s.lastUpdated);
  const connectionStatus = useAtlasStore((s) => s.connectionStatus);
  const [uptimeSec, setUptimeSec] = useState<number | null>(null);

  useEffect(() => {
    getStatus()
      .then((d) => setUptimeSec(d.uptime_sec))
      .catch(() => setUptimeSec(null));
  }, []);

  const lastCandleAge = lastUpdated
    ? Math.floor((Date.now() - lastUpdated.getTime()) / 1000)
    : null;
  const mt5Connected = lastCandleAge !== null && lastCandleAge < 90;

  return (
    <div className="flex flex-col h-screen bg-atlas-bg overflow-hidden">
      {/* Header */}
      <div className="h-10 flex-shrink-0 flex items-center px-6 border-b border-atlas-border bg-atlas-surface">
        <span className="font-mono text-atlas-accent font-bold tracking-[4px] text-sm uppercase">ATLAS</span>
        <span className="font-mono text-atlas-text-dim text-xs ml-4 tracking-widest">/ SETTINGS</span>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">

        {/* System status */}
        <div>
          <h2 className="font-mono text-[10px] tracking-[4px] text-atlas-accent uppercase mb-3">System Status</h2>
          <div className="grid grid-cols-3 gap-3">
            <StatusCard
              label="MT5 Connection"
              status={mt5Connected ? "ok" : "warn"}
              detail={mt5Connected
                ? `Last candle ${lastCandleAge}s ago`
                : lastCandleAge !== null
                  ? `Last candle ${lastCandleAge}s ago`
                  : "No data received"
              }
            />
            <StatusCard
              label="WebSocket"
              status={connectionStatus === "connected" ? "ok" : connectionStatus === "reconnecting" ? "warn" : "err"}
              detail={connectionStatus}
            />
            <StatusCard
              label="API Server"
              status={uptimeSec !== null ? "ok" : "err"}
              detail={uptimeSec !== null ? `Uptime: ${Math.floor(uptimeSec / 60)}m` : "Unreachable"}
            />
          </div>
        </div>

        {/* Strategy constants */}
        <div>
          <h2 className="font-mono text-[10px] tracking-[4px] text-atlas-accent uppercase mb-3">
            Strategy Constants — TJR EUR/USD London Session
          </h2>
          <div className="bg-atlas-surface border border-atlas-border overflow-hidden">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-atlas-border">
                  <th className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-4 py-2">Parameter</th>
                  <th className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-4 py-2">Value</th>
                  <th className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-4 py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {CONSTANTS.map(({ label, value, rule }) => (
                  <tr key={label} className="border-b border-atlas-border hover:bg-atlas-bg transition-colors">
                    <td className="px-4 py-2 font-sans text-[11px] text-atlas-text-dim">{label}</td>
                    <td className="px-4 py-2 font-mono text-xs font-bold text-atlas-text-bright">{value}</td>
                    <td className="px-4 py-2 font-mono text-[9px] text-atlas-accent">{rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="font-mono text-[9px] text-atlas-text-dim mt-2">
            All constants are hardcoded per the TJR EUR/USD Operational Document. Changes require code modification and restart.
          </p>
        </div>
      </div>
    </div>
  );
}

function StatusCard({ label, status, detail }: { label: string; status: "ok" | "warn" | "err"; detail: string }) {
  const colors = {
    ok:   { dot: "bg-atlas-long",    text: "text-atlas-long" },
    warn: { dot: "bg-atlas-neutral animate-pulse", text: "text-atlas-neutral" },
    err:  { dot: "bg-atlas-short",   text: "text-atlas-short" },
  };
  const c = colors[status];

  return (
    <div className="bg-atlas-surface border border-atlas-border p-3 flex items-start gap-3">
      <div className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${c.dot}`} />
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">{label}</span>
        <span className={`block font-mono text-xs font-bold ${c.text} mt-0.5`}>{detail}</span>
      </div>
    </div>
  );
}