/**
 * frontend/src/components/trades/OpenPositions.tsx
 * Live open position panel — TP/SL price grid and lifecycle flags.
 */
import { useAtlasStore } from "../../store/atlasStore";
import { formatPrice, formatPnL } from "../../lib/formatters";
import "./OpenPositions.css";

function Flag({ label, active }: { label: string; active: boolean }) {
  return (
    <div className={`trade-flag${active ? " is-active" : ""}`}>
      <div className="trade-flag-dot" />
      {label}
    </div>
  );
}

export function OpenPositions() {
  const trade = useAtlasStore((s) => s.openTrade);

  if (!trade) {
    return (
      <div className="open-positions-empty">
        <p className="open-positions-empty-text">No Open Position</p>
      </div>
    );
  }

  const isLong   = trade.direction === "BUY";
  const pnlClass = trade.unrealized_pnl >= 0 ? "positive" : "negative";

  return (
    <div className="open-positions">

      {/* Header */}
      <div className="open-positions-header">
        <div className="op-header-left">
          <span className="op-header-title">Open Position</span>
          <span className={`op-direction-label ${isLong ? "long" : "short"}`}>{trade.direction}</span>
          <span className="op-ticket">#{trade.ticket} · {trade.current_lot}L</span>
        </div>
        <span className={`op-pnl ${pnlClass}`}>{formatPnL(trade.unrealized_pnl)}</span>
      </div>

      {/* Price grid */}
      <div className="op-prices">
        {[
          { label: "Entry",    value: formatPrice(trade.entry_price),  cls: "entry" },
          { label: "SL",       value: formatPrice(trade.current_sl),   cls: "sl" },
          { label: "TP1 40%",  value: formatPrice(trade.tp1_price),    cls: trade.tp1_hit ? "tp-hit" : "tp" },
          { label: "TP2 35%",  value: formatPrice(trade.tp2_price),    cls: trade.tp2_hit ? "tp-hit" : "tp" },
          { label: "TP3 25%",  value: formatPrice(trade.tp3_price),    cls: "tp" },
        ].map(({ label, value, cls }) => (
          <div key={label} className="op-price-item">
            <span className="op-price-label">{label}</span>
            <span className={`op-price-value ${cls}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* Lifecycle flags */}
      <div className="op-flags">
        <Flag label="BE"       active={trade.be_moved} />
        <Flag label="TP1"      active={trade.tp1_hit} />
        <Flag label="TP2"      active={trade.tp2_hit} />
        <Flag label="TRAILING" active={trade.trailing_active} />
        {trade.opened_at && (
          <span className="op-opened-time">
            Opened {new Date(trade.opened_at).toLocaleTimeString("en-US", {
              timeZone: "America/New_York",
              hour: "2-digit", minute: "2-digit", hour12: false,
            })} EST
          </span>
        )}
      </div>

    </div>
  );
}
