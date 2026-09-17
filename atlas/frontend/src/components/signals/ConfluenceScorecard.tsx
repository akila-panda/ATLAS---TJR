/**
 * frontend/src/components/signals/ConfluenceScorecard.tsx
 * Live 8-factor TJR confluence scorecard — Section 10.
 */
import { useAtlasStore } from "../../store/atlasStore";
import "./ConfluenceScorecard.css";

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

function scoreBadgeClass(score: number): string {
  if (score === 3) return "s3";
  if (score === 2) return "s2";
  if (score === 1) return "s1";
  return "s0";
}

function gradeInfo(total: number): { label: string; cls: string; barCls: string } {
  if (total >= 18) return { label: "A+",   cls: "aplus", barCls: "aplus" };
  if (total >= 14) return { label: "A",    cls: "a",     barCls: "a" };
  if (total >= 10) return { label: "B",    cls: "b",     barCls: "b" };
  return               { label: "C",    cls: "c",     barCls: "c" };
}

export function ConfluenceScorecard() {
  const signal = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  const factors = signal?.decision_state?.["confluence"] as
    | { factors: Record<string, number>; reasons?: Record<string, string> }
    | undefined;

  const scores:  number[] = FACTOR_KEYS.map((k) => factors?.factors?.[k] ?? 0);
  const reasons: string[] = FACTOR_KEYS.map((k) => factors?.reasons?.[k]  ?? "");
  const total   = scores.reduce((a, b) => a + b, 0);
  const hasData = signal !== null;
  const grade   = hasData ? gradeInfo(total) : null;

  return (
    <div className="confluence-scorecard">

      {/* Header */}
      <div className="confluence-scorecard-header">
        <span className="confluence-scorecard-title">Confluence Stack</span>
        {hasData && grade && (
          <span className={`confluence-total-badge ${grade.cls}`}>
            {total}/{MAX_SCORE} · {grade.label}
          </span>
        )}
      </div>

      {/* Factor table */}
      <div className="confluence-table-wrapper">
        <table className="confluence-table">
          <thead>
            <tr>
              <th>Factor</th>
              <th style={{ textAlign: "center", width: 40 }}>Sc</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {FACTOR_NAMES.map((name, i) => {
              const score  = scores[i] ?? 0;
              const reason = reasons[i] ?? "";
              return (
                <tr key={name}>
                  <td className="cf-factor-name">{name}</td>
                  <td className="cf-score-cell">
                    {hasData
                      ? <span className={`cf-score-badge ${scoreBadgeClass(score)}`}>{score}</span>
                      : <span style={{ color: "var(--text-dim)", fontSize: 10 }}>—</span>
                    }
                  </td>
                  <td className="cf-reason">{hasData && reason ? reason : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="confluence-scorecard-footer">
        <div className="cf-footer-row">
          <span className="cf-footer-label">Total</span>
          <span className={`cf-footer-total${grade ? ` confluence-total-badge ${grade.cls}` : ""}`}>
            {hasData ? `${total}/${MAX_SCORE}` : "—"}
          </span>
        </div>

        <div className="cf-progress-track">
          {hasData && grade && (
            <div
              className={`cf-progress-fill ${grade.barCls}`}
              style={{ width: `${(total / MAX_SCORE) * 100}%` }}
            />
          )}
          {[{ v: 10, label: "min" }, { v: 14, label: "A" }, { v: 18, label: "A+" }].map(({ v, label }) => (
            <div
              key={v}
              className="cf-tick"
              style={{ left: `${(v / MAX_SCORE) * 100}%` }}
            >
              <div className="cf-tick-line" />
              <span className="cf-tick-label">{label}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
