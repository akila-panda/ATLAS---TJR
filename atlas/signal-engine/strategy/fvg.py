"""
signal-engine/strategy/fvg.py
Fair Value Gap (FVG) Entry Zone — Rule 4.2 of TJR Operational Document.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import pytz

from models.candle import Candle
from strategy.judas_sweep import SweepResult
from strategy.structure import StructureResult
from config import ENTRY_EXPIRY_H, ENTRY_EXPIRY_M, PIP_SIZE

EST = pytz.timezone("America/New_York")


@dataclass
class FVGResult:
    found:          bool
    direction:      Optional[str]  = None   # "LONG" | "SHORT"

    # FVG boundaries (Rule 4.2a/4.2b)
    fvg_high:       float = 0.0    # upper boundary of the gap
    fvg_low:        float = 0.0    # lower boundary of the gap
    fvg_midpoint:   float = 0.0    # 50% level — the limit entry price (Rule 4.2)
    fvg_size_pips:  float = 0.0

    # The three candles that formed the FVG
    candle_1:       Optional[Candle] = None
    candle_2:       Optional[Candle] = None
    candle_3:       Optional[Candle] = None

    # Validity state
    is_violated:    bool = False   # Rule 4.2c: candle body fully through gap
    is_expired:     bool = False   # Rule 4.2d: past 05:30 EST


def detect_fvg(
    candles_m5:   List[Candle],
    sweep:        SweepResult,
    structure:    StructureResult,
    now_utc:      datetime,
) -> FVGResult:
    """
    Implements Rule 4.2.

    Identifies the FVG created by the displacement candle.

    LONG FVG (post-SSL sweep):
        fvg_low  = candles[idx-1].high  (top of candle before displacement)
        fvg_high = candles[idx+1].low   (bottom of candle after displacement)
        Gap exists when c_prev.high < c_next.low

    SHORT FVG (post-BSL sweep):
        fvg_high = candles[idx-1].low   (bottom of candle before displacement)
        fvg_low  = candles[idx+1].high  (top of candle after displacement)
        Gap exists when c_prev.low > c_next.high

    Entry limit = midpoint (50%) of the FVG (Rule 4.2).

    Args:
        candles_m5:  Full M5 candle list (oldest-first).
        sweep:       Validated SweepResult.
        structure:   StructureResult with displacement_idx populated.
        now_utc:     Current UTC datetime.

    Returns:
        FVGResult with found flag and entry zone levels.
    """
    # ── Expiry check (Rule 4.2d) ───────────────────────────────────────────────
    now_est = now_utc.astimezone(EST) if now_utc.tzinfo else \
              now_utc.replace(tzinfo=timezone.utc).astimezone(EST)

    expiry_today = now_est.replace(
        hour=ENTRY_EXPIRY_H, minute=ENTRY_EXPIRY_M,
        second=0, microsecond=0
    )
    is_expired = now_est >= expiry_today

    if not structure.displacement or structure.displacement_idx is None:
        return FVGResult(found=False, is_expired=is_expired)

    idx = structure.displacement_idx

    # Need candles at idx-1, idx, idx+1
    if idx < 1 or idx + 1 >= len(candles_m5):
        return FVGResult(found=False, is_expired=is_expired)

    c1 = candles_m5[idx - 1]   # candle before displacement
    c2 = candles_m5[idx]        # displacement candle
    c3 = candles_m5[idx + 1]    # candle after displacement

    reversal_up = sweep.direction == "SSL"

    if reversal_up:
        # ── Rule 4.2a: Bullish FVG ─────────────────────────────────────────────
        # Gap between c1.high and c3.low
        fvg_low  = c1.high
        fvg_high = c3.low
        if fvg_high <= fvg_low:
            return FVGResult(found=False, is_expired=is_expired)
        direction = "LONG"
    else:
        # ── Rule 4.2b: Bearish FVG ─────────────────────────────────────────────
        # Gap between c1.low and c3.high
        fvg_high = c1.low
        fvg_low  = c3.high
        if fvg_low >= fvg_high:
            return FVGResult(found=False, is_expired=is_expired)
        direction = "SHORT"

    fvg_midpoint  = (fvg_high + fvg_low) / 2.0
    fvg_size_pips = round((fvg_high - fvg_low) / PIP_SIZE, 1)

    # ── Rule 4.2c: Violation check ─────────────────────────────────────────────
    # Check all candles after c3 to see if any body fully penetrates the FVG
    is_violated = _check_fvg_violated(
        candles_m5[idx + 2:], direction, fvg_high, fvg_low
    )

    return FVGResult(
        found=True,
        direction=direction,
        fvg_high=fvg_high,
        fvg_low=fvg_low,
        fvg_midpoint=fvg_midpoint,
        fvg_size_pips=fvg_size_pips,
        candle_1=c1,
        candle_2=c2,
        candle_3=c3,
        is_violated=is_violated,
        is_expired=is_expired,
    )


def _check_fvg_violated(
    subsequent_candles: List[Candle],
    direction:          str,
    fvg_high:           float,
    fvg_low:            float,
) -> bool:
    """
    Rule 4.2c: FVG is violated if any subsequent candle BODY closes fully
    through the gap boundaries (beyond the opposing FVG boundary).

    For LONG FVG: violated if a candle body close < fvg_low (price dropped through)
    For SHORT FVG: violated if a candle body close > fvg_high (price rose through)
    """
    for c in subsequent_candles:
        if direction == "LONG":
            # Body close below the FVG floor → FVG violated
            body_bottom = min(c.open, c.close)
            if body_bottom < fvg_low:
                return True
        else:
            # Body close above the FVG ceiling → FVG violated
            body_top = max(c.open, c.close)
            if body_top > fvg_high:
                return True
    return False


def is_fvg_expired(now_utc: datetime) -> bool:
    """
    Rule 4.2d: Standalone expiry check.
    Returns True if current time is past 05:30 EST.
    Used in decision_tree.py node 14.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_est = now_utc.astimezone(EST)
    return now_est.hour > ENTRY_EXPIRY_H or (
        now_est.hour == ENTRY_EXPIRY_H and now_est.minute >= ENTRY_EXPIRY_M
    )