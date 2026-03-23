"""
signal-engine/strategy/trade_manager.py
Post-Entry Trade Management — Rules 5.4, 6.2–6.4, 8.2.
Watches live price and issues management commands to the EA via Redis.
Called on every M5 candle close when an open trade exists.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
import pytz

from models.candle import Candle
from models.signal import TradeState
from config import (
    NY_OPEN_KILL_H,
    TP1_CLOSE_PCT, TP2_CLOSE_PCT,
    PIP_SIZE,
)

EST = pytz.timezone("America/New_York")


async def process_trade_management(
    state:       TradeState,
    candles_m5:  List[Candle],
    now_utc:     datetime,
    set_manage_cmd_fn,    # callable: async (ticket, cmd_str) -> None
    update_state_fn,      # callable: async (trade_id, state_dict) -> None
    insert_event_fn,      # callable: async (trade_id, event_type, desc, price, lots, pnl) -> None
) -> TradeState:
    """
    Implements post-entry management rules.

    Called on every M5 close while a trade is open.

    Management cascade:
    1. Rule 8.2.4: NY open time kill (08:00 EST) → CLOSE_ALL
    2. Rule 6.2c: TP1 hit → PARTIAL_CLOSE 40%, move SL to BE
    3. Rule 6.3c: TP1 hit but price reverses back through TP1 → close remaining
    4. Rule 6.3: TP2 hit → PARTIAL_CLOSE 35% of original, activate trailing
    5. Rule 6.4b: Trailing stop on runner using 5M swing lows/highs

    Args:
        state:            Current TradeState (loaded from Redis).
        candles_m5:       Recent M5 candles for swing detection.
        now_utc:          Current UTC datetime.
        set_manage_cmd_fn: Async function to write manage command to Redis.
        update_state_fn:  Async function to persist updated TradeState.
        insert_event_fn:  Async function to log trade event to PostgreSQL.

    Returns:
        Updated TradeState.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_est = now_utc.astimezone(EST)

    current_candle = candles_m5[-1] if candles_m5 else None
    if current_candle is None:
        return state

    # Use the close of the most recent candle as current price proxy
    current_price = current_candle.close
    is_long = state.direction == "BUY"

    # ── Rule 8.2.4: NY open time kill ─────────────────────────────────────────
    if now_est.hour >= NY_OPEN_KILL_H:
        await set_manage_cmd_fn(
            state.ticket,
            f"CLOSE_ALL|NY_OPEN_TIME_KILL|{state.trade_id}"
        )
        await insert_event_fn(
            state.trade_id, "TIME_KILL",
            "NY open 08:00 EST — close all remaining positions",
            current_price, state.current_lot, None,
        )
        state.close_reason = "NY_OPEN_TIME_KILL"
        await update_state_fn(state.trade_id, _state_to_dict(state))
        return state

    # ── Rule 8.2.1: Mid-trade invalidation ────────────────────────────────────
    # Price closes back through sweep wick (beyond ASH for SHORT, below ASL for LONG)
    if is_long:
        invalidation_triggered = current_candle.close < state.asia_low
    else:
        invalidation_triggered = current_candle.close > state.asia_high

    if invalidation_triggered and not state.tp1_hit:
        # Only trigger mid-trade exit if TP1 hasn't been hit yet (position at risk)
        await set_manage_cmd_fn(
            state.ticket,
            f"CLOSE_ALL|MID_TRADE_INVALIDATION_8.2.1|{state.trade_id}"
        )
        await insert_event_fn(
            state.trade_id, "INVALIDATION_EXIT",
            "Rule 8.2.1: Price closed back through sweep level",
            current_price, state.current_lot, None,
        )
        state.close_reason = "INVALIDATION_8.2.1"
        await update_state_fn(state.trade_id, _state_to_dict(state))
        return state

    # ── Rule 6.2c: TP1 management ─────────────────────────────────────────────
    if not state.tp1_hit:
        tp1_reached = (is_long  and current_price >= state.tp1_price) or \
                      (not is_long and current_price <= state.tp1_price)

        if tp1_reached:
            state.tp1_hit    = True
            state.tp1_hit_at = now_utc

            # PARTIAL_CLOSE 40% of original lot
            await set_manage_cmd_fn(
                state.ticket,
                f"PARTIAL_CLOSE|{TP1_CLOSE_PCT}|{state.trade_id}"
            )

            # Update current_lot after 40% close
            closed_lot       = round(state.original_lot * TP1_CLOSE_PCT / 100.0, 2)
            state.current_lot = round(state.original_lot - closed_lot, 2)

            # Move SL to break-even (Rule 5.4)
            # BE = entry + 1 pip (LONG) or entry − 1 pip (SHORT)
            be_price = state.entry_price + PIP_SIZE if is_long \
                       else state.entry_price - PIP_SIZE
            state.be_moved   = True
            state.current_sl = be_price

            await set_manage_cmd_fn(
                state.ticket,
                f"MODIFY_SL|{be_price:.5f}|{state.trade_id}"
            )
            await insert_event_fn(
                state.trade_id, "TP1_HIT",
                f"Rule 6.2c: TP1 hit — closed {TP1_CLOSE_PCT}%, SL moved to BE {be_price:.5f}",
                current_price, closed_lot, None,
            )
            await update_state_fn(state.trade_id, _state_to_dict(state))
            return state

    # ── Rule 6.3c: TP1 reversal — price closes back through TP1 level ────────
    # Only applies after TP1 hit but before TP2 hit
    if state.tp1_hit and not state.tp2_hit:
        tp1_reversal = (is_long  and current_candle.close < state.tp1_price and
                        current_candle.is_bearish() and
                        current_candle.body_pips() > 3) or \
                       (not is_long and current_candle.close > state.tp1_price and
                        current_candle.is_bullish() and
                        current_candle.body_pips() > 3)

        if tp1_reversal:
            await set_manage_cmd_fn(
                state.ticket,
                f"CLOSE_ALL|TP1_REVERSAL_RULE_6.3C|{state.trade_id}"
            )
            await insert_event_fn(
                state.trade_id, "TP1_REVERSAL_EXIT",
                "Rule 6.3c: Displacement reversal back through TP1 level",
                current_price, state.current_lot, None,
            )
            state.close_reason = "TP1_REVERSAL"
            await update_state_fn(state.trade_id, _state_to_dict(state))
            return state

    # ── Rule 6.3: TP2 management ──────────────────────────────────────────────
    if state.tp1_hit and not state.tp2_hit:
        tp2_reached = (is_long  and current_price >= state.tp2_price) or \
                      (not is_long and current_price <= state.tp2_price)

        if tp2_reached:
            state.tp2_hit    = True
            state.tp2_hit_at = now_utc

            # PARTIAL_CLOSE 35% of ORIGINAL lot
            # (at this point current_lot = 60% of original; close 35/60 of remaining)
            close_pct_of_remaining = round(
                (TP2_CLOSE_PCT / (100.0 - TP1_CLOSE_PCT)) * 100.0, 0
            )
            await set_manage_cmd_fn(
                state.ticket,
                f"PARTIAL_CLOSE|{int(close_pct_of_remaining)}|{state.trade_id}"
            )

            closed_lot        = round(state.original_lot * TP2_CLOSE_PCT / 100.0, 2)
            state.current_lot = round(state.current_lot - closed_lot, 2)
            state.trailing_active = True

            # Initialise trailing stop at most recent swing
            swing = _get_trailing_swing(candles_m5, is_long)
            if swing:
                state.last_swing = swing
                state.current_sl = swing
                await set_manage_cmd_fn(
                    state.ticket,
                    f"MODIFY_SL|{swing:.5f}|{state.trade_id}"
                )

            await insert_event_fn(
                state.trade_id, "TP2_HIT",
                f"Rule 6.3: TP2 hit — closed {TP2_CLOSE_PCT}% of original, "
                f"runner {state.current_lot:.2f}lot trailing active",
                current_price, closed_lot, None,
            )
            await update_state_fn(state.trade_id, _state_to_dict(state))
            return state

    # ── Rule 6.4b: Trailing stop for TP3 runner ───────────────────────────────
    if state.trailing_active and state.tp2_hit:
        new_swing = _get_trailing_swing(candles_m5, is_long)
        if new_swing and new_swing != state.last_swing:
            # Advance trail only if the new swing is better than the current one
            should_advance = (is_long  and new_swing > (state.last_swing or 0)) or \
                             (not is_long and new_swing < (state.last_swing or float("inf")))

            if should_advance:
                state.last_swing = new_swing
                state.current_sl = new_swing
                await set_manage_cmd_fn(
                    state.ticket,
                    f"MODIFY_SL|{new_swing:.5f}|{state.trade_id}"
                )
                await insert_event_fn(
                    state.trade_id, "TRAILING_SL_MOVED",
                    f"Rule 6.4b: Trailing SL advanced to {new_swing:.5f}",
                    new_swing, state.current_lot, None,
                )
                await update_state_fn(state.trade_id, _state_to_dict(state))

    return state


