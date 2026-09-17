/**
 * frontend/src/components/session/SessionStatus.tsx
 * Compact session status bar — Asia range, HTF bias, LKZ timing, sweep, mode.
 */
import { useAtlasStore } from "../../store/atlasStore";
import { formatDateEST, getLKZStatus } from "../../lib/formatters";
import "./SessionStatus.css";

export function SessionStatus() {
  const session = useAtlasStore((s) => s.session);
  const mode    = useAtlasStore((s) => s.mode);
  const signal  = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  const today     = formatDateEST(new Date());
  const lkzStatus = getLKZStatus();

  const htfClass: Record<string, string> = {
    BULLISH:   "long",
    BEARISH:   "short",
    AMBIGUOUS: "neutral",
  };

  const sweepData = signal?.decision_state?.["sweep"] as
    | { detected?: boolean; direction?: string }
    | undefined;

  return (
    <div className="session-status">

      {/* Date */}
      <div className="session-pill">
        <span className="session-pill-label">Date</span>
        <span className="session-pill-value">{today}</span>
      </div>

      {/* Asia range */}
      <div className="session-pill">
        <span className="session-pill-label">Asia Range</span>
        {session?.range_valid ? (
          <span className="session-pill-value">
            {session.asia_range_pips?.toFixed(1)} pips
            <span className="asia-valid-mark"> ✓</span>
          </span>
        ) : session?.invalid_reason ? (
          <span className="asia-invalid-text">INVALID — {session.invalid_reason}</span>
        ) : (
          <span className="session-pill-value dim">—</span>
        )}
      </div>

      {/* HTF Bias */}
      <div className="session-pill">
        <span className="session-pill-label">HTF Bias</span>
        <span className={`session-pill-value ${htfClass[session?.htf_bias ?? "AMBIGUOUS"] ?? "dim"}`}>
          {session?.htf_bias ?? "—"}
        </span>
      </div>

      {/* LKZ */}
      <div className="session-pill">
        <span className="session-pill-label">LKZ</span>
        <span className={`lkz-badge ${lkzStatus.toLowerCase()}`}>{lkzStatus}</span>
      </div>

      {/* Sweep */}
      <div className="session-pill">
        <span className="session-pill-label">Sweep</span>
        {sweepData?.detected
          ? <span className="session-pill-value neutral">{sweepData.direction ?? "—"}</span>
          : <span className="session-pill-value dim">NONE</span>
        }
      </div>

      {/* Mode */}
      <div className="session-pill">
        <span className="session-pill-label">Mode</span>
        <span className={`session-pill-value ${mode === "AUTO" ? "accent" : "neutral"}`}>
          {mode}
        </span>
      </div>

    </div>
  );
}
