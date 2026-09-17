/**
 * frontend/src/components/session/RiskMeter.tsx
 * SVG circular arc gauge — daily loss vs 2% limit (Rule 7.3).
 * Light-mode aware colour tokens.
 */
import { useAtlasStore } from "../../store/atlasStore";
import "./RiskMeter.css";

const SIZE   = 120;
const RADIUS = 46;
const CX     = SIZE / 2;
const CY     = SIZE / 2;
const STROKE = 6;
const START_DEG = 160;
const SWEEP_DEG = 220;

function degToRad(d: number) { return (d * Math.PI) / 180; }

function polarToXY(deg: number, r: number) {
  const rad = degToRad(deg);
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

function describeArc(startDeg: number, endDeg: number, r: number): string {
  const s     = polarToXY(startDeg, r);
  const e     = polarToXY(endDeg, r);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
}

function arcColor(pct: number, terminated: boolean): string {
  if (terminated) return "#c41c38";
  if (pct >= 75)  return "#c41c38";
  if (pct >= 50)  return "#b56b00";
  return "#0a7e5c";
}

interface Props {
  compact?: boolean;
}

export function RiskMeter({ compact = false }: Props) {
  const risk    = useAtlasStore((s) => s.riskState);
  const ACCOUNT = 100_000;

  const dailyLossPct = risk.daily_loss_pct;
  const terminated   = risk.session_terminated;
  const wins         = risk.trades_today - Math.round((risk.daily_loss_pct / 100) * risk.trades_today);
  const losses       = risk.trades_today - Math.max(0, wins);
  const remaining    = ACCOUNT * (1 - risk.daily_loss_pct / 100);

  const fillPct  = Math.min((dailyLossPct / 2.0) * 100, 100);
  const color    = arcColor(fillPct, terminated);

  const bgPath   = describeArc(START_DEG, START_DEG + SWEEP_DEG, RADIUS);
  const fillEnd  = START_DEG + (SWEEP_DEG * fillPct) / 100;
  const fillPath = fillPct > 0 ? describeArc(START_DEG, fillEnd, RADIUS) : null;

  const size  = compact ? 80 : SIZE;
  const scale = compact ? 80 / SIZE : 1;

  return (
    <div className="risk-meter">
      <div style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
          {/* Track */}
          <path
            d={bgPath}
            fill="none"
            stroke="#dde3ee"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
          {/* Fill */}
          {fillPath && (
            <path
              d={fillPath}
              fill="none"
              stroke={color}
              strokeWidth={STROKE}
              strokeLinecap="round"
              style={{ transition: "stroke 0.5s" }}
            />
          )}
          {/* Center label */}
          {terminated ? (
            <>
              <text x={CX} y={CY - 4}  textAnchor="middle" fontFamily='"JetBrains Mono"' fontSize="9"  fill="#c41c38" fontWeight="700">SESSION</text>
              <text x={CX} y={CY + 8}  textAnchor="middle" fontFamily='"JetBrains Mono"' fontSize="9"  fill="#c41c38" fontWeight="700">TERMINATED</text>
            </>
          ) : (
            <text x={CX} y={CY + 5} textAnchor="middle" fontFamily='"JetBrains Mono"' fontSize="18" fill={color} fontWeight="700">
              {dailyLossPct.toFixed(1)}%
            </text>
          )}
          {/* Bottom label */}
          <text x={CX} y={CY + 30} textAnchor="middle" fontFamily='"JetBrains Mono"' fontSize="8" fill="#8097b1">
            DAILY LOSS
          </text>
        </svg>
      </div>

      {!compact && (
        <div className="risk-meter-info">
          <span className="risk-meter-wl">W:{Math.max(0, wins)} / L:{Math.max(0, losses)}</span>
          <span className="risk-meter-budget">Budget: ${Math.max(0, remaining).toFixed(0)}</span>
        </div>
      )}
    </div>
  );
}
