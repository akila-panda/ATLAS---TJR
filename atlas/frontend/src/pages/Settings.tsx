/**
 * frontend/src/pages/Settings.tsx
 * Read-only strategy constants and system status.
 */
import { useEffect, useState } from "react";
import { useAtlasStore }       from "../store/atlasStore";
import { getStatus }           from "../lib/api";
import "./Settings.css";

const CONSTANTS = [
  { label: "Asia Range Min",       value: "10 pips",          rule: "Rule 1.2" },
  { label: "Asia Range Max",       value: "40 pips",          rule: "Rule 1.2" },
  { label: "Wide Range Threshold", value: "38 pips",          rule: "Rule 1.4" },
  { label: "Sweep Min Extension",  value: "3 pips",           rule: "Rule 2.2" },
  { label: "Sweep Max Extension",  value: "8 pips",           rule: "Rule 2.2" },
  { label: "SL Buffer (standard)", value: "3 pips",           rule: "Rule 5.1" },
  { label: "SL Buffer (elevated)", value: "5 pips",           rule: "Rule 5.1c" },
  { label: "SL Max Distance",      value: "15 pips",          rule: "Rule 5.2" },
  { label: "Min R:R (standard)",   value: "2.0",              rule: "Rule 7.5" },
  { label: "Min R:R (wide range)", value: "2.5",              rule: "Rule 1.4" },
  { label: "Max Risk / Trade",     value: "1.0%",             rule: "Rule 7.2" },
  { label: "Late LKZ Risk",        value: "0.5%",             rule: "Rule 2.1a" },
  { label: "Max Daily Loss",       value: "2.0%",             rule: "Rule 7.3" },
  { label: "Min Confluence Score", value: "10 / 21",          rule: "Section 10" },
  { label: "TP1 Close %",          value: "40%",              rule: "Rule 6.2c" },
  { label: "TP2 Close %",          value: "35%",              rule: "Rule 6.3" },
  { label: "TP3 Runner %",         value: "25%",              rule: "Rule 6.4" },
  { label: "Entry Expiry",         value: "05:30 EST",        rule: "Rule 4.2d" },
  { label: "NY Open Kill",         value: "08:00 EST",        rule: "Rule 8.2.4" },
  { label: "LKZ Window",           value: "02:00–05:00 EST",  rule: "Section 8" },
  { label: "Asia Window",          value: "20:00–00:00 EST",  rule: "Rule 1.1" },
  { label: "Displacement Mult",    value: "1.5×",             rule: "Rule 4.1b" },
  { label: "Magic Number",         value: "20240101",         rule: "EA Config" },
];

type StatusLevel = "ok" | "warn" | "err";

function StatusCard({ label, status, detail }: { label: string; status: StatusLevel; detail: string }) {
  return (
    <div className="status-card">
      <div className={`status-card-dot ${status}`} />
      <div>
        <span className="status-card-label">{label}</span>
        <span className={`status-card-detail ${status}`}>{detail}</span>
      </div>
    </div>
  );
}

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
    <div className="settings">

      {/* Header */}
      <header className="settings-header">
        <span className="settings-header-brand">ATLAS</span>
        <span className="settings-header-crumb">/ Settings</span>
      </header>

      <div className="settings-body">

        {/* System status */}
        <section>
          <h2 className="settings-section-title">System Status</h2>
          <div className="settings-status-grid">
            <StatusCard
              label="MT5 Connection"
              status={mt5Connected ? "ok" : "warn"}
              detail={
                mt5Connected
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
        </section>

        {/* Strategy constants */}
        <section>
          <h2 className="settings-section-title">
            Strategy Constants — TJR EUR/USD London Session
          </h2>
          <div className="settings-table-wrapper">
            <table className="settings-table">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {CONSTANTS.map(({ label, value, rule }) => (
                  <tr key={label}>
                    <td className="td-label">{label}</td>
                    <td className="td-value">{value}</td>
                    <td className="td-rule">{rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="settings-note">
            All constants are hardcoded per the TJR EUR/USD Operational Document.
            Changes require code modification and restart.
          </p>
        </section>

      </div>
    </div>
  );
}
