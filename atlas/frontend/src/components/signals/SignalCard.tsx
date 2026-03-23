/**
 * frontend/src/components/signals/SignalCard.tsx
 * Live signal display — direction badge, confluence bar, data grid, CONFIRM/SKIP buttons.
 */
import { useState } from "react";
import { useAtlasStore } from "../../store/atlasStore";
import { confirmTrade, skipTrade } from "../../lib/api";
import { formatPrice, formatPips, formatRR, gradeColor } from "../../lib/formatters";

const CONFLUENCE_MAX = 21;

function confluenceBarColor(score: number): string {
  if (score >= 18) return "bg-atlas-long";
  if (score >= 14) return "bg-atlas-accent";
  if (score >= 10) return "bg-atlas-neutral";
  return "bg-atlas-short";
}

export function SignalCard() {
  const mode          = useAtlasStore((s) => s.mode);
  const latestSignal  = useAtlasStore((s) => s.latestSignal);
  const pendingSignal = useAtlasStore((s) => s.pendingSignal);
  const clearPending  = useAtlasStore((s) => s.clearPendingSignal);

  const signal = pendingSignal ?? latestSignal;
  const isManualPending = pendingSignal !== null && mode === "MANUAL";

  const [loading, setLoading] = useState(false);

  async function handleConfirm() {
    if (!pendingSignal) return;
    setLoading(true);
    try {
      await confirmTrade(pendingSignal.trade_id);
    } catch (e) {
      console.error("confirm failed", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSkip() {
    setLoading(true);
    try {
      await skipTrade();
      clearPending();
    } catch (e) {
      console.error("skip failed", e);
    } finally {
      setLoading(false);
    }
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (!signal) {
    return (
      <div className="h-full bg-atlas-surface border border-atlas-border flex flex-col items-center justify-center p-6">
        <p className="font-mono text-atlas-text-dim text-sm tracking-widest uppercase">
          Waiting for LKZ sweep
          <span className="animate-pulse">_</span>
        </p>
        <p className="font-mono text-atlas-text-dim text-xs mt-2 opacity-50">
          02:00–05:00 EST
        </p>
      </div>
    );
  }

  const isEnter    = signal.outcome === "ENTER";
  const isLong     = signal.direction === "BUY";
  const score      = signal.confluence_score ?? 0;
  const pct        = Math.min((score / CONFLUENCE_MAX) * 100, 100);

  // ── Direction badge ────────────────────────────────────────────────────────
  const dirBadgeCls = isEnter
    ? isLong
      ? "bg-atlas-long text-atlas-bg"
      : "bg-atlas-short text-white"
    : "bg-atlas-neutral text-atlas-bg";

  const dirLabel = isEnter
    ? isLong ? "LONG" : "SHORT"
    : "NO TRADE";

  return (
    <div className="h-full bg-atlas-surface border border-atlas-border flex flex-col overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-atlas-border">
        <span className="font-mono text-[10px] tracking-[3px] text-atlas-text-dim uppercase">Signal</span>
        {signal.setup_grade && (
          <span className={`font-mono text-xs font-bold ${gradeColor(signal.setup_grade)} border ${signal.setup_grade === "A+" ? "border-atlas-long" : signal.setup_grade === "A" ? "border-atlas-accent" : signal.setup_grade === "B" ? "border-atlas-neutral" : "border-atlas-short"} px-2 py-0.5`}>
            {signal.setup_grade}
          </span>
        )}
      </div>

      {/* Direction badge */}
      <div className="px-3 pt-3 pb-2">
        <div className={`inline-block px-4 py-2 font-mono font-bold text-xl tracking-widest uppercase ${dirBadgeCls}`}>
          {dirLabel}
        </div>
        {!isEnter && signal.reason && (
          <p className="font-mono text-atlas-neutral text-xs mt-2 tracking-wider">
            {signal.reason}
          </p>
        )}
      </div>

      {/* Confluence bar */}
      <div className="px-3 pb-2">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] tracking-[2px] text-atlas-text-dim uppercase">Confluence</span>
          <span className={`font-mono text-xs font-bold ${score >= 10 ? "text-atlas-text-bright" : "text-atlas-short"}`}>
            {score}/{CONFLUENCE_MAX}
          </span>
        </div>
        <div className="h-1.5 bg-atlas-bg rounded-none overflow-hidden">
          <div
            className={`h-full transition-all duration-700 ease-out ${confluenceBarColor(score)}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        {/* Threshold markers */}
        <div className="relative h-2 mt-0.5">
          {[10, 14, 18].map((threshold) => (
            <div
              key={threshold}
              className="absolute top-0 w-px h-2 bg-atlas-border"
              style={{ left: `${(threshold / CONFLUENCE_MAX) * 100}%` }}
            />
          ))}
        </div>
      </div>

      {/* Data grid — only when ENTER */}
      {isEnter && (
        <div className="px-3 pb-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
          {[
            { label: "Entry", value: signal.entry_price > 0 ? formatPrice(signal.entry_price) : "—" },
            { label: "SL",    value: signal.sl_price    > 0 ? formatPrice(signal.sl_price)    : "—" },
            { label: "TP1",   value: signal.tp1_price   > 0 ? formatPrice(signal.tp1_price)   : "—" },
            { label: "TP2",   value: signal.tp2_price   > 0 ? formatPrice(signal.tp2_price)   : "—" },
            { label: "TP3",   value: signal.tp3_price   > 0 ? formatPrice(signal.tp3_price)   : "—" },
            { label: "R:R",   value: signal.rr_ratio    > 0 ? formatRR(signal.rr_ratio)       : "—" },
            { label: "SL pips", value: signal.sl_pips   > 0 ? formatPips(signal.sl_pips)      : "—" },
            { label: "Trade ID", value: signal.trade_id ? signal.trade_id.slice(0, 8) + "…" : "—" },
          ].map(({ label, value }) => (
            <div key={label}>
              <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">{label}</span>
              <span className="block font-mono text-xs text-atlas-text-bright">{value}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex-1" />

      {/* MANUAL mode action buttons */}
      {isManualPending && (
        <div className="px-3 pb-3 flex gap-2">
          <button
            onClick={() => void handleConfirm()}
            disabled={loading}
            className="flex-1 py-2 font-mono text-xs font-bold tracking-widest uppercase border border-atlas-long text-atlas-long hover:bg-atlas-long hover:text-atlas-bg transition-colors disabled:opacity-40"
          >
            {loading ? "…" : "Confirm Trade"}
          </button>
          <button
            onClick={() => void handleSkip()}
            disabled={loading}
            className="flex-1 py-2 font-mono text-xs font-bold tracking-widest uppercase border border-atlas-short text-atlas-short hover:bg-atlas-short hover:text-white transition-colors disabled:opacity-40"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  );
}