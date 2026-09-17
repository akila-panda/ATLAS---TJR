/**
 * frontend/src/pages/Journal.tsx
 * Trade journal — stat cards, filters, paginated table, expandable rows.
 */
import { useState, useEffect, useCallback } from "react";
import { getTrades, getJournalStats }        from "../lib/api";
import type { TradeRecord, JournalStats }    from "../lib/api";
import { formatPrice, formatPnL, formatRR, gradeColor, formatDateEST } from "../lib/formatters";
import "./Journal.css";

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
    <div className="stat-card">
      <span className="stat-card-label">{label}</span>
      <span className="stat-card-value">{value}</span>
      {sub && <span className="stat-card-sub">{sub}</span>}
    </div>
  );
}

function outcomeClass(outcome: string | null): string {
  if (!outcome) return "td-dim";
  if (["TP1", "TP2", "TP3"].includes(outcome)) return "td-long";
  if (outcome === "SL") return "td-short";
  if (outcome === "BE") return "td-neutral";
  return "td-dim";
}

export function Journal() {
  const [stats,    setStats]    = useState<JournalStats | null>(null);
  const [trades,   setTrades]   = useState<TradeRecord[]>([]);
  const [total,    setTotal]    = useState(0);
  const [page,     setPage]     = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [filters,  setFilters]  = useState<FilterState>({
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

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="journal">

      {/* Header */}
      <header className="journal-header">
        <span className="journal-header-brand">ATLAS</span>
        <span className="journal-header-crumb">/ Journal</span>
      </header>

      <div className="journal-body">

        {/* Stat cards */}
        {stats && (
          <div className="journal-stats">
            <StatCard label="Win Rate TP1"  value={`${stats.win_rate_tp1.toFixed(1)}%`}  sub="Target: 65%+ | Min: 55%" />
            <StatCard label="Win Rate TP2"  value={`${stats.win_rate_tp2.toFixed(1)}%`}  sub="Target: 52%+ | Min: 40%" />
            <StatCard label="Avg R:R"       value={formatRR(stats.avg_rr)}               sub="Target: 2.3+ | Min: 1.8" />
            <StatCard label="Expectancy"    value={`${stats.expectancy.toFixed(3)}R`}    sub="Target: +0.5R | Min: +0.3R" />
            <StatCard label="Profit Factor" value={stats.profit_factor.toFixed(2)}       sub="Target: 1.8+ | Min: 1.4" />
          </div>
        )}

        {/* Filters */}
        <div className="journal-filters">
          <span className="journal-filter-label">Filter:</span>

          {([
            { key: "direction", opts: ["", "BUY", "SELL"],                    label: "Direction" },
            { key: "grade",     opts: ["", "A+", "A", "B", "C"],              label: "Grade" },
            { key: "outcome",   opts: ["", "TP1", "TP2", "TP3", "SL", "BE", "OPEN"], label: "Outcome" },
          ] as { key: keyof FilterState; opts: string[]; label: string }[]).map(({ key, opts, label }) => (
            <select
              key={key}
              value={filters[key]}
              onChange={(e) => { setFilters(f => ({ ...f, [key]: e.target.value })); setPage(0); }}
              className="filter-select"
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
            className="filter-date"
          />
          <span className="journal-filter-sep">–</span>
          <input
            type="date"
            value={filters.to}
            onChange={(e) => { setFilters(f => ({ ...f, to: e.target.value })); setPage(0); }}
            className="filter-date"
          />

          <span className="journal-count">{total} trades</span>
        </div>

        {/* Table */}
        <div className="journal-table-wrapper">
          <table className="journal-table">
            <thead>
              <tr>
                {["Date", "Dir", "Grade", "Entry", "SL", "R:R", "SL Pips", "Score", "Outcome", "P&L"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={10} className="journal-table-empty">Loading…</td></tr>
              )}
              {!loading && trades.length === 0 && (
                <tr><td colSpan={10} className="journal-table-empty">No trades found</td></tr>
              )}
              {!loading && trades.map((t) => (
                <>
                  <tr key={t.id} onClick={() => setExpanded(expanded === t.id ? null : t.id)}>
                    <td className="td-dim">{t.created_at.slice(0, 10)}</td>
                    <td className={t.direction === "BUY" ? "td-long" : "td-short"}>{t.direction}</td>
                    <td className={gradeClass(t.setup_grade)}>{t.setup_grade || "—"}</td>
                    <td className="td-bright">{formatPrice(t.entry_price)}</td>
                    <td className="td-short">{formatPrice(t.sl_price)}</td>
                    <td className="td-bright">{formatRR(t.rr_ratio)}</td>
                    <td className="td-dim">{t.sl_pips?.toFixed(1) ?? "—"}</td>
                    <td className="td-bright">{t.confluence_score ?? "—"}</td>
                    <td className={outcomeClass(t.outcome)}>{t.outcome ?? t.status}</td>
                    <td className={(t.pnl ?? 0) >= 0 ? "td-long" : "td-short"}>
                      {t.pnl != null ? formatPnL(t.pnl) : "—"}
                    </td>
                  </tr>
                  {expanded === t.id && (
                    <tr key={`${t.id}-exp`} className="journal-expanded-row">
                      <td colSpan={10}>
                        <pre className="journal-expanded-pre">
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
          <div className="journal-pagination">
            <button
              className="pagination-btn"
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(0, p - 1))}
            >← Prev</button>
            <span className="pagination-info">{page + 1} / {totalPages}</span>
            <button
              className="pagination-btn"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            >Next →</button>
          </div>
        )}

      </div>
    </div>
  );
}

function gradeClass(grade: string | null): string {
  if (!grade) return "td-dim";
  if (grade === "A+") return "td-long";
  if (grade === "A")  return "td-accent";
  if (grade === "B")  return "td-neutral";
  return "td-short";
}
