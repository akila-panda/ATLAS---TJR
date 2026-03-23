"""
signal-engine/strategy/asia_range.py
Asia Range Mapping Protocol — Section 1 of TJR Operational Document.
Implements Rules 1.1 through 1.4 exactly.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
import pytz

from models.candle import Candle
from config import (
    ASIA_START_EST, ASIA_END_EST,
    ASIA_RANGE_MIN_PIPS, ASIA_RANGE_MAX_PIPS,
    WIDE_RANGE_PIPS, MIN_RR_WIDE_RANGE,
    CONTAMINATION_BODY_PIPS, CONTAMINATION_MAX_CANDLES,
    PIP_SIZE,
)

EST = pytz.timezone("America/New_York")


@dataclass
class AsiaRangeResult:
    is_valid:       bool
    invalid_reason: Optional[str] = None

    # Core levels (Rule 1.1a / 1.1b)
    asia_high:      float = 0.0   # ASH — highest wick high in window
    asia_low:       float = 0.0   # ASL — lowest wick low in window
    range_pips:     float = 0.0

    # Metadata
    candle_count:   int   = 0
    contaminated:   bool  = False
    is_wide_range:  bool  = False   # Rule 1.4: 38–40 pip range
    required_rr:    float = 2.0     # elevated to 2.5 if wide range (Rule 1.4)

    # The candles that formed the range (for annotation)
    window_candles: List[Candle] = field(default_factory=list)


def detect_asia_range(candles_m5: List[Candle], now_utc: datetime) -> AsiaRangeResult:
    """
    Implements Rules 1.1–1.4.

    Filters M5 candles whose open time falls within the Asia session window
    (20:00–00:00 EST). Computes ASH and ASL from wick extremes.
    Applies validity filters: range size, contamination.

    Args:
        candles_m5: List of M5 Candle objects (oldest-first).
        now_utc:    Current UTC datetime (used to determine session date).

    Returns:
        AsiaRangeResult with is_valid flag and all computed levels.
    """
    # ── Determine the Asia window boundaries for the most recent session ──────
    # The Asia session for a given trading day runs 20:00 EST of the PREVIOUS
    # calendar day through 00:00 EST of the CURRENT calendar day.
    now_est = now_utc.astimezone(EST)

    # Find today's Asia window: from 20:00 EST yesterday to 00:00 EST today
    from datetime import timedelta
    today_est = now_est.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end   = today_est                          # 00:00 EST today
    window_start = today_est - timedelta(hours=4)     # 20:00 EST yesterday
    # 20:00 = 00:00 - 4 hours only if today midnight - 4h = 20:00 previous day
    # More explicitly:
    prev_day_20 = (today_est - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    window_start = prev_day_20

    # ── Rule 1.1: Filter M5 candles within 20:00–00:00 EST window ─────────────
    window_candles: List[Candle] = []
    for c in candles_m5:
        # Convert candle open time to EST
        if c.time.tzinfo is None:
            c_utc = c.time.replace(tzinfo=timezone.utc)
        else:
            c_utc = c.time
        c_est = c_utc.astimezone(EST)

        # Candle must open on or after window_start and before window_end
        c_est_naive = c_est.replace(tzinfo=None)
        ws_naive    = window_start.replace(tzinfo=None)
        we_naive    = window_end.replace(tzinfo=None)

        if ws_naive <= c_est_naive < we_naive:
            window_candles.append(c)

    if len(window_candles) == 0:
        return AsiaRangeResult(
            is_valid=False,
            invalid_reason="ASIA_RANGE_NO_CANDLES",
        )

    # ── Rule 1.3: Contamination check ─────────────────────────────────────────
    # A candle with body >= 15 pips indicates news-driven expansion.
    # If >= 3 such candles exist, the range is contaminated.
    contaminated_candles = [
        c for c in window_candles
        if c.body_pips() >= CONTAMINATION_BODY_PIPS
    ]

    if len(contaminated_candles) >= CONTAMINATION_MAX_CANDLES:
        return AsiaRangeResult(
            is_valid=False,
            invalid_reason="ASIA_RANGE_CONTAMINATED",
            candle_count=len(window_candles),
            contaminated=True,
            window_candles=window_candles,
        )

    # If 1–2 contaminated candles exist, exclude them from ASH/ASL calculation
    # but do not invalidate the session (Rule 1.3: only 3+ = CONTAMINATED)
    clean_candles = [
        c for c in window_candles
        if c.body_pips() < CONTAMINATION_BODY_PIPS
    ]
    # Use all candles if fewer than 3 are contaminated
    calc_candles = clean_candles if len(contaminated_candles) > 0 else window_candles

    if len(calc_candles) == 0:
        return AsiaRangeResult(
            is_valid=False,
            invalid_reason="ASIA_RANGE_NO_CLEAN_CANDLES",
            candle_count=len(window_candles),
        )

    # ── Rule 1.1a/1.1b: ASH = highest wick high; ASL = lowest wick low ────────
    asia_high = max(c.high for c in calc_candles)
    asia_low  = min(c.low  for c in calc_candles)
    range_pips = round((asia_high - asia_low) / PIP_SIZE, 1)

    # ── Rule 1.2: Valid range filter 10–40 pips ────────────────────────────────
    if range_pips < ASIA_RANGE_MIN_PIPS:
        return AsiaRangeResult(
            is_valid=False,
            invalid_reason="ASIA_RANGE_TOO_NARROW",
            asia_high=asia_high,
            asia_low=asia_low,
            range_pips=range_pips,
            candle_count=len(window_candles),
            window_candles=window_candles,
        )

    if range_pips > ASIA_RANGE_MAX_PIPS:
        return AsiaRangeResult(
            is_valid=False,
            invalid_reason="ASIA_RANGE_TOO_WIDE",
            asia_high=asia_high,
            asia_low=asia_low,
            range_pips=range_pips,
            candle_count=len(window_candles),
            window_candles=window_candles,
        )

    # ── Rule 1.4: Wide range edge case (38–40 pips) ────────────────────────────
    # Elevates R:R requirement from 2.0 to 2.5 for this session.
    is_wide = range_pips >= WIDE_RANGE_PIPS
    required_rr = MIN_RR_WIDE_RANGE if is_wide else 2.0

    return AsiaRangeResult(
        is_valid=True,
        asia_high=asia_high,
        asia_low=asia_low,
        range_pips=range_pips,
        candle_count=len(window_candles),
        contaminated=len(contaminated_candles) > 0,
        is_wide_range=is_wide,
        required_rr=required_rr,
        window_candles=window_candles,
    )