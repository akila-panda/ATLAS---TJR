/**
 * frontend/src/components/session/SessionStatus.tsx
 * Compact session status bar — Asia range, HTF bias, LKZ timing, sweep, mode.
 */
import { useAtlasStore } from "../../store/atlasStore";
import { formatDateEST, getLKZStatus } from "../../lib/formatters";

export function SessionStatus() {
  const session = useAtlasStore((s) => s.session);
  const mode    = useAtlasStore((s) => s.mode);
  const signal  = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  const today     = formatDateEST(new Date());
  const lkzStatus = getLKZStatus();

  const lkzColors = {
    ACTIVE:  "text-atlas-long border-atlas-long",
    WAITING: "text-atlas-text-dim border-atlas-border",
    CLOSED:  "text-atlas-short border-atlas-short",
  };

  const htfColors: Record<string, string> = {
    BULLISH:   "text-atlas-long",
    BEARISH:   "text-atlas-short",
    AMBIGUOUS: "text-atlas-neutral",
  };

  const sweepDirection = signal?.decision_state?.["sweep"] as
    | { detected?: boolean; direction?: string }
    | undefined;

  return (
    <div className="h-full bg-atlas-surface border border-atlas-border flex items-center px-4 gap-6 overflow-x-auto">

      {/* Date */}
      <Pill label="DATE" value={today} valueClass="text-atlas-text-bright" />

      {/* Asia range */}
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">Asia Range</span>
        {session?.range_valid ? (
          <span className="font-mono text-xs text-atlas-text-bright">
            {session.asia_range_pips?.toFixed(1)} pips{" "}
            <span className="text-atlas-long text-[9px]">✓ VALID</span>
          </span>
        ) : session?.invalid_reason ? (
          <span className="font-mono text-xs text-atlas-short">
            INVALID — {session.invalid_reason}
          </span>
        ) : (
          <span className="font-mono text-xs text-atlas-text-dim">—</span>
        )}
      </div>

      {/* HTF Bias */}
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">HTF Bias</span>
        <span className={`font-mono text-xs font-bold ${htfColors[session?.htf_bias ?? "AMBIGUOUS"] ?? "text-atlas-text-dim"}`}>
          {session?.htf_bias ?? "—"}
        </span>
      </div>

      {/* LKZ Status */}
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">LKZ</span>
        <span className={`font-mono text-xs font-bold border px-1.5 py-0.5 ${lkzColors[lkzStatus]}`}>
          {lkzStatus}
        </span>
      </div>

      {/* Sweep badge */}
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">Sweep</span>
        {sweepDirection?.detected ? (
          <span className="font-mono text-xs font-bold text-atlas-neutral">
            {sweepDirection.direction ?? "—"}
          </span>
        ) : (
          <span className="font-mono text-xs text-atlas-text-dim">NONE</span>
        )}
      </div>

      {/* Mode */}
      <div>
        <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">Mode</span>
        <span className={`font-mono text-xs font-bold ${mode === "AUTO" ? "text-atlas-accent" : "text-atlas-neutral"}`}>
          {mode}
        </span>
      </div>
    </div>
  );
}

function Pill({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">{label}</span>
      <span className={`font-mono text-xs ${valueClass ?? "text-atlas-text-bright"}`}>{value}</span>
    </div>
  );
}