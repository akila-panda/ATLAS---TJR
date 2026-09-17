/**
 * frontend/src/components/signals/SignalCard.tsx
 * Live signal display — direction badge, confluence bar, data grid, CONFIRM/SKIP buttons.
 */
import { useState } from "react";
import { useAtlasStore } from "../../store/atlasStore";
import { confirmTrade, skipTrade } from "../../lib/api";
import { formatPrice, formatPips, formatRR } from "../../lib/formatters";
import "./SignalCard.css";

const CONFLUENCE_MAX = 21;

function confluenceFillClass(score: number): string {
  if (score >= 18) return "max";
  if (score >= 14) return "high";
  if (score >= 10) return "mid";
  return "low";
}

function gradeBadgeClass(grade: string): string {
  if (grade === "A+") return "aplus";
  if (grade === "A")  return "a";
  if (grade === "B")  return "b";
  return "c";
}

export function SignalCard() {
  const mode          = useAtlasStore((s) => s.mode);
  const latestSignal  = useAtlasStore((s) => s.latestSignal);
  const pendingSignal = useAtlasStore((s) => s.pendingSignal);
  const clearPending  = useAtlasStore((s) => s.clearPendingSignal);

  const signal           = pendingSignal ?? latestSignal;
  const isManualPending  = pendingSignal !== null && mode === "MANUAL";
  const [loading, setLoading] = useState(false);

  async function handleConfirm() {
    if (!pendingSignal) return;
    setLoading(true);
    try { await confirmTrade(pendingSignal.trade_id); }
    catch (e) { console.error("confirm failed", e); }
    finally   { setLoading(false); }
  }

  async function handleSkip() {
    setLoading(true);
    try { await skipTrade(); clearPending(); }
    catch (e) { console.error("skip failed", e); }
    finally   { setLoading(false); }
  }

  /* Empty state */
  if (!signal) {
    return (
      <div className="signal-card-empty">
        <p className="signal-card-empty-text">
          Waiting for LKZ sweep<span className="animate-blink">_</span>
        </p>
        <p className="signal-card-empty-time">02:00–05:00 EST</p>
      </div>
    );
  }

  const isEnter = signal.outcome === "ENTER";
  const isLong  = signal.direction === "BUY";
  const score   = signal.confluence_score ?? 0;
  const pct     = Math.min((score / CONFLUENCE_MAX) * 100, 100);

  const dirClass = isEnter ? (isLong ? "long" : "short") : "none";
  const dirLabel = isEnter ? (isLong ? "LONG" : "SHORT") : "NO TRADE";

  return (
    <div className="signal-card">

      {/* Header */}
      <div className="signal-card-header">
        <span className="signal-card-title">Signal</span>
        {signal.setup_grade && (
          <span className={`signal-grade-badge ${gradeBadgeClass(signal.setup_grade)}`}>
            {signal.setup_grade}
          </span>
        )}
      </div>

      {/* Direction */}
      <div className="signal-direction-block">
        <span className={`signal-direction-badge ${dirClass}`}>{dirLabel}</span>
        {!isEnter && signal.reason && (
          <p className="signal-no-trade-reason">{signal.reason}</p>
        )}
      </div>

      {/* Confluence bar */}
      <div className="signal-confluence">
        <div className="signal-confluence-header">
          <span className="signal-confluence-label">Confluence</span>
          <span className={`signal-confluence-score${score < 10 ? " low" : ""}`}>
            {score}/{CONFLUENCE_MAX}
          </span>
        </div>
        <div className="signal-confluence-track">
          <div
            className={`signal-confluence-fill ${confluenceFillClass(score)}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="signal-confluence-ticks">
          {[10, 14, 18].map((t) => (
            <div
              key={t}
              className="signal-confluence-tick"
              style={{ left: `${(t / CONFLUENCE_MAX) * 100}%` }}
            />
          ))}
        </div>
      </div>

      {/* Data grid — ENTER only */}
      {isEnter && (
        <div className="signal-data-grid">
          {[
            { label: "Entry",    value: signal.entry_price > 0 ? formatPrice(signal.entry_price) : "—" },
            { label: "SL",       value: signal.sl_price    > 0 ? formatPrice(signal.sl_price)    : "—" },
            { label: "TP1",      value: signal.tp1_price   > 0 ? formatPrice(signal.tp1_price)   : "—" },
            { label: "TP2",      value: signal.tp2_price   > 0 ? formatPrice(signal.tp2_price)   : "—" },
            { label: "TP3",      value: signal.tp3_price   > 0 ? formatPrice(signal.tp3_price)   : "—" },
            { label: "R:R",      value: signal.rr_ratio    > 0 ? formatRR(signal.rr_ratio)       : "—" },
            { label: "SL pips",  value: signal.sl_pips     > 0 ? formatPips(signal.sl_pips)      : "—" },
            { label: "Trade ID", value: signal.trade_id ? signal.trade_id.slice(0, 8) + "…"      : "—" },
          ].map(({ label, value }) => (
            <div key={label} className="signal-data-item">
              <span className="signal-data-label">{label}</span>
              <span className="signal-data-value">{value}</span>
            </div>
          ))}
        </div>
      )}

      <div className="signal-spacer" />

      {/* MANUAL action buttons */}
      {isManualPending && (
        <div className="signal-actions">
          <button
            className="signal-btn signal-btn-confirm"
            onClick={() => void handleConfirm()}
            disabled={loading}
          >
            {loading ? "…" : "Confirm Trade"}
          </button>
          <button
            className="signal-btn signal-btn-skip"
            onClick={() => void handleSkip()}
            disabled={loading}
          >
            Skip
          </button>
        </div>
      )}

    </div>
  );
}
