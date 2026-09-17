"""
signal-engine/strategy/backtest.py
Backtesting & Journaling Framework — Section 9 of TJR Operational Document.
Runs the full strategy pipeline over historical candle data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import pytz

from models.candle import Candle, CandleBuffer
from strategy.asia_range import detect_asia_range
from strategy.judas_sweep import detect_sweep
from strategy.structure import detect_post_sweep_structure
from strategy.fvg import detect_fvg
from strategy.order_block import detect_ob
from strategy.confluence_score import score_confluence
from strategy.decision_tree import run_decision_tree
from strategy.entry_model import calculate_entry
from strategy.risk_manager import validate_final
from strategy.news_filter import is_news_blocked
from config import (
    ACCOUNT_BALANCE, MIN_RR, SL_MAX_PIPS,
    TP1_CLOSE_PCT, TP2_CLOSE_PCT, PIP_SIZE,
    LKZ_START_EST, ENTRY_EXPIRY_H, ENTRY_EXPIRY_M,
)

EST = pytz.timezone("America/New_York")


@dataclass
class BacktestTrade:
    """
    Single backtested trade record — matches Section 9.1 journal fields exactly.
    Two traders journaling the same trade produce identical values for every field.
    """
    date:                str        # YYYY-MM-DD
    session:             str = "LKZ"
    asia_range_pips:     float = 0.0
    asia_high:           float = 0.0
    asia_low:            float = 0.0
    judas_direction:     str = ""   # "BSL" | "SSL"
    sweep_time_est:      str = ""   # HH:MM
    sweep_extension_pips: float = 0.0
    htf_bias:            str = ""   # "BULLISH" | "BEARISH" | "AMBIGUOUS"
    trade_direction:     str = ""   # "LONG" | "SHORT"
    entry_method:        str = ""   # "FVG_LIMIT" | "OB_LIMIT" | "MSS_MARKET"
    entry_price:         float = 0.0
    sl_price:            float = 0.0
    sl_distance_pips:    float = 0.0
    tp1_price:           float = 0.0
    tp2_price:           float = 0.0
    tp3_price:           float = 0.0
    lot_size:            float = 0.0
    risk_usd:            float = 0.0
    confluence_score:    int = 0
    setup_grade:         str = ""   # "A+" | "A" | "B"
    outcome:             str = ""   # "TP1" | "TP2" | "TP3" | "BE" | "SL" | "MISSED"
    rr_achieved:         float = 0.0
    pnl_usd:             float = 0.0
    invalidation_hit:    str = "NO"  # "NO" | reason code
    rule_violation:      str = "NO"  # "NO" | rule reference
    screenshot_ref:      str = ""    # filename reference

    # Decision tree state snapshot (for review)
    decision_state:      Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestStats:
    """Section 9.3 statistical thresholds."""
    total_trades:        int   = 0
    tp1_hits:            int   = 0
    tp2_hits:            int   = 0
    tp3_hits:            int   = 0
    sl_hits:             int   = 0
    be_hits:             int   = 0
    missed:              int   = 0
    no_trades:           int   = 0

    win_rate_tp1:        float = 0.0   # min 55%, target 65%
    win_rate_tp2:        float = 0.0   # min 40%, target 52%
    avg_rr_achieved:     float = 0.0   # min 1.8, target 2.3
    expectancy_r:        float = 0.0   # min +0.3R, target +0.5R
    profit_factor:       float = 0.0   # min 1.4, target 1.8
    max_consecutive_losses: int = 0

    total_pnl_usd:       float = 0.0
    gross_profit:        float = 0.0
    gross_loss:          float = 0.0

    # Threshold pass/fail (Section 9.3)
    passes_edge_threshold: bool = False
    edge_notes:          List[str] = field(default_factory=list)


def run_backtest(
    all_candles_m5:  List[Candle],
    all_candles_m15: List[Candle],
    all_candles_h4:  List[Candle],
    all_candles_d1:  List[Candle],
    htf_contexts:    Dict[str, dict],   # date_str → htf_context dict
    news_by_date:    Dict[str, list],   # date_str → news events list
    start_date:      datetime,
    end_date:        datetime,
    spread_pips:     float = 1.5,       # Rule 9.4b: fixed 1.5 pip spread simulation
) -> tuple[List[BacktestTrade], BacktestStats]:
    """
    Runs the full TJR pipeline over a historical candle range.

    Section 9.4 standardisation:
    - Spread: fixed 1.5 pips applied to entry and exit calculations
    - Bar detection: M5 wick-to-wick measurements
    - Missed trades: setup valid but FVG not filled → logged as MISSED

    Args:
        all_candles_m5:  Full M5 history (oldest-first).
        all_candles_m15: Full M15 history.
        all_candles_h4:  Full H4 history.
        all_candles_d1:  Full D1 history.
        htf_contexts:    Pre-computed HTF context per date.
        news_by_date:    News events per date.
        start_date:      Backtest start (UTC).
        end_date:        Backtest end (UTC).
        spread_pips:     Simulated spread (Rule 9.4b).

    Returns:
        (list of BacktestTrade, BacktestStats)
    """
    trades:   List[BacktestTrade] = []
    no_trade_count = 0
    spread = spread_pips * PIP_SIZE

    idx_m5  = CandleIndex(all_candles_m5)
    idx_m15 = CandleIndex(all_candles_m15)
    idx_h4  = CandleIndex(all_candles_h4)
    idx_d1  = CandleIndex(all_candles_d1)

    # Group M5 candles by session date (EST date at 20:00 start)
    session_dates = _get_session_dates(all_candles_m5, start_date, end_date)

    for session_date in session_dates:
        date_str = session_date.strftime("%Y-%m-%d")

        # Slice candles for this session window
        # Asia window: session_date 20:00 EST to next day 08:00 EST
        asia_start = EST.localize(
            datetime.combine(session_date, datetime.min.time()).replace(hour=20)
        )
        lkz_end    = EST.localize(
            datetime.combine(
                session_date + timedelta(days=1),
                datetime.min.time()
            ).replace(hour=8)
        )

        session_m5  = idx_m5.slice(asia_start, lkz_end)
        session_m15 = idx_m15.slice(asia_start, lkz_end)
        session_h4  = idx_h4.slice(asia_start - timedelta(days=30), lkz_end)
        session_d1  = idx_d1.slice(asia_start - timedelta(days=60), lkz_end)

        if len(session_m5) < 20:
            no_trade_count += 1
            continue

        htf_ctx   = htf_contexts.get(date_str, {"dol_direction": "AMBIGUOUS"})
        news_evs  = news_by_date.get(date_str, [])

        # ── Step through the session one M5 close at a time ──────────────────
        # Live ATLAS runs run_strategy_pipeline() on every M5 candle close, so
        # the backtest must too. Evaluating the whole session at once would
        # (a) pin now_utc past the 05:30 EST expiry so node 14 could never
        # pass, and (b) let detect_sweep see candles that had not yet closed.
        # The session runs 20:00 EST -> 08:00 EST the NEXT calendar day, so the
        # kill-zone bounds must be absolute datetimes. Comparing bare hours
        # breaks across midnight (hour 20 is not < 2, and 20 > 5).
        next_day = session_date + timedelta(days=1)
        lkz_open = EST.localize(
            datetime.combine(next_day, datetime.min.time())
            .replace(hour=LKZ_START_EST)
        )
        entry_expiry = EST.localize(
            datetime.combine(next_day, datetime.min.time())
            .replace(hour=ENTRY_EXPIRY_H, minute=ENTRY_EXPIRY_M)
        )

        decision = None
        for i, bar in enumerate(session_m5):
            bar_close = _utc(bar.time) + timedelta(minutes=5)

            # Nothing to decide before the kill zone opens.
            if bar_close < lkz_open:
                continue
            # Rule 4.2d: the limit-order window shuts at 05:30 EST.
            if bar_close >= entry_expiry:
                break

            # Only candles that have actually closed are visible.
            vis_m5  = session_m5[: i + 1]
            vis_m15 = [c for c in session_m15
                       if _utc(c.time) + timedelta(minutes=15) <= bar_close]
            if len(vis_m5) < 20:
                continue

            asia = detect_asia_range(vis_m5, bar_close)
            if not asia.is_valid:
                continue

            sweep = detect_sweep(vis_m5, asia, htf_ctx, bar_close)
            if not sweep.is_valid:
                continue

            structure = detect_post_sweep_structure(vis_m5, vis_m15, sweep)
            fvg = detect_fvg(vis_m5, sweep, structure, bar_close) \
                  if structure.choch_15m else _null_fvg()
            ob  = detect_ob(vis_m5, sweep, structure) \
                  if structure.choch_15m else _null_ob()

            entry = calculate_entry(sweep, asia, fvg, ob, htf_ctx, ACCOUNT_BALANCE) \
                    if (fvg.found or ob.found) else None
            if entry is None:
                continue

            confluence = score_confluence(
                asia, sweep, structure, fvg, htf_ctx, news_evs, sweep.sweep_time
            )
            risk_state = {"session_terminated": False, "daily_loss_pct": 0.0}

            dt = run_decision_tree(
                news_blocked=is_news_blocked(news_evs, bar_close),
                asia=asia,
                sweep=sweep,
                structure=structure,
                fvg=fvg,
                ob_found=ob.found,
                entry_sl_pips=entry.sl_pips,
                entry_rr_ratio=entry.rr_ratio,
                required_rr=asia.required_rr,
                confluence=confluence,
                risk_state=risk_state,
                entry_lot_size=entry.lot_size,
                now_utc=bar_close,
            )
            if dt.outcome == "ENTER":
                decision = (i, asia, sweep, structure, fvg, entry, confluence, dt)
                break

        if decision is None:
            no_trade_count += 1
            continue

        bar_idx, asia, sweep, structure, fvg, entry, confluence, dt = decision

        # Apply spread to entry (Section 9.4b)
        direction = entry.direction
        actual_entry = (entry.entry_price + spread if direction == "BUY"
                        else entry.entry_price - spread)

        # Simulate outcome against M5 candles AFTER the decision bar. The limit
        # order may never be touched, in which case _simulate_outcome returns
        # MISSED (Rule 9.4d).
        post_entry = session_m5[bar_idx + 1:]

        outcome, rr_achieved, pnl_usd = _simulate_outcome(
            direction, actual_entry, entry.sl_price,
            entry.tp1_price, entry.tp2_price, entry.tp3_price,
            post_entry, entry.lot_size, spread,
        )

        bt = BacktestTrade(
            date=date_str,
            asia_range_pips=asia.range_pips,
            asia_high=asia.asia_high,
            asia_low=asia.asia_low,
            judas_direction=sweep.direction or "",
            sweep_time_est=sweep.sweep_time.strftime("%H:%M") if sweep.sweep_time else "",
            sweep_extension_pips=sweep.extension_pips,
            htf_bias=htf_ctx.get("dol_direction", "AMBIGUOUS"),
            trade_direction="LONG" if direction == "BUY" else "SHORT",
            entry_method=entry.entry_method,
            entry_price=round(actual_entry, 5),
            sl_price=round(entry.sl_price, 5),
            sl_distance_pips=entry.sl_pips,
            tp1_price=round(entry.tp1_price, 5),
            tp2_price=round(entry.tp2_price, 5),
            tp3_price=round(entry.tp3_price, 5),
            lot_size=entry.lot_size,
            risk_usd=entry.risk_usd,
            confluence_score=confluence.total,
            setup_grade=confluence.grade,
            outcome=outcome,
            rr_achieved=rr_achieved,
            pnl_usd=pnl_usd,
            decision_state={
                "nodes": [
                    {"id": n.node_id, "name": n.name, "passed": n.passed,
                     "reason": n.reason}
                    for n in dt.nodes
                ],
                "confluence_factors": confluence.factors,
                "confluence_reasons": confluence.reasons,
            },
        )
        trades.append(bt)

    stats = compute_stats(trades, no_trade_count)
    return trades, stats


def compute_stats(
    trades:        List[BacktestTrade],
    no_trade_count: int = 0,
) -> BacktestStats:
    """
    Section 9.3: Compute statistical edge metrics.
    Minimum sample: 50 trades before conclusions are drawn.
    """
    stats = BacktestStats(
        total_trades=len(trades),
        no_trades=no_trade_count,
    )
    if not trades:
        return stats

    consecutive = 0
    max_consec   = 0
    gross_profit = 0.0
    gross_loss   = 0.0

    for t in trades:
        if t.outcome in ("TP1", "TP2", "TP3"):
            stats.tp1_hits += 1
            gross_profit   += t.pnl_usd
            consecutive    = 0
        if t.outcome in ("TP2", "TP3"):
            stats.tp2_hits += 1
        if t.outcome == "TP3":
            stats.tp3_hits += 1
        if t.outcome == "SL":
            stats.sl_hits += 1
            gross_loss     += abs(t.pnl_usd)
            consecutive    += 1
            max_consec      = max(max_consec, consecutive)
        if t.outcome == "BE":
            stats.be_hits  += 1
            consecutive     = 0
        if t.outcome == "MISSED":
            stats.missed   += 1

    n = stats.total_trades
    traded = n - stats.missed

    stats.win_rate_tp1   = stats.tp1_hits / traded * 100.0 if traded > 0 else 0.0
    stats.win_rate_tp2   = stats.tp2_hits / traded * 100.0 if traded > 0 else 0.0
    stats.avg_rr_achieved = (
        sum(t.rr_achieved for t in trades if t.outcome not in ("MISSED",)) /
        max(traded, 1)
    )
    stats.total_pnl_usd  = sum(t.pnl_usd for t in trades)
    stats.gross_profit   = gross_profit
    stats.gross_loss     = gross_loss
    stats.profit_factor  = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )
    stats.max_consecutive_losses = max_consec

    # Expectancy is simply the mean realised R across executed trades. The
    # previous formula substituted avg_win = 2.0 whenever avg_rr_achieved was
    # negative, which manufactured a positive expectancy from losing trades.
    executed = [t for t in trades if t.outcome != "MISSED"]
    stats.expectancy_r = round(
        sum(t.rr_achieved for t in executed) / len(executed), 3
    ) if executed else 0.0

    # Section 9.3 pass/fail
    notes = []
    passes = True
    if stats.win_rate_tp1 < 55.0:
        passes = False
        notes.append(f"Win rate {stats.win_rate_tp1:.1f}% < 55% minimum")
    if stats.avg_rr_achieved < 1.8:
        passes = False
        notes.append(f"Avg R:R {stats.avg_rr_achieved:.2f} < 1.8 minimum")
    if stats.expectancy_r < 0.3:
        passes = False
        notes.append(f"Expectancy {stats.expectancy_r:.3f}R < 0.3R minimum")
    if stats.profit_factor < 1.4:
        passes = False
        notes.append(f"Profit factor {stats.profit_factor:.2f} < 1.4 minimum")
    if traded < 50:
        notes.append(f"Sample size {traded} < 50 — insufficient for edge confirmation")

    stats.passes_edge_threshold = passes
    stats.edge_notes = notes
    return stats


# ─── Private simulation helpers ───────────────────────────────────────────────

def _simulate_outcome(
    direction:   str,
    entry:       float,
    sl:          float,
    tp1:         float,
    tp2:         float,
    tp3:         float,
    candles:     List[Candle],
    lot_size:    float,
    spread:      float,
) -> tuple[str, float, float]:
    """
    Forward-simulate the trade, modelling the partial-exit ladder that
    trade_manager.py actually runs live:

      Rule 6.2c  TP1 hit -> close TP1_CLOSE_PCT (40%), move SL to breakeven
      Rule 6.3   TP2 hit -> close TP2_CLOSE_PCT (35% of original), trail runner
      Rule 6.4   remaining 25% runs to TP3

    Returns (outcome, realised_R, pnl_usd) where realised_R is the position-
    weighted R multiple — comparable across trades, unlike the previous
    implementation which returned R for TP outcomes and raw pips for SL.

    Rule 9.4d: if the limit is never touched, the trade is MISSED.
    Intrabar ambiguity resolves against us: a bar spanning both stop and target
    is treated as the stop.
    """
    is_long = direction == "BUY"
    risk = abs(entry - sl)
    if risk <= 0:
        return "MISSED", 0.0, 0.0

    risk_usd = (risk / PIP_SIZE) * 10.0 * lot_size     # $10/pip/standard lot
    r_of = lambda px: (px - entry) / risk if is_long else (entry - px) / risk

    p1 = TP1_CLOSE_PCT / 100.0                          # 0.40
    p2 = TP2_CLOSE_PCT / 100.0                          # 0.35
    p3 = 1.0 - p1 - p2                                  # 0.25

    filled = False
    tp1_hit = tp2_hit = False
    stop = sl
    realised = 0.0
    remaining = 1.0

    for c in candles:
        if not filled:
            # Limit order at `entry`; long fills on a dip, short on a rally.
            if (is_long and c.low <= entry) or (not is_long and c.high >= entry):
                filled = True
            else:
                continue

        hit_stop = c.low <= stop if is_long else c.high >= stop
        if hit_stop:
            realised += remaining * r_of(stop)
            outcome = ("TP2" if tp2_hit else "TP1" if tp1_hit
                       else ("BE" if abs(r_of(stop)) < 1e-9 else "SL"))
            return outcome, round(realised, 3), round(realised * risk_usd, 2)

        if not tp1_hit and ((is_long and c.high >= tp1) or
                            (not is_long and c.low <= tp1)):
            realised += p1 * r_of(tp1)
            remaining -= p1
            tp1_hit = True
            stop = entry                                # Rule 6.2c: SL -> BE

        if tp1_hit and not tp2_hit and ((is_long and c.high >= tp2) or
                                        (not is_long and c.low <= tp2)):
            realised += p2 * r_of(tp2)
            remaining -= p2
            tp2_hit = True

        if tp2_hit and ((is_long and c.high >= tp3) or
                        (not is_long and c.low <= tp3)):
            realised += p3 * r_of(tp3)
            return "TP3", round(realised, 3), round(realised * risk_usd, 2)

    if not filled:
        return "MISSED", 0.0, 0.0

    # Session ended with the position still open — close at the last price
    # (Rule 8.2.4 kills any open trade at the NY open).
    realised += remaining * r_of(candles[-1].close)
    outcome = "TP2" if tp2_hit else "TP1" if tp1_hit else "BE"
    return outcome, round(realised, 3), round(realised * risk_usd, 2)

def _get_session_dates(candles: List[Candle], start: datetime, end: datetime):
    """Return unique EST dates within the backtest range that have M5 data."""
    seen = set()
    dates = []
    for c in candles:
        if c.time.tzinfo is None:
            c_utc = c.time.replace(tzinfo=timezone.utc)
        else:
            c_utc = c.time
        if c_utc < start.replace(tzinfo=timezone.utc) or \
           c_utc > end.replace(tzinfo=timezone.utc):
            continue
        c_est  = c_utc.astimezone(EST)
        d      = c_est.date()
        if d not in seen:
            seen.add(d)
            dates.append(d)
    return sorted(dates)


class CandleIndex:
    """
    A candle list plus a parallel array of UTC open times, so a session slice
    is a binary search instead of a full scan.

    The naive version rescanned all 875k M5 candles for every one of ~3,000
    sessions — about 3.6 billion iterations across the four timeframes, which
    dominated total runtime. Phase 5 re-runs the whole backtest per parameter
    variant, so this has to be cheap.
    """

    __slots__ = ("candles", "times")

    def __init__(self, candles: List[Candle]) -> None:
        self.candles = candles
        self.times = [_utc(c.time) for c in candles]

    def slice(self, start: datetime, end: datetime) -> List[Candle]:
        """Candles whose open time falls within [start, end)."""
        lo = bisect_left(self.times, start.astimezone(timezone.utc))
        hi = bisect_left(self.times, end.astimezone(timezone.utc))
        return self.candles[lo:hi]

    def upto(self, cutoff: datetime, limit: int) -> List[Candle]:
        """The last `limit` candles that had closed by `cutoff`."""
        hi = bisect_right(self.times, cutoff.astimezone(timezone.utc))
        return self.candles[max(0, hi - limit):hi]


def _slice_candles(candles: List[Candle], start: datetime, end: datetime) -> List[Candle]:
    """Return candles whose open time falls within [start, end). Kept for callers
    that hold a bare list; prefer CandleIndex.slice in hot loops."""
    return CandleIndex(candles).slice(start, end)


def _null_sweep():
    from strategy.judas_sweep import SweepResult
    return SweepResult(detected=False, is_valid=False, invalid_reason="SKIPPED")

def _null_structure():
    from strategy.structure import StructureResult
    return StructureResult()

def _null_fvg():
    from strategy.fvg import FVGResult
    return FVGResult(found=False)

def _null_ob():
    from strategy.order_block import OBResult
    return OBResult(found=False)

# ─── CLI runner (Phase 2) ─────────────────────────────────────────────────────
# SETUP.md 9 documents `python -m strategy.backtest`, but the module had no
# __main__, no argparse and no data loader. This supplies all three.

def build_htf_contexts(
    session_dates: List[Any],
    candles_d1:    List[Candle],
    candles_h4:    List[Candle],
) -> Dict[str, dict]:
    """
    Pre-compute the Daily/4H context for every session, using only candles that
    had already closed by that session's Asia open. No look-ahead.
    """
    from strategy.htf_context import compute_htf_context

    idx_d1 = CandleIndex(candles_d1)
    idx_h4 = CandleIndex(candles_h4)

    contexts: Dict[str, dict] = {}
    for d in session_dates:
        cutoff = EST.localize(
            datetime.combine(d, datetime.min.time()).replace(hour=20)
        ).astimezone(timezone.utc)

        d1 = idx_d1.upto(cutoff, 60)
        h4 = idx_h4.upto(cutoff, 50)
        if len(d1) < 5:
            contexts[d.strftime("%Y-%m-%d")] = {"dol_direction": "AMBIGUOUS"}
            continue
        contexts[d.strftime("%Y-%m-%d")] = compute_htf_context(d1, h4).to_dict()
    return contexts


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m strategy.backtest",
        description="Backtest the TJR strategy over historical EUR/USD data.",
    )
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--from", dest="start", default="2015-01-01")
    ap.add_argument("--to",   dest="end",   default="2026-09-16")
    ap.add_argument("--spread", type=float, default=1.5,
                    help="simulated spread in pips (Rule 9.4b)")
    ap.add_argument("--out", default="results/backtest_trades.csv")
    a = ap.parse_args()

    from data_pipeline.adapter import load_candle_sets

    sets = load_candle_sets(a.symbol, a.start, a.end)
    m5, m15, h4, d1 = (sets["5min"], sets["15min"], sets["4h"], sets["1day"])

    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end   = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)

    session_dates = _get_session_dates(m5, start, end)
    print(f"\n  {len(session_dates):,} candidate sessions")
    print("  building HTF context per session (no look-ahead)...")
    htf_contexts = build_htf_contexts(session_dates, d1, h4)

    # No historical economic calendar is available, so the news filter (node 1)
    # always passes. The backtest therefore sees MORE sessions than live ATLAS
    # would — live blocks red-folder sessions under Rule 7.4a.
    news_by_date: Dict[str, list] = {}

    print("  running strategy pipeline...\n")
    trades, stats = run_backtest(
        m5, m15, h4, d1, htf_contexts, news_by_date, start, end, a.spread
    )

    print_report(trades, stats)

    if trades:
        out = Path(__file__).resolve().parent.parent / a.out
        out.parent.mkdir(parents=True, exist_ok=True)
        import csv as _csv
        with out.open("w", newline="") as fh:
            w = _csv.writer(fh)
            fields = [f for f in vars(trades[0]) if f != "decision_state"]
            w.writerow(fields)
            for t in trades:
                w.writerow([getattr(t, f) for f in fields])
        print(f"\n  {len(trades)} trades written to {a.out}")
    return 0


def print_report(trades: List[BacktestTrade], stats: BacktestStats) -> None:
    """Section 9.3 metrics against the SETUP.md 10 go-live thresholds."""
    print("=" * 70)
    print("TJR BACKTEST — Section 9.3 metrics")
    print("=" * 70)
    print(f"  sessions evaluated     {stats.total_trades + stats.no_trades:,}")
    print(f"  NO_TRADE sessions      {stats.no_trades:,}")
    print(f"  trades taken           {stats.total_trades:,}")
    if not stats.total_trades:
        print("\n  No trades. Nothing to measure.")
        print("=" * 70)
        return

    rows = [
        ("win rate TP1",   f"{stats.win_rate_tp1:.1f}%",  "55%",   stats.win_rate_tp1 >= 55),
        ("win rate TP2",   f"{stats.win_rate_tp2:.1f}%",  "40%",   stats.win_rate_tp2 >= 40),
        ("avg R:R",        f"{stats.avg_rr_achieved:.2f}", "1.8",  stats.avg_rr_achieved >= 1.8),
        ("expectancy",     f"{stats.expectancy_r:+.3f}R", "+0.3R", stats.expectancy_r >= 0.3),
        ("profit factor",  f"{stats.profit_factor:.2f}",  "1.4",   stats.profit_factor >= 1.4),
    ]
    print(f"\n  {'metric':<18}{'value':>12}{'min':>10}   status")
    print("  " + "-" * 52)
    for name, val, thresh, ok in rows:
        print(f"  {name:<18}{val:>12}{thresh:>10}   {'PASS' if ok else 'FAIL'}")

    print(f"\n  TP1/TP2/TP3 hits       {stats.tp1_hits}/{stats.tp2_hits}/{stats.tp3_hits}")
    print(f"  SL hits                {stats.sl_hits}")
    print(f"  max consecutive losses {stats.max_consecutive_losses}")
    print(f"  net P&L                ${stats.total_pnl_usd:,.2f}")
    if stats.total_trades < 50:
        print(f"\n  WARNING: {stats.total_trades} trades is below the 50-trade minimum")
        print("  (Section 9.3). Do not draw conclusions from this sample.")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    sys.exit(main())