def _get_trailing_swing(candles: List[Candle], is_long: bool) -> Optional[float]:
    """
    Rule 6.4b: Identify the most recent 5M swing low (LONG) or swing high (SHORT)
    on a close basis. Advance trail only when a new swing point prints.
    """
    if len(candles) < 3:
        return None

    # Look at the last 5 completed candles (exclude the current forming candle)
    lookback = candles[-6:-1] if len(candles) >= 6 else candles[:-1]

    if is_long:
        # Swing low: candle whose low is lower than both adjacent candles
        for i in range(1, len(lookback) - 1):
            c = lookback[i]
            if c.low < lookback[i - 1].low and c.low < lookback[i + 1].low:
                return c.low
        # Fallback: use the lowest low of the lookback
        return min(c.low for c in lookback)
    else:
        # Swing high: candle whose high is higher than both adjacent candles
        for i in range(1, len(lookback) - 1):
            c = lookback[i]
            if c.high > lookback[i - 1].high and c.high > lookback[i + 1].high:
                return c.high
        return max(c.high for c in lookback)


def _state_to_dict(state: TradeState) -> dict:
    """Serialise TradeState to dict for Redis storage."""
    return {
        "trade_id":        state.trade_id,
        "ticket":          state.ticket,
        "direction":       state.direction,
        "entry_price":     state.entry_price,
        "sl_price":        state.sl_price,
        "tp1_price":       state.tp1_price,
        "tp2_price":       state.tp2_price,
        "tp3_price":       state.tp3_price,
        "original_lot":    state.original_lot,
        "current_lot":     state.current_lot,
        "asia_high":       state.asia_high,
        "asia_low":        state.asia_low,
        "tp1_hit":         state.tp1_hit,
        "tp2_hit":         state.tp2_hit,
        "be_moved":        state.be_moved,
        "trailing_active": state.trailing_active,
        "last_swing":      state.last_swing,
        "current_sl":      state.current_sl,
        "opened_at":       str(state.opened_at) if state.opened_at else None,
        "tp1_hit_at":      str(state.tp1_hit_at) if state.tp1_hit_at else None,
        "tp2_hit_at":      str(state.tp2_hit_at) if state.tp2_hit_at else None,
        "close_reason":    state.close_reason,
        "close_price":     state.close_price,
        "pnl_usd":         state.pnl_usd,
    }