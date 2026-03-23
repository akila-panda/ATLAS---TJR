"""
signal-engine/strategy/order_block.py
Order Block Entry Zone — Rule 4.3 of TJR Operational Document.
Used as fallback when no FVG is present in the displacement move.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from models.candle import Candle
from strategy.judas_sweep import SweepResult
from strategy.structure import StructureResult
from config import PIP_SIZE


@dataclass
class OBResult:
    found:          bool
    direction:      Optional[str]  = None   # "LONG" | "SHORT"

    # OB body boundaries (Rule 4.3: open to close of the last opposing candle)
    ob_high:        float = 0.0   # top of OB body
    ob_low:         float = 0.0   # bottom of OB body
    entry_price:    float = 0.0   # Rule 4.3a/4.3b: entry at OB close price

    # The order block candle itself
    ob_candle:      Optional[Candle] = None

    # Validity
    has_bos_consequence: bool = False  # Rule 4.3c: displacement caused BOS/CHoCH


def detect_ob(
    candles_m5: List[Candle],
    sweep:      SweepResult,
    structure:  StructureResult,
) -> OBResult:
    """
    Implements Rule 4.3.

    The Order Block is the last opposing candle before the displacement move.
    Only valid if the displacement from it produced a BOS or CHoCH (Rule 4.3c).

    LONG OB (post-SSL sweep → upward displacement):
        OB = last bearish candle before displacement_idx.
        Entry = OB close price (bottom of the bearish body). (Rule 4.3a)

    SHORT OB (post-BSL sweep → downward displacement):
        OB = last bullish candle before displacement_idx.
        Entry = OB close price (top of the bullish body). (Rule 4.3b)

    Args:
        candles_m5:  Full M5 candle list (oldest-first).
        sweep:       Validated SweepResult.
        structure:   StructureResult — must have displacement_idx set.

    Returns:
        OBResult with found flag and entry zone levels.
    """
    if not structure.displacement or structure.displacement_idx is None:
        return OBResult(found=False)

    # Rule 4.3c: OB is only valid if displacement caused a BOS or CHoCH
    has_consequence = structure.bos_5m or structure.choch_5m or structure.choch_15m
    if not has_consequence:
        return OBResult(found=False, has_bos_consequence=False)

    idx = structure.displacement_idx
    reversal_up = sweep.direction == "SSL"

    # Scan backwards from displacement_idx to find the last opposing candle
    ob_candle: Optional[Candle] = None

    for i in range(idx - 1, -1, -1):
        c = candles_m5[i]
        if reversal_up and c.is_bearish():
            # LONG setup: last bearish candle before upward displacement
            ob_candle = c
            break
        elif not reversal_up and c.is_bullish():
            # SHORT setup: last bullish candle before downward displacement
            ob_candle = c
            break

    if ob_candle is None:
        return OBResult(found=False, has_bos_consequence=has_consequence)

    # OB body is defined by open and close (not wicks)
    ob_open  = ob_candle.open
    ob_close = ob_candle.close
    ob_high  = max(ob_open, ob_close)
    ob_low   = min(ob_open, ob_close)

    if reversal_up:
        # Rule 4.3a: LONG — entry at OB close (bottom of the bearish body)
        entry_price = ob_close  # for a bearish candle: close < open → close is lower
    else:
        # Rule 4.3b: SHORT — entry at OB close (top of the bullish body)
        entry_price = ob_close  # for a bullish candle: close > open → close is higher

    direction = "LONG" if reversal_up else "SHORT"

    return OBResult(
        found=True,
        direction=direction,
        ob_high=ob_high,
        ob_low=ob_low,
        entry_price=entry_price,
        ob_candle=ob_candle,
        has_bos_consequence=has_consequence,
    )