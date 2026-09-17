"""
signal-engine/strategy/funnel.py
Where do sessions die?

Runs the same bar-by-bar pipeline as backtest.py, but records the furthest
stage each session reached and why it stopped. Answers whether a low trade
count is a real edge filter or an over-tight gate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List

import pytz

from models.candle import Candle
from strategy.backtest import (
    CandleIndex, _get_session_dates, build_htf_contexts, _utc,
    _null_fvg, _null_ob,
)
from strategy.asia_range import detect_asia_range
from strategy.judas_sweep import detect_sweep
from strategy.structure import detect_post_sweep_structure
from strategy.fvg import detect_fvg
from strategy.order_block import detect_ob
from strategy.entry_model import calculate_entry
from strategy.confluence_score import score_confluence
from strategy.decision_tree import run_decision_tree
from config import ACCOUNT_BALANCE, LKZ_START_EST, ENTRY_EXPIRY_H, ENTRY_EXPIRY_M

EST = pytz.timezone("America/New_York")

STAGES = [
    "1 no session data",
    "2 asia range invalid",
    "3 sweep invalid",
    "4 no 15M CHoCH",
    "5 no displacement",
    "6 no entry zone",
    "7 decision tree rejected",
    "8 ENTER",
]


def analyse(m5: List[Candle], m15: List[Candle], h4: List[Candle],
            d1: List[Candle], start: datetime, end: datetime):
    idx5, idx15 = CandleIndex(m5), CandleIndex(m15)
    dates = _get_session_dates(m5, start, end)
    ctxs = build_htf_contexts(dates, d1, h4)

    stage_counts = Counter()
    reasons = Counter()
    dt_nodes = Counter()

    for d in dates:
        a0 = EST.localize(datetime.combine(d, datetime.min.time()).replace(hour=20))
        nd = d + timedelta(days=1)
        z = EST.localize(datetime.combine(nd, datetime.min.time()).replace(hour=8))
        lkz_open = EST.localize(datetime.combine(nd, datetime.min.time())
                                .replace(hour=LKZ_START_EST))
        expiry = EST.localize(datetime.combine(nd, datetime.min.time())
                              .replace(hour=ENTRY_EXPIRY_H, minute=ENTRY_EXPIRY_M))

        s5, s15 = idx5.slice(a0, z), idx15.slice(a0, z)
        if len(s5) < 20:
            stage_counts["1 no session data"] += 1
            continue

        ctx = ctxs.get(d.strftime("%Y-%m-%d"), {"dol_direction": "AMBIGUOUS"})
        best, why = 2, "ASIA_RANGE_NO_CANDLES"

        for i, bar in enumerate(s5):
            bc = _utc(bar.time) + timedelta(minutes=5)
            if bc < lkz_open:
                continue
            if bc >= expiry:
                break
            v5 = s5[: i + 1]
            v15 = [c for c in s15 if _utc(c.time) + timedelta(minutes=15) <= bc]
            if len(v5) < 20:
                continue

            asia = detect_asia_range(v5, bc)
            if not asia.is_valid:
                best, why = max(best, 2), asia.invalid_reason or "ASIA_INVALID"
                continue
            sweep = detect_sweep(v5, asia, ctx, bc)
            if not sweep.is_valid:
                if best <= 3:
                    best, why = 3, sweep.invalid_reason or "SWEEP_INVALID"
                continue
            st = detect_post_sweep_structure(v5, v15, sweep)
            if not st.choch_15m:
                best, why = max(best, 4), "NO_15M_CHOCH"
                continue
            if not st.displacement:
                best, why = max(best, 5), "NO_DISPLACEMENT"
                continue
            fvg = detect_fvg(v5, sweep, st, bc)
            ob = detect_ob(v5, sweep, st)
            entry = calculate_entry(sweep, asia, fvg, ob, ctx, ACCOUNT_BALANCE) \
                if (fvg.found or ob.found) else None
            if entry is None:
                best, why = max(best, 6), "NO_ENTRY_ZONE"
                continue
            conf = score_confluence(asia, sweep, st, fvg, ctx, [], sweep.sweep_time)
            dtree = run_decision_tree(
                news_blocked=False, asia=asia, sweep=sweep, structure=st, fvg=fvg,
                ob_found=ob.found, entry_sl_pips=entry.sl_pips,
                entry_rr_ratio=entry.rr_ratio, required_rr=asia.required_rr,
                confluence=conf, risk_state={"session_terminated": False},
                entry_lot_size=entry.lot_size, now_utc=bc,
            )
            if dtree.outcome == "ENTER":
                best, why = 8, "ENTER"
                break
            best, why = max(best, 7), dtree.reason

        stage_counts[STAGES[best - 1]] += 1
        reasons[why] += 1
        if best == 7:
            dt_nodes[why] += 1

    return stage_counts, reasons, dt_nodes


def main() -> int:
    from data_pipeline.adapter import load_candle_sets
    import argparse

    ap = argparse.ArgumentParser(prog="python -m strategy.funnel")
    ap.add_argument("--from", dest="start", default="2015-01-01")
    ap.add_argument("--to", dest="end", default="2026-09-16")
    a = ap.parse_args()

    sets = load_candle_sets("EURUSD", a.start, a.end, quiet=True)
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)

    stages, reasons, nodes = analyse(
        sets["5min"], sets["15min"], sets["4h"], sets["1day"], start, end
    )
    total = sum(stages.values())

    print("=" * 70)
    print(f"SESSION FUNNEL — {total:,} sessions, {a.start} to {a.end}")
    print("=" * 70)
    print("\n  furthest stage reached:")
    running = total
    for st in STAGES:
        n = stages.get(st, 0)
        if n:
            print(f"    {st:<28}{n:>6}  ({n/total*100:5.1f}%)   survived to here: {running:,}")
        running -= n

    print("\n  terminal reason (top 12):")
    for why, n in reasons.most_common(12):
        print(f"    {why:<34}{n:>6}  ({n/total*100:5.1f}%)")

    if nodes:
        print("\n  decision-tree rejections:")
        for why, n in nodes.most_common():
            print(f"    {why:<34}{n:>6}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
