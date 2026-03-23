/**
 * frontend/src/components/trades/OpenPositions.tsx
 * Live open position panel — shows active trade with TP/SL levels and lifecycle flags.
 */
import { useAtlasStore } from "../../store/atlasStore";
import { formatPrice, formatPnL, formatPips } from "../../lib/formatters";

export function OpenPositions() {
  const trade = useAtlasStore((s) => s.openTrade);

  if (!trade) {
    return (
      <div className="h-full bg-atlas-surface border border-atlas-border flex items-center justify-center">
        <p className="font-mono text-xs text-atlas-text-dim tracking-widest uppercase">
          No Open Position
        </p>
      </div>
    );
  }

  const isLong    = trade.direction === "BUY";
  const dirColor  = isLong ? "text-atlas-long" : "text-atlas-short";
  const pnlColor  = trade.unrealized_pnl >= 0 ? "text-atlas-long" : "text-atlas-short";

  return (
    <div className="h-full bg-atlas-surface border border-atlas-border flex flex-col overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-atlas-border">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] tracking-[3px] text-atlas-text-dim uppercase">Open Position</span>
          <span className={`font-mono text-xs font-bold ${dirColor}`}>{trade.direction}</span>
          <span className="font-mono text-xs text-atlas-text-dim">
            #{trade.ticket} · {trade.current_lot}L
          </span>
        </div>
        <span className={`font-mono text-sm font-bold ${pnlColor}`}>
          {formatPnL(trade.unrealized_pnl)}
        </span>
      </div>

      {/* Price levels grid */}
      <div className="flex-1 px-4 py-3 grid grid-cols-5 gap-4 items-center">
        {[
          { label: "Entry",  value: formatPrice(trade.entry_price),  cls: "text-atlas-accent" },
          { label: "SL",     value: formatPrice(trade.current_sl),   cls: "text-atlas-short" },
          { label: "TP1 40%", value: formatPrice(trade.tp1_price),   cls: trade.tp1_hit ? "text-atlas-long line-through opacity-50" : "text-atlas-long" },
          { label: "TP2 35%", value: formatPrice(trade.tp2_price),   cls: trade.tp2_hit ? "text-atlas-long line-through opacity-50" : "text-atlas-long" },
          { label: "TP3 25%", value: formatPrice(trade.tp3_price),   cls: "text-atlas-long" },
        ].map(({ label, value, cls }) => (
          <div key={label}>
            <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase">{label}</span>
            <span className={`font-mono text-xs font-bold ${cls}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* Lifecycle flags */}
      <div className="px-4 py-2 border-t border-atlas-border flex items-center gap-4">
        <Flag label="BE" active={trade.be_moved} />
        <Flag label="TP1" active={trade.tp1_hit} />
        <Flag label="TP2" active={trade.tp2_hit} />
        <Flag label="TRAILING" active={trade.trailing_active} />
        {trade.opened_at && (
          <span className="font-mono text-[9px] text-atlas-text-dim ml-auto">
            Opened {new Date(trade.opened_at).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false })} EST
          </span>
        )}
      </div>
    </div>
  );
}

function Flag({ label, active }: { label: string; active: boolean }) {
  return (
    <div className={`flex items-center gap-1 font-mono text-[9px] tracking-[1px] uppercase ${active ? "text-atlas-long" : "text-atlas-text-dim"}`}>
      <div className={`w-1.5 h-1.5 rounded-full ${active ? "bg-atlas-long" : "bg-atlas-border"}`} />
      {label}
    </div>
  );
}