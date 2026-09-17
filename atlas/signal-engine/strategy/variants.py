"""
signal-engine/strategy/variants.py
Phase 5: change one rule at a time and measure what it actually buys.

Every constant in config.py is an assertion until tested. This flips them one
at a time over the full history, scoring each on an in-sample period and an
out-of-sample period that no parameter is ever chosen on.

Candle data and HTF contexts are built once and shared, so a variant costs only
the pipeline pass.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from strategy import asia_range, decision_tree, entry_model, judas_sweep
from strategy import risk_manager, structure as structure_mod
from strategy.backtest import (
    BacktestTrade, build_htf_contexts, compute_stats, run_backtest,
    _get_session_dates,
)

SPLIT = "2021-06-01"          # fixed once; never moved

# A constant may have been imported into several modules, so every copy must be
# patched or the change silently half-applies.
TARGETS: Dict[str, list] = {
    "SWEEP_MIN_PIPS":      [judas_sweep],
    "SWEEP_MAX_PIPS":      [judas_sweep],
    "ASIA_RANGE_MIN_PIPS": [asia_range],
    "ASIA_RANGE_MAX_PIPS": [asia_range],
    "DISPLACEMENT_MULT":   [structure_mod],
    "SL_MAX_PIPS":         [decision_tree, entry_model, risk_manager],
    "MIN_CONFLUENCE":      [decision_tree, risk_manager],
    "MIN_RR":              [decision_tree, risk_manager],
    "ALLOW_DOUBLE_SWEEP":      [judas_sweep],
    "ALLOW_AMBIGUOUS_DOL":     [judas_sweep],
    "BREAKOUT_FILTER_USE_DOL": [judas_sweep],
}

VARIANTS: Dict[str, dict] = {
    "baseline (rules as shipped)":      {},
    # ── sweep stage: rejects 91% of sessions that reach it ───────────────────
    "allow ambiguous Daily DOL":        {"ALLOW_AMBIGUOUS_DOL": True},
    "allow double sweep":               {"ALLOW_DOUBLE_SWEEP": True},
    "breakout filter: drop DOL factor": {"BREAKOUT_FILTER_USE_DOL": False},
    "sweep min 1 pip (was 3)":          {"SWEEP_MIN_PIPS": 1},
    "sweep max 15 pips (was 8)":        {"SWEEP_MAX_PIPS": 15},
    # ── asia range ──────────────────────────────────────────────────────────
    "asia range min 5 (was 10)":        {"ASIA_RANGE_MIN_PIPS": 5},
    "asia range max 60 (was 40)":       {"ASIA_RANGE_MAX_PIPS": 60},
    # ── structure / entry / risk ────────────────────────────────────────────
    "displacement 1.2x (was 1.5)":      {"DISPLACEMENT_MULT": 1.2},
    "SL max 25 pips (was 15)":          {"SL_MAX_PIPS": 25},
    "confluence min 6 (was 10)":        {"MIN_CONFLUENCE": 6},
    "min R:R 1.5 (was 2.0)":            {"MIN_RR": 1.5},
    # ── combinations, to reach a measurable sample ──────────────────────────
    "all sweep filters relaxed":        {"ALLOW_AMBIGUOUS_DOL": True,
                                         "ALLOW_DOUBLE_SWEEP": True,
                                         "BREAKOUT_FILTER_USE_DOL": False},
    "sweep relaxed + wide asia":        {"ALLOW_AMBIGUOUS_DOL": True,
                                         "ALLOW_DOUBLE_SWEEP": True,
                                         "BREAKOUT_FILTER_USE_DOL": False,
                                         "ASIA_RANGE_MIN_PIPS": 5,
                                         "ASIA_RANGE_MAX_PIPS": 60},
    "everything relaxed":               {"ALLOW_AMBIGUOUS_DOL": True,
                                         "ALLOW_DOUBLE_SWEEP": True,
                                         "BREAKOUT_FILTER_USE_DOL": False,
                                         "ASIA_RANGE_MIN_PIPS": 5,
                                         "ASIA_RANGE_MAX_PIPS": 60,
                                         "SWEEP_MIN_PIPS": 1,
                                         "SWEEP_MAX_PIPS": 15,
                                         "SL_MAX_PIPS": 25,
                                         "MIN_CONFLUENCE": 6},
}


def apply(overrides: Dict[str, Any]) -> Dict[str, list]:
    """Set overrides across every module holding a copy. Returns the originals."""
    saved: Dict[str, list] = {}
    for name, value in overrides.items():
        saved[name] = [getattr(m, name) for m in TARGETS[name]]
        for m in TARGETS[name]:
            setattr(m, name, value)
    return saved


def restore(saved: Dict[str, list]) -> None:
    for name, values in saved.items():
        for m, v in zip(TARGETS[name], values):
            setattr(m, name, v)


def split_stats(trades: List[BacktestTrade]) -> dict:
    is_ = [t for t in trades if t.date < SPLIT]
    oos = [t for t in trades if t.date >= SPLIT]
    row = {"n": len(trades)}
    for tag, part in (("is", is_), ("oos", oos)):
        s = compute_stats(part)
        row[f"{tag}_n"] = s.total_trades
        row[f"{tag}_exp"] = s.expectancy_r if s.total_trades else float("nan")
        row[f"{tag}_pf"] = (round(s.profit_factor, 2)
                            if s.total_trades and s.profit_factor != float("inf")
                            else float("nan"))
    return row


def main() -> int:
    from data_pipeline.adapter import load_candle_sets

    start = datetime(2015, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 16, tzinfo=timezone.utc)

    print("loading candles...", flush=True)
    sets = load_candle_sets("EURUSD", "2015-01-01", "2026-09-16", quiet=True)
    m5, m15, h4, d1 = sets["5min"], sets["15min"], sets["4h"], sets["1day"]

    print("building HTF contexts (shared across variants)...", flush=True)
    dates = _get_session_dates(m5, start, end)
    ctxs = build_htf_contexts(dates, d1, h4)
    print(f"{len(dates):,} sessions\n", flush=True)

    rows = []
    for name, overrides in VARIANTS.items():
        saved = apply(overrides)
        try:
            trades, stats = run_backtest(m5, m15, h4, d1, ctxs, {}, start, end)
        finally:
            restore(saved)
        row = split_stats(trades)
        row["name"] = name
        row["wr"] = round(stats.win_rate_tp1, 1) if stats.total_trades else float("nan")
        rows.append(row)
        print(f"  {name:<34} n={row['n']:<5} "
              f"IS {row['is_n']:>4} @ {row['is_exp']:+.3f}R   "
              f"OOS {row['oos_n']:>4} @ {row['oos_exp']:+.3f}R", flush=True)

    print("\n" + "=" * 96)
    print("PHASE 5 — one change at a time. A change counts only if it holds IS *and* OOS.")
    print(f"split at {SPLIT}   ·   exp = mean realised R per executed trade")
    print("=" * 96)
    print(f"  {'variant':<34}{'n':>5}{'wr%':>7}{'IS n':>6}{'IS exp':>9}"
          f"{'IS pf':>7}{'OOS n':>7}{'OOS exp':>9}{'OOS pf':>8}")
    print("  " + "-" * 92)
    for r in rows:
        print(f"  {r['name']:<34}{r['n']:>5}{r['wr']:>7}{r['is_n']:>6}"
              f"{r['is_exp']:>9.3f}{r['is_pf']:>7}{r['oos_n']:>7}"
              f"{r['oos_exp']:>9.3f}{r['oos_pf']:>8}")
    print("=" * 96)

    import csv
    from pathlib import Path
    out = Path(__file__).resolve().parent.parent / "results/variants.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"written to results/variants.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
