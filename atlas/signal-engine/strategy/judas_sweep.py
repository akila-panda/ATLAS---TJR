"""
signal-engine/strategy/judas_sweep.py
Judas Swing Identification Rules — Section 2 of TJR Operational Document.
Implements Rules 2.1 through 2.6 exactly.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
import pytz

from models.candle import Candle
from strategy.asia_range import AsiaRangeResult
from config import (
    LKZ_START_EST, LKZ_END_EST,
    SWEEP_MIN_PIPS, SWEEP_MAX_PIPS,
    LATE_LKZ_H, LATE_LKZ_M,
    PIP_SIZE,
)

EST = pytz.timezone("America/New_York")

# ── Phase 5 experiment switches ───────────────────────────────────────────────
# Defaults reproduce the shipped rules exactly. strategy/variants.py flips these
# one at a time to measure what each filter is actually contributing. Nothing in
# the live path changes them.
ALLOW_DOUBLE_SWEEP      = False   # Rule 2.6: reject when both ASH and ASL swept
ALLOW_AMBIGUOUS_DOL     = False   # Rule 2.5: reject when Daily DOL is unclear
BREAKOUT_FILTER_USE_DOL = True    # Rule 2.4c: DOL-aligned break counts as breakout


@dataclass
class SweepResult:
    detected:       bool
    is_valid:       bool
    invalid_reason: Optional[str] = None

    # Sweep details
    direction:      Optional[str]   = None   # "BSL" (above ASH) | "SSL" (below ASL)
    sweep_candle:   Optional[Candle] = None
    sweep_time:     Optional[datetime] = None
    extension_pips: float = 0.0              # wick extension beyond ASH or ASL
    is_late_lkz:    bool  = False            # Rule 2.1a: sweep after 04:56 EST
    is_wick_only:   bool  = False            # Rule 2.3: body closed back inside range

    # HTF alignment
    aligns_with_dol: bool = False            # Rule 2.5: swept side matches Daily DOL


def _to_est(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EST)


def _in_lkz(dt_est: datetime) -> bool:
    """Returns True if time is within 02:00–05:00 EST (Rule 2.1)."""
    h = dt_est.hour
    return LKZ_START_EST <= h < LKZ_END_EST


def _is_late_lkz(dt_est: datetime) -> bool:
    """
    Returns True if sweep occurs in final 4 minutes of LKZ (04:56–05:00 EST).
    Implements Rule 2.1a edge case.
    """
    return dt_est.hour == LATE_LKZ_H and dt_est.minute >= LATE_LKZ_M


def detect_sweep(
    candles_m5:  List[Candle],
    asia:        AsiaRangeResult,
    htf_context: dict,
    now_utc:     datetime,
) -> SweepResult:
    """
    Implements Rules 2.1–2.6.

    Scans M5 candles within the LKZ (02:00–05:00 EST) for a Judas sweep
    of the Asia high (BSL) or Asia low (SSL).

    Args:
        candles_m5:   List of M5 candles (oldest-first).
        asia:         Validated AsiaRangeResult.
        htf_context:  Dict from Redis with 'dol_direction' key ("BULLISH"|"BEARISH"|"AMBIGUOUS").
        now_utc:      Current UTC datetime.

    Returns:
        SweepResult with detected flag and all sweep metadata.
    """
    if not asia.is_valid:
        return SweepResult(detected=False, is_valid=False,
                           invalid_reason="ASIA_RANGE_INVALID")

    # ── Filter to candles within the LKZ window (Rule 2.1) ───────────────────
    lkz_candles: List[Candle] = []
    for c in candles_m5:
        c_est = _to_est(c.time)
        if _in_lkz(c_est):
            lkz_candles.append(c)

    if not lkz_candles:
        return SweepResult(detected=False, is_valid=False,
                           invalid_reason="NO_CANDLES_IN_LKZ")

    # ── Scan for sweep candidates ─────────────────────────────────────────────
    # Collect all candles that wick beyond ASH or ASL
    bsl_sweeps: List[Candle] = []  # wicks above ASH
    ssl_sweeps: List[Candle] = []  # wicks below ASL

    for c in lkz_candles:
        bsl_ext = (c.high - asia.asia_high) / PIP_SIZE   # positive = above ASH
        ssl_ext = (asia.asia_low - c.low)  / PIP_SIZE    # positive = below ASL

        if bsl_ext >= SWEEP_MIN_PIPS:
            bsl_sweeps.append(c)
        if ssl_ext >= SWEEP_MIN_PIPS:
            ssl_sweeps.append(c)

    # ── Rule 2.6: Double sweep check ──────────────────────────────────────────
    if bsl_sweeps and ssl_sweeps and not ALLOW_DOUBLE_SWEEP:
        return SweepResult(
            detected=True,
            is_valid=False,
            invalid_reason="DOUBLE_SWEEP",
        )

    # ── No sweep detected ─────────────────────────────────────────────────────
    if not bsl_sweeps and not ssl_sweeps:
        return SweepResult(detected=False, is_valid=False,
                           invalid_reason="NO_SWEEP_IN_LKZ")

    # ── Identify the sweep candidate (first qualifying candle) ───────────────
    if bsl_sweeps:
        direction    = "BSL"
        sweep_candle = bsl_sweeps[0]
        extension    = round((sweep_candle.high - asia.asia_high) / PIP_SIZE, 1)
        level        = asia.asia_high
    else:
        direction    = "SSL"
        sweep_candle = ssl_sweeps[0]
        extension    = round((asia.asia_low - sweep_candle.low) / PIP_SIZE, 1)
        level        = asia.asia_low

    sweep_est  = _to_est(sweep_candle.time)
    is_late    = _is_late_lkz(sweep_est)

    # ── Rule 2.2: Extension distance 3–8 pips ────────────────────────────────
    if extension < SWEEP_MIN_PIPS:
        return SweepResult(
            detected=True, is_valid=False,
            direction=direction,
            sweep_candle=sweep_candle,
            sweep_time=sweep_est,
            extension_pips=extension,
            invalid_reason="SWEEP_EXTENSION_TOO_SMALL",
        )

    # ── Rule 2.3: Wick-only check — body must close back inside range ─────────
    if direction == "BSL":
        # Bullish sweep of ASH: body close must be below ASH
        body_close_outside = sweep_candle.close > asia.asia_high
    else:
        # Bearish sweep of ASL: body close must be above ASL
        body_close_outside = sweep_candle.close < asia.asia_low

    if body_close_outside:
        # ── Rule 2.4: Breakout filter ─────────────────────────────────────────
        # If body closes beyond the level, apply the three-factor breakout test.
        is_breakout = _apply_breakout_filter(
            direction, sweep_candle, lkz_candles, asia, htf_context
        )
        if is_breakout:
            return SweepResult(
                detected=True, is_valid=False,
                direction=direction,
                sweep_candle=sweep_candle,
                sweep_time=sweep_est,
                extension_pips=extension,
                invalid_reason="BREAKOUT_NOT_JUDAS",
            )
        # Body close outside but breakout tests negative — still classify as sweep
        is_wick_only = False
    else:
        is_wick_only = True

    # ── Rule 2.2 upper bound: extension > 8 pips → apply breakout filter ─────
    if extension > SWEEP_MAX_PIPS:
        is_breakout = _apply_breakout_filter(
            direction, sweep_candle, lkz_candles, asia, htf_context
        )
        if is_breakout:
            return SweepResult(
                detected=True, is_valid=False,
                direction=direction,
                sweep_candle=sweep_candle,
                sweep_time=sweep_est,
                extension_pips=extension,
                invalid_reason="DEEP_SWEEP_BREAKOUT_FILTER",
            )

    # ── Rule 2.5: HTF DOL alignment ───────────────────────────────────────────
    dol_direction = htf_context.get("dol_direction", "AMBIGUOUS")
    if direction == "BSL":
        # Sweep above ASH — Judas SHORT setup — DOL should be bearish (Rule 2.5a)
        aligns = dol_direction == "BEARISH"
    else:
        # Sweep below ASL — Judas LONG setup — DOL should be bullish (Rule 2.5b)
        aligns = dol_direction == "BULLISH"

    if dol_direction == "AMBIGUOUS" and not ALLOW_AMBIGUOUS_DOL:
        return SweepResult(
            detected=True, is_valid=False,
            direction=direction,
            sweep_candle=sweep_candle,
            sweep_time=sweep_est,
            extension_pips=extension,
            is_late_lkz=is_late,
            is_wick_only=is_wick_only,
            aligns_with_dol=False,
            invalid_reason="DOL_AMBIGUOUS",
        )

    return SweepResult(
        detected=True,
        is_valid=True,
        direction=direction,
        sweep_candle=sweep_candle,
        sweep_time=sweep_est,
        extension_pips=extension,
        is_late_lkz=is_late,
        is_wick_only=is_wick_only,
        aligns_with_dol=aligns,
    )


def _apply_breakout_filter(
    direction:    str,
    sweep_candle: Candle,
    lkz_candles:  List[Candle],
    asia:         AsiaRangeResult,
    htf_context:  dict,
) -> bool:
    """
    Rule 2.4: Three-factor breakout test.
    Returns True if price is breaking out (NOT a Judas sweep).
    All three factors must be NEGATIVE for sweep to retain Judas classification.

    2.4a: Body close beyond level → breakout signal (checked by caller)
    2.4b: Next 2 candles also close beyond level → breakout confirmation
    2.4c: Breakout direction aligns with Daily DOL → elevated breakout probability
    """
    level = asia.asia_high if direction == "BSL" else asia.asia_low

    # Find index of sweep candle in lkz_candles
    sweep_idx = next(
        (i for i, c in enumerate(lkz_candles) if c.time == sweep_candle.time),
        None
    )
    if sweep_idx is None:
        return False

    # 2.4b: Check next 2 candles after sweep
    follow_through_count = 0
    for c in lkz_candles[sweep_idx + 1: sweep_idx + 3]:
        if direction == "BSL" and c.close > level:
            follow_through_count += 1
        elif direction == "SSL" and c.close < level:
            follow_through_count += 1

    factor_b = follow_through_count >= 2

    # 2.4c: Direction aligns with Daily DOL
    dol = htf_context.get("dol_direction", "AMBIGUOUS")
    if direction == "BSL":
        factor_c = dol == "BULLISH"   # breakout UP aligns with bullish DOL
    else:
        factor_c = dol == "BEARISH"   # breakout DOWN aligns with bearish DOL

    # Any positive factor = breakout
    return factor_b or (factor_c and BREAKOUT_FILTER_USE_DOL)