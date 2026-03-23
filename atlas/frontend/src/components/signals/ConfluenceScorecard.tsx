/**
 * frontend/src/components/signals/ConfluenceScorecard.tsx
 * Live 8-factor TJR confluence scorecard — Section 10 of strategy document.
 */
import { useAtlasStore } from "../../store/atlasStore";

const FACTOR_NAMES = [
  "Daily HTF Bias",
  "4H Structure",
  "Judas Sweep Quality",
  "Session Timing",
  "Asia Range Quality",
  "Structural Confirm",
  "Entry Zone (FVG/OB)",
  "News Calendar",
];

const FACTOR_KEYS = [
  "f1_htf_bias",
  "f2_h4_structure",
  "f3_sweep_quality",
  "f4_timing",
  "f5_asia_range",
  "f6_structure",
  "f7_entry_zone",
  "f8_news",
];

const MAX_SCORE = 21;

function scoreBadge(score: number): string {
  if (score === 3) return "bg-atlas-long text-atlas-bg";
  if (score === 2) return "bg-atlas-neutral text-atlas-bg";
  if (score === 1) return "bg-atlas-short text-white";
  return "bg-atlas-border text-atlas-text-dim";
}

function gradeLabel(total: number): { label: string; color: string } {
  if (total >= 18) return { label: "A+", color: "text-atlas-long" };
  if (total >= 14) return { label: "A",  color: "text-atlas-accent" };
  if (total >= 10) return { label: "B",  color: "text-atlas-neutral" };
  return { label: "C", color: "text-atlas-short" };
}

export function ConfluenceScorecard() {
  const signal = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  const factors = signal?.decision_state?.["confluence"] as
    | { factors: Record<string, number>; reasons?: Record<string, string> }
    | undefined;

  const scores: number[]  = FACTOR_KEYS.map((k) => factors?.factors?.[k] ?? 0);
  const reasons: string[] = FACTOR_KEYS.map((k) => factors?.reasons?.[k] ?? "");
  const total = scores.reduce((a, b) => a + b, 0);
  const hasData = signal !== null;
  const grade   = hasData ? gradeLabel(total) : null;

  return (
    <div className="h-full bg-atlas-surface border border-atlas-border flex flex-col overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-atlas-border">
        <span className="font-mono text-[10px] tracking-[3px] text-atlas-text-dim uppercase">
          Confluence Stack
        </span>
        {hasData && grade && (
          <span className={`font-mono text-xs font-bold ${grade.color}`}>
            {total}/{MAX_SCORE} · {grade.label}
          </span>
        )}
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-atlas-border">
              <th className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-3 py-1.5">Factor</th>
              <th className="text-center font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-2 py-1.5 w-10">Sc</th>
              <th className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-2 py-1.5">Reason</th>
            </tr>
          </thead>
          <tbody>
            {FACTOR_NAMES.map((name, i) => {
              const score  = scores[i] ?? 0;
              const reason = reasons[i] ?? "";
              return (
                <tr key={name} className="border-b border-atlas-border hover:bg-atlas-bg transition-colors">
                  <td className="px-3 py-2 font-sans text-[11px] text-atlas-text-dim whitespace-nowrap">
                    {name}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {hasData ? (
                      <span className={`inline-block font-mono font-bold text-[10px] px-1.5 py-0.5 min-w-[20px] text-center ${scoreBadge(score)}`}>
                        {score}
                      </span>
                    ) : (
                      <span className="text-atlas-text-dim font-mono text-[10px]">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2 font-mono text-[9px] text-atlas-text-dim max-w-[120px] truncate">
                    {hasData && reason ? reason : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Total row with threshold markers */}
      <div className="px-3 py-2 border-t border-atlas-border">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] tracking-[2px] text-atlas-text-dim uppercase">Total</span>
          <span className={`font-mono text-xs font-bold ${hasData && grade ? grade.color : "text-atlas-text-dim"}`}>
            {hasData ? `${total}/${MAX_SCORE}` : "—"}
          </span>
        </div>
        {/* Progress bar with threshold markers */}
        <div className="relative h-1 bg-atlas-bg">
          {hasData && (
            <div
              className={`h-full transition-all duration-700 ${total >= 18 ? "bg-atlas-long" : total >= 14 ? "bg-atlas-accent" : total >= 10 ? "bg-atlas-neutral" : "bg-atlas-short"}`}
              style={{ width: `${(total / MAX_SCORE) * 100}%` }}
            />
          )}
          {/* Threshold ticks */}
          {[{ v: 10, label: "min" }, { v: 14, label: "A" }, { v: 18, label: "A+" }].map(({ v, label }) => (
            <div
              key={v}
              className="absolute top-0 flex flex-col items-center"
              style={{ left: `${(v / MAX_SCORE) * 100}%` }}
            >
              <div className="w-px h-3 bg-atlas-border-hi" style={{ marginTop: "-1px" }} />
              <span className="font-mono text-[7px] text-atlas-text-dim mt-0.5 -translate-x-1/2">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}