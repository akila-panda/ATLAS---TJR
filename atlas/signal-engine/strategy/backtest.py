"""
signal-engine/strategy/backtest.py
Backtesting & Journaling Framework — Section 9 of TJR Operational Document.
Runs the full strategy pipeline over historical candle data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

        session_m5  = _slice_candles(all_candles_m5,  asia_start, lkz_end)
        session_m15 = _slice_candles(all_candles_m15, asia_start, lkz_end)
        session_h4  = _slice_candles(all_candles_h4,
                                     asia_start - timedelta(days=30), lkz_end)
        session_d1  = _slice_candles(all_candles_d1,
                                     asia_start - timedelta(days=60), lkz_end)

        if len(session_m5) < 20:
            no_trade_count += 1
            continue

        htf_ctx   = htf_contexts.get(date_str, {"dol_direction": "AMBIGUOUS"})
        news_evs  = news_by_date.get(date_str, [])

        # Run pipeline for this session
        now_utc = lkz_end.astimezone(timezone.utc).replace(tzinfo=None)

        # News filter
        news_bl = is_news_blocked(news_evs, now_utc)

        # Asia range
        asia = detect_asia_range(session_m5, now_utc)

        # Sweep
        sweep = detect_sweep(session_m5, asia, htf_ctx, now_utc) \
                if asia.is_valid else _null_sweep()

        # Structure
        structure = detect_post_sweep_structure(session_m5, session_m15, sweep) \
                    if sweep.is_valid else _null_structure()

        # FVG / OB
        fvg = detect_fvg(session_m5, sweep, structure, now_utc) \
              if structure.choch_15m else _null_fvg()
        ob  = detect_ob(session_m5, sweep, structure) \
              if structure.choch_15m else _null_ob()

        # Entry params
        entry = calculate_entry(sweep, asia, fvg, ob, htf_ctx, ACCOUNT_BALANCE) \
                if (fvg.found or ob.found) else None

        if entry is None:
            no_trade_count += 1
            continue

        # Confluence
        confluence = score_confluence(
            asia, sweep, structure, fvg, htf_ctx, news_evs, sweep.sweep_time
        )

        # Risk state (reset per session for backtest)
        risk_state = {"session_terminated": False, "daily_loss_pct": 0.0}

        # Decision tree
        dt = run_decision_tree(
            news_blocked=news_bl,
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
            now_utc=now_utc,
        )

        if dt.outcome != "ENTER":
            no_trade_count += 1
            continue

        # Apply spread to entry (Section 9.4b)
        direction = entry.direction
        if direction == "BUY":
            actual_entry = entry.entry_price + spread
        else:
            actual_entry = entry.entry_price - spread

        # Simulate outcome against subsequent M5 candles
        post_entry = [c for c in session_m5 if c.time > (sweep.sweep_candle.time
                      if sweep.sweep_candle else session_m5[0].time)]

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

    # Expectancy in R: E = (win_rate * avg_win_R) − (loss_rate * 1)
    win_r   = stats.win_rate_tp1 / 100.0
    loss_r  = 1.0 - win_r
    avg_win = stats.avg_rr_achieved if stats.avg_rr_achieved > 0 else 2.0
    stats.expectancy_r = round(win_r * avg_win - loss_r * 1.0, 3)

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
    Forward-simulate trade outcome against subsequent candle prices.
    Returns (outcome_str, rr_achieved, pnl_usd).

    Rule 9.4d: Only count as entry if price returned to FVG zone.
    If no candle touches entry price: classify as MISSED.
    """
    is_long = direction == "BUY"
    pip_val = 10.0 * lot_size   # $10 per pip per standard lot × lots

    # Check if entry price was ever reached
    entry_filled = any(
        (is_long  and c.low  <= entry) or
        (not is_long and c.high >= entry)
        for c in candles
    )
    if not entry_filled:
        return "MISSED", 0.0, 0.0

    for c in candles:
        if is_long:
            if c.low <= sl:
                pips = (sl - entry) / PIP_SIZE
                return "SL", round(pips, 1), round(pips * pip_val, 2)
            if c.high >= tp3:
                rr = abs(tp3 - entry) / abs(entry - sl)
                pnl = abs(tp3 - entry) / PIP_SIZE * pip_val
                return "TP3", round(rr, 2), round(pnl, 2)
            if c.high >= tp2:
                rr = abs(tp2 - entry) / abs(entry - sl)
                pnl = abs(tp2 - entry) / PIP_SIZE * pip_val
                return "TP2", round(rr, 2), round(pnl, 2)
            if c.high >= tp1:
                rr = abs(tp1 - entry) / abs(entry - sl)
                pnl = abs(tp1 - entry) / PIP_SIZE * pip_val * (TP1_CLOSE_PCT / 100.0)
                return "TP1", round(rr, 2), round(pnl, 2)
        else:
            if c.high >= sl:
                pips = (entry - sl) / PIP_SIZE
                return "SL", round(-pips, 1), round(-pips * pip_val, 2)
            if c.low <= tp3:
                rr = abs(tp3 - entry) / abs(entry - sl)
                pnl = abs(tp3 - entry) / PIP_SIZE * pip_val
                return "TP3", round(rr, 2), round(pnl, 2)
            if c.low <= tp2:
                rr = abs(tp2 - entry) / abs(entry - sl)
                pnl = abs(tp2 - entry) / PIP_SIZE * pip_val
                return "TP2", round(rr, 2), round(pnl, 2)
            if c.low <= tp1:
                rr = abs(tp1 - entry) / abs(entry - sl)
                pnl = abs(tp1 - entry) / PIP_SIZE * pip_val * (TP1_CLOSE_PCT / 100.0)
                return "TP1", round(rr, 2), round(pnl, 2)

    return "MISSED", 0.0, 0.0


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


def _slice_candles(candles: List[Candle], start: datetime, end: datetime) -> List[Candle]:
    """Return candles whose open time falls within [start, end)."""
    s = start.astimezone(timezone.utc)
    e = end.astimezone(timezone.utc)
    result = []
    for c in candles:
        t = c.time.replace(tzinfo=timezone.utc) if c.time.tzinfo is None else c.time
        if s <= t < e:
            result.append(c)
    return result


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