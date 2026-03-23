/**
 * frontend/src/pages/Journal.tsx
 * Trade journal with filters, Section 9.3 stat cards, paginated table, expandable rows.
 */
import { useState, useEffect, useCallback } from "react";
import { getTrades, getJournalStats }        from "../lib/api";
import type { TradeRecord, JournalStats }    from "../lib/api";
import { formatPrice, formatPnL, formatRR, gradeColor, formatDateEST } from "../lib/formatters";

const PAGE_SIZE = 20;

type FilterState = {
  direction: string;
  grade:     string;
  outcome:   string;
  from:      string;
  to:        string;
};

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-atlas-surface border border-atlas-border p-3">
      <span className="block font-sans text-[9px] tracking-[2px] text-atlas-text-dim uppercase mb-1">{label}</span>
      <span className="block font-mono text-lg font-bold text-atlas-text-bright">{value}</span>
      {sub && <span className="block font-mono text-[9px] text-atlas-text-dim mt-0.5">{sub}</span>}
    </div>
  );
}

export function Journal() {
  const [stats,      setStats]      = useState<JournalStats | null>(null);
  const [trades,     setTrades]     = useState<TradeRecord[]>([]);
  const [total,      setTotal]      = useState(0);
  const [page,       setPage]       = useState(0);
  const [expanded,   setExpanded]   = useState<string | null>(null);
  const [loading,    setLoading]    = useState(false);
  const [filters,    setFilters]    = useState<FilterState>({
    direction: "", grade: "", outcome: "", from: "", to: "",
  });

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        limit:  PAGE_SIZE,
        offset: page * PAGE_SIZE,
      };
      if (filters.direction) params["direction"] = filters.direction;
      if (filters.grade)     params["grade"]     = filters.grade;
      if (filters.outcome)   params["status"]    = filters.outcome;
      if (filters.from)      params["from"]      = filters.from;
      if (filters.to)        params["to"]        = filters.to;

      const res = await getTrades(params as Parameters<typeof getTrades>[0]);
      setTrades(res.trades);
      setTotal(res.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  useEffect(() => { void fetchTrades(); }, [fetchTrades]);

  useEffect(() => {
    getJournalStats().then(setStats).catch(console.error);
  }, []);

  function outcomeColor(outcome: string | null): string {
    if (!outcome) return "text-atlas-text-dim";
    if (["TP1","TP2","TP3"].includes(outcome)) return "text-atlas-long";
    if (outcome === "SL") return "text-atlas-short";
    if (outcome === "BE") return "text-atlas-neutral";
    return "text-atlas-text-dim";
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-col h-screen bg-atlas-bg overflow-hidden">
      {/* Header */}
      <div className="h-10 flex-shrink-0 flex items-center px-6 border-b border-atlas-border bg-atlas-surface">
        <span className="font-mono text-atlas-accent font-bold tracking-[4px] text-sm uppercase">ATLAS</span>
        <span className="font-mono text-atlas-text-dim text-xs ml-4 tracking-widest">/ JOURNAL</span>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">

        {/* Stat cards */}
        {stats && (
          <div className="grid grid-cols-5 gap-3">
            <StatCard label="Win Rate TP1"   value={`${stats.win_rate_tp1.toFixed(1)}%`}  sub={`Target: 65%+ | Min: 55%`} />
            <StatCard label="Win Rate TP2"   value={`${stats.win_rate_tp2.toFixed(1)}%`}  sub={`Target: 52%+ | Min: 40%`} />
            <StatCard label="Avg R:R"        value={formatRR(stats.avg_rr)}               sub={`Target: 2.3+ | Min: 1.8`} />
            <StatCard label="Expectancy"     value={`${stats.expectancy.toFixed(3)}R`}    sub={`Target: +0.5R | Min: +0.3R`} />
            <StatCard label="Profit Factor"  value={stats.profit_factor.toFixed(2)}       sub={`Target: 1.8+ | Min: 1.4`} />
          </div>
        )}

        {/* Filter row */}
        <div className="flex gap-3 items-center">
          <span className="font-mono text-[9px] tracking-[3px] text-atlas-text-dim uppercase">Filter:</span>
          {([
            { key: "direction", opts: ["","BUY","SELL"], label: "Direction" },
            { key: "grade",     opts: ["","A+","A","B","C"], label: "Grade" },
            { key: "outcome",   opts: ["","TP1","TP2","TP3","SL","BE","OPEN"], label: "Outcome" },
          ] as { key: keyof FilterState; opts: string[]; label: string }[]).map(({ key, opts, label }) => (
            <select
              key={key}
              value={filters[key]}
              onChange={(e) => { setFilters(f => ({ ...f, [key]: e.target.value })); setPage(0); }}
              className="bg-atlas-surface border border-atlas-border font-mono text-xs text-atlas-text-bright px-2 py-1 focus:outline-none focus:border-atlas-accent"
            >
              {opts.map((o) => (
                <option key={o} value={o}>{o || label}</option>
              ))}
            </select>
          ))}
          <input
            type="date"
            value={filters.from}
            onChange={(e) => { setFilters(f => ({ ...f, from: e.target.value })); setPage(0); }}
            className="bg-atlas-surface border border-atlas-border font-mono text-xs text-atlas-text-bright px-2 py-1 focus:outline-none focus:border-atlas-accent"
          />
          <span className="font-mono text-xs text-atlas-text-dim">to</span>
          <input
            type="date"
            value={filters.to}
            onChange={(e) => { setFilters(f => ({ ...f, to: e.target.value })); setPage(0); }}
            className="bg-atlas-surface border border-atlas-border font-mono text-xs text-atlas-text-bright px-2 py-1 focus:outline-none focus:border-atlas-accent"
          />
          <span className="font-mono text-[9px] text-atlas-text-dim ml-auto">
            {total} trades
          </span>
        </div>

        {/* Trade table */}
        <div className="bg-atlas-surface border border-atlas-border overflow-hidden">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-atlas-border">
                {["Date","Dir","Grade","Entry","SL","R:R","SL Pips","Score","Outcome","P&L"].map((h) => (
                  <th key={h} className="text-left font-sans font-normal text-[9px] tracking-[2px] text-atlas-text-dim uppercase px-3 py-2">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={10} className="px-3 py-6 text-center font-mono text-xs text-atlas-text-dim">Loading…</td></tr>
              )}
              {!loading && trades.length === 0 && (
                <tr><td colSpan={10} className="px-3 py-6 text-center font-mono text-xs text-atlas-text-dim">No trades found</td></tr>
              )}
              {!loading && trades.map((t) => (
                <>
                  <tr
                    key={t.id}
                    onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                    className="border-b border-atlas-border hover:bg-atlas-bg cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-2 font-mono text-atlas-text-dim">{t.created_at.slice(0,10)}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${t.direction === "BUY" ? "text-atlas-long" : "text-atlas-short"}`}>{t.direction}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${gradeColor(t.setup_grade)}`}>{t.setup_grade || "—"}</td>
                    <td className="px-3 py-2 font-mono text-atlas-text-bright">{formatPrice(t.entry_price)}</td>
                    <td className="px-3 py-2 font-mono text-atlas-short">{formatPrice(t.sl_price)}</td>
                    <td className="px-3 py-2 font-mono text-atlas-text-bright">{formatRR(t.rr_ratio)}</td>
                    <td className="px-3 py-2 font-mono text-atlas-text-dim">{t.sl_pips?.toFixed(1) ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-atlas-text-bright">{t.confluence_score ?? "—"}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${outcomeColor(t.outcome)}`}>{t.outcome ?? t.status}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${(t.pnl ?? 0) >= 0 ? "text-atlas-long" : "text-atlas-short"}`}>
                      {t.pnl != null ? formatPnL(t.pnl) : "—"}
                    </td>
                  </tr>
                  {expanded === t.id && (
                    <tr key={`${t.id}-expanded`} className="border-b border-atlas-border bg-atlas-bg">
                      <td colSpan={10} className="px-3 py-3">
                        <pre className="font-mono text-[9px] text-atlas-text-dim overflow-x-auto whitespace-pre-wrap max-h-64">
                          {JSON.stringify(t.decision_state, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
              className="font-mono text-xs px-3 py-1 border border-atlas-border text-atlas-text-dim hover:border-atlas-accent hover:text-atlas-accent disabled:opacity-30 transition-colors"
            >
              ← Prev
            </button>
            <span className="font-mono text-xs text-atlas-text-dim">
              {page + 1} / {totalPages}
            </span>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              className="font-mono text-xs px-3 py-1 border border-atlas-border text-atlas-text-dim hover:border-atlas-accent hover:text-atlas-accent disabled:opacity-30 transition-colors"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}