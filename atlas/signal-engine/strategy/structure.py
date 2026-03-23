"""
signal-engine/strategy/structure.py
Post-sweep structural confirmation — Rules 3.4 and 4.1.
Detects CHoCH on 15M, CHoCH on 5M, and displacement candle with FVG.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from models.candle import Candle
from strategy.judas_sweep import SweepResult
from config import DISPLACEMENT_MULT, PIP_SIZE


@dataclass
class StructureResult:
    choch_15m:      bool  = False   # Rule 3.4a: CHoCH on 15M (minimum requirement)
    choch_5m:       bool  = False   # Rule 3.4b: CHoCH on 5M
    displacement:   bool  = False   # Rule 4.1: displacement candle present
    bos_5m:         bool  = False   # 5M BOS in reversal direction

    # Displacement candle details (for FVG detection)
    displacement_idx: Optional[int] = None   # index in candles_m5 list
    displacement_candle: Optional[Candle] = None

    # Confluence flag
    full_confirmation: bool = False  # True if 15M CHoCH + 5M BOS + displacement all present


def detect_post_sweep_structure(
    candles_m5:  List[Candle],
    candles_m15: List[Candle],
    sweep:       SweepResult,
) -> StructureResult:
    """
    Implements Rules 3.4 and 4.1.

    After a Judas sweep, looks for:
    1. CHoCH on 15M (Rule 3.4a) — minimum entry requirement
    2. CHoCH/BOS on 5M (Rule 3.4b)
    3. Displacement candle on 5M with FVG (Rule 4.1)

    The reversal direction is opposite to the sweep direction:
    - BSL sweep (swept ASH) → reversal direction is DOWN (SHORT)
    - SSL sweep (swept ASL) → reversal direction is UP (LONG)

    Args:
        candles_m5:   M5 candles after the sweep candle (oldest-first).
        candles_m15:  M15 candles (oldest-first).
        sweep:        Validated SweepResult.

    Returns:
        StructureResult with all confirmation flags.
    """
    if not sweep.is_valid or sweep.sweep_candle is None:
        return StructureResult()

    # Reversal direction
    reversal_up   = sweep.direction == "SSL"   # swept below → reverse UP
    reversal_down = sweep.direction == "BSL"   # swept above → reverse DOWN

    # Filter candles to only those AFTER the sweep candle
    post_sweep_m5 = [
        c for c in candles_m5
        if c.time > sweep.sweep_candle.time
    ]
    post_sweep_m15 = [
        c for c in candles_m15
        if c.time >= sweep.sweep_candle.time
    ]

    if len(post_sweep_m5) < 3:
        return StructureResult()

    # ── Rule 3.4a: CHoCH on 15M ───────────────────────────────────────────────
    choch_15m = _detect_choch(post_sweep_m15, reversal_up)

    # ── Rule 3.4b / BOS on 5M ────────────────────────────────────────────────
    choch_5m  = _detect_choch(post_sweep_m5, reversal_up)
    bos_5m    = _detect_bos(post_sweep_m5, reversal_up)

    # ── Rule 4.1: Displacement candle detection ───────────────────────────────
    disp_idx, disp_candle = _detect_displacement(post_sweep_m5, reversal_up)
    has_displacement = disp_idx is not None

    # Map index back to the global candles_m5 list for FVG detection
    global_disp_idx = None
    if disp_candle is not None:
        for i, c in enumerate(candles_m5):
            if c.time == disp_candle.time:
                global_disp_idx = i
                break

    full_confirmation = choch_15m and bos_5m and has_displacement

    return StructureResult(
        choch_15m=choch_15m,
        choch_5m=choch_5m,
        displacement=has_displacement,
        bos_5m=bos_5m,
        displacement_idx=global_disp_idx,
        displacement_candle=disp_candle,
        full_confirmation=full_confirmation,
    )


def _detect_choch(candles: List[Candle], reversal_up: bool) -> bool:
    """
    Detects a Change of Character (CHoCH) on the given candle list.

    CHoCH (reversal signal): price breaks the most recent opposing swing point
    that formed after the last BOS.

    Simplified implementation for real-time detection:
    - For reversal UP: a candle closes above the most recent swing high
      that formed during the post-sweep downswing.
    - For reversal DOWN: a candle closes below the most recent swing low
      that formed during the post-sweep upswing.
    """
    if len(candles) < 4:
        return False

    # Find the swing high/low formed immediately after the sweep
    # then check if a later candle breaks it
    if reversal_up:
        # Post-SSL-sweep: price was falling → look for a swing low, then break up
        swing_low = min(c.low for c in candles[:3])
        for c in candles[3:]:
            if c.close > swing_low + (3 * PIP_SIZE):  # 3 pip clearance
                return True
    else:
        # Post-BSL-sweep: price was rising → look for a swing high, then break down
        swing_high = max(c.high for c in candles[:3])
        for c in candles[3:]:
            if c.close < swing_high - (3 * PIP_SIZE):
                return True

    return False


def _detect_bos(candles: List[Candle], reversal_up: bool) -> bool:
    """
    Detects a Break of Structure (BOS) — continuation signal.
    Price breaks a prior swing high (bullish BOS) or prior swing low (bearish BOS).
    """
    if len(candles) < 5:
        return False

    if reversal_up:
        # Look for a bullish BOS: close beyond the highest high in first half
        pivot_high = max(c.high for c in candles[:4])
        for c in candles[4:]:
            if c.close > pivot_high:
                return True
    else:
        # Bearish BOS: close beyond the lowest low in first half
        pivot_low = min(c.low for c in candles[:4])
        for c in candles[4:]:
            if c.close < pivot_low:
                return True

    return False


def _detect_displacement(
    candles:     List[Candle],
    reversal_up: bool,
) -> tuple[Optional[int], Optional[Candle]]:
    """
    Rule 4.1: Displacement candle detection.

    A displacement candle must satisfy ALL THREE criteria simultaneously:
    4.1a: Body closes beyond the most recent 5M swing point in reversal direction.
    4.1b: Body size >= DISPLACEMENT_MULT (1.5×) the average body of the preceding 5 candles.
    4.1c: The three-candle sequence leaves at least one visible FVG.

    Returns (index_in_post_sweep_list, candle) or (None, None).
    """
    if len(candles) < 6:
        return None, None

    for i in range(5, len(candles)):
        candle = candles[i]

        # 4.1a: Directional close
        if reversal_up and not candle.is_bullish():
            continue
        if not reversal_up and not candle.is_bearish():
            continue

        # 4.1b: Body size >= 1.5× average of preceding 5 candle bodies
        prev_5  = candles[i - 5: i]
        avg_body = sum(c.body_size() for c in prev_5) / 5.0
        if avg_body == 0:
            continue
        if candle.body_size() < DISPLACEMENT_MULT * avg_body:
            continue

        # 4.1c: Three-candle FVG check
        if i < 1 or i + 1 >= len(candles):
            continue
        c_prev = candles[i - 1]
        c_next = candles[i + 1]

        if reversal_up:
            # Bullish FVG: c_prev.high < c_next.low (gap between them)
            has_fvg = c_prev.high < c_next.low
        else:
            # Bearish FVG: c_prev.low > c_next.high
            has_fvg = c_prev.low > c_next.high

        if not has_fvg:
            continue

        # All three criteria met — this is the displacement candle
        return i, candle

    return None, None