"""
signal-engine/strategy/htf_context.py
Higher Timeframe Context — Section 3 of TJR Operational Document.
Implements Rules 3.1 (Daily DOL), 3.2 (4H structure), 3.3 (counter-trend permission).
Called by scheduler on new D1/H4 bar; result stored in Redis.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from models.candle import Candle
from config import PIP_SIZE


@dataclass
class HTFContext:
    # Rule 3.1: Daily DOL
    dol_direction:      str   = "AMBIGUOUS"   # "BULLISH" | "BEARISH" | "AMBIGUOUS"
    dol_target_price:   float = 0.0
    daily_fvg_above:    bool  = False   # Rule 3.1a: unmitigated Daily FVG above price
    daily_fvg_below:    bool  = False
    daily_bsl_above:    bool  = False   # Rule 3.1b: untested Daily swing high above
    daily_ssl_below:    bool  = False
    weekly_swept:       bool  = False   # Rule 3.1c: Weekly level swept in last 3 sessions

    # Rule 3.2: 4H structural context
    h4_bos_direction:   Optional[str] = None  # "BULLISH" | "BEARISH"
    h4_choch_direction: Optional[str] = None
    h4_ob_price:        float = 0.0
    h4_fvg_high:        float = 0.0
    h4_fvg_low:         float = 0.0
    h4_structure_valid: bool  = False

    # Computed fields
    htf_bias_score:     int   = 1   # 1=ambiguous, 2=one confirmed, 3=both+weekly
    counter_trend_permitted: bool = False   # Rule 3.3

    # Raw dict for Redis storage
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dol_direction":        self.dol_direction,
            "dol_target_price":     self.dol_target_price,
            "daily_fvg_above":      self.daily_fvg_above,
            "daily_fvg_below":      self.daily_fvg_below,
            "daily_bsl_above":      self.daily_bsl_above,
            "daily_ssl_below":      self.daily_ssl_below,
            "weekly_swept":         self.weekly_swept,
            "h4_bos_direction":     self.h4_bos_direction,
            "h4_choch_direction":   self.h4_choch_direction,
            "h4_ob_price":          self.h4_ob_price,
            "h4_fvg_high":          self.h4_fvg_high,
            "h4_fvg_low":           self.h4_fvg_low,
            "h4_structure_valid":   self.h4_structure_valid,
            "htf_bias_score":       self.htf_bias_score,
            "counter_trend_permitted": self.counter_trend_permitted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HTFContext":
        ctx = cls()
        for k, v in d.items():
            if hasattr(ctx, k):
                setattr(ctx, k, v)
        return ctx


def compute_htf_context(
    candles_d1: List[Candle],
    candles_h4: List[Candle],
) -> HTFContext:
    """
    Implements Section 3 HTF narrative.

    Rules 3.1a/3.1b: Identify Daily DOL by finding:
    - Unmitigated Daily FVG above/below current price (3.1a)
    - Untested Daily swing high (BSL) or low (SSL) within ADR distance (3.1b)

    Rule 3.2: 4H structural context.
    Rule 3.3: Counter-trend permission (not computed here — requires trade context).

    Args:
        candles_d1: Daily candles (oldest-first, ~30 candles).
        candles_h4: 4H candles (oldest-first, ~50 candles).

    Returns:
        HTFContext with all computed fields.
    """
    ctx = HTFContext()

    if len(candles_d1) < 5:
        return ctx

    current_price = candles_d1[-1].close

    # ── Rule 3.1a: Unmitigated Daily FVG ─────────────────────────────────────
    # A Daily FVG above price = bullish draw (DOL above)
    # A Daily FVG below price = bearish draw (DOL below)
    fvg_above, fvg_above_price = _find_unmitigated_fvg(candles_d1, current_price, direction="above")
    fvg_below, fvg_below_price = _find_unmitigated_fvg(candles_d1, current_price, direction="below")

    ctx.daily_fvg_above = fvg_above
    ctx.daily_fvg_below = fvg_below

    # ── Rule 3.1b: Untested Daily swing highs/lows ────────────────────────────
    # BSL above: prior Daily swing high not yet taken
    # SSL below: prior Daily swing low not yet taken
    ctx.daily_bsl_above = _has_untested_swing_high(candles_d1, current_price)
    ctx.daily_ssl_below = _has_untested_swing_low(candles_d1, current_price)

    # ── Rule 3.1c: Weekly level swept in last 3 sessions ────────────────────
    ctx.weekly_swept = _weekly_level_swept(candles_d1)

    # ── Determine DOL direction (Rules 3.1a + 3.1b must agree) ───────────────
    bullish_signals = int(ctx.daily_fvg_above) + int(ctx.daily_bsl_above)
    bearish_signals = int(ctx.daily_fvg_below) + int(ctx.daily_ssl_below)

    if bullish_signals >= 2 and bearish_signals == 0:
        ctx.dol_direction   = "BULLISH"
        ctx.dol_target_price = fvg_above_price if fvg_above else 0.0
        ctx.htf_bias_score  = 3 if ctx.weekly_swept else 2
    elif bearish_signals >= 2 and bullish_signals == 0:
        ctx.dol_direction   = "BEARISH"
        ctx.dol_target_price = fvg_below_price if fvg_below else 0.0
        ctx.htf_bias_score  = 3 if ctx.weekly_swept else 2
    elif bullish_signals == 1 or bearish_signals == 1:
        # Only one factor confirmed → ambiguous but downgraded (Rule 3.1)
        if bullish_signals > bearish_signals:
            ctx.dol_direction = "BULLISH"
        elif bearish_signals > bullish_signals:
            ctx.dol_direction = "BEARISH"
        else:
            ctx.dol_direction = "AMBIGUOUS"
        ctx.htf_bias_score = 1
    else:
        ctx.dol_direction  = "AMBIGUOUS"
        ctx.htf_bias_score = 1

    # ── Rule 3.2: 4H structural context ──────────────────────────────────────
    if len(candles_h4) >= 10:
        ctx.h4_bos_direction  = _detect_h4_bos(candles_h4)
        ctx.h4_choch_direction = _detect_h4_choch(candles_h4)
        fvg_h, fvg_l          = _find_h4_fvg(candles_h4, ctx.dol_direction)
        ctx.h4_fvg_high       = fvg_h
        ctx.h4_fvg_low        = fvg_l
        ctx.h4_structure_valid = ctx.h4_bos_direction is not None

    return ctx


# ─── Private helpers ──────────────────────────────────────────────────────────

def _find_unmitigated_fvg(
    candles:       List[Candle],
    current_price: float,
    direction:     str,           # "above" | "below"
) -> tuple[bool, float]:
    """
    Scan Daily candles for an unmitigated FVG in the given direction.
    An FVG is 'unmitigated' if price has not returned to fill it since formation.
    Returns (found, fvg_mid_price).
    """
    for i in range(1, len(candles) - 1):
        c1, c2, c3 = candles[i - 1], candles[i], candles[i + 1]

        if direction == "above":
            # Bullish FVG above current price: gap between c1.high and c3.low
            if c1.high < c3.low:
                fvg_mid = (c1.high + c3.low) / 2.0
                if fvg_mid > current_price:
                    # Check if price has re-entered the FVG since formation
                    subsequent = candles[i + 2:]
                    mitigated = any(c.low <= c3.low for c in subsequent)
                    if not mitigated:
                        return True, fvg_mid
        else:
            # Bearish FVG below current price: gap between c1.low and c3.high
            if c1.low > c3.high:
                fvg_mid = (c1.low + c3.high) / 2.0
                if fvg_mid < current_price:
                    subsequent = candles[i + 2:]
                    mitigated = any(c.high >= c3.high for c in subsequent)
                    if not mitigated:
                        return True, fvg_mid

    return False, 0.0


def _has_untested_swing_high(candles: List[Candle], current_price: float) -> bool:
    """
    Rule 3.1b: Untested Daily swing high (BSL) exists above current price.
    A swing high is a candle with a higher high than both adjacent candles.
    """
    for i in range(1, len(candles) - 1):
        c = candles[i]
        if c.high > candles[i - 1].high and c.high > candles[i + 1].high:
            if c.high > current_price:
                # Check not yet taken by subsequent price action
                subsequent = candles[i + 1:]
                taken = any(s.high >= c.high for s in subsequent)
                if not taken:
                    return True
    return False


def _has_untested_swing_low(candles: List[Candle], current_price: float) -> bool:
    """
    Rule 3.1b: Untested Daily swing low (SSL) exists below current price.
    """
    for i in range(1, len(candles) - 1):
        c = candles[i]
        if c.low < candles[i - 1].low and c.low < candles[i + 1].low:
            if c.low < current_price:
                subsequent = candles[i + 1:]
                taken = any(s.low <= c.low for s in subsequent)
                if not taken:
                    return True
    return False


def _detect_h4_bos(candles: List[Candle]) -> Optional[str]:
    """Rule 3.2: Most recent 4H BOS direction."""
    for i in range(len(candles) - 1, 3, -1):
        c = candles[i]
        prior_high = max(x.high for x in candles[i - 4: i])
        prior_low  = min(x.low  for x in candles[i - 4: i])
        if c.close > prior_high:
            return "BULLISH"
        if c.close < prior_low:
            return "BEARISH"
    return None


def _detect_h4_choch(candles: List[Candle]) -> Optional[str]:
    """Rule 3.2: Most recent 4H CHoCH direction."""
    # Simplified: look for a candle that breaks the opposing structure
    for i in range(len(candles) - 1, 5, -1):
        c = candles[i]
        recent_high = max(x.high for x in candles[i - 3: i])
        recent_low  = min(x.low  for x in candles[i - 3: i])
        if c.is_bearish() and c.close < recent_low:
            return "BEARISH"
        if c.is_bullish() and c.close > recent_high:
            return "BULLISH"
    return None


def _find_h4_fvg(
    candles:       List[Candle],
    dol_direction: str,
) -> tuple[float, float]:
    """Rule 3.2: Find the most recent unmitigated 4H FVG in DOL direction."""
    for i in range(len(candles) - 2, 0, -1):
        c1, c2, c3 = candles[i - 1], candles[i], candles[i + 1]
        if dol_direction == "BULLISH":
            if c1.high < c3.low:
                return c3.low, c1.high
        elif dol_direction == "BEARISH":
            if c1.low > c3.high:
                return c1.low, c3.high
    return 0.0, 0.0


def _weekly_level_swept(candles_d1: List[Candle], lookback_sessions: int = 3) -> bool:
    """
    Rule 3.1c: has a prior weekly high or low been swept in the last N sessions?

    ATLAS receives no weekly candles — the EA pushes M5/M15/H4/D1 only — so the
    weekly levels are rebuilt by grouping Daily candles into ISO weeks. The
    reference level is the last *completed* week; the sweep test is a wick of
    any of the last `lookback_sessions` daily candles beyond that level.

    Returns False when there is not enough history to name a completed week.
    """
    if len(candles_d1) < lookback_sessions + 1:
        return False

    # Group daily candles by ISO (year, week).
    weeks: dict[tuple[int, int], list[Candle]] = {}
    for c in candles_d1:
        iso = c.time.isocalendar()
        weeks.setdefault((iso[0], iso[1]), []).append(c)

    if len(weeks) < 2:
        return False

    # The most recent key is the in-progress week; the one before it is complete.
    ordered = sorted(weeks.keys())
    prev_week = weeks[ordered[-2]]
    prev_high = max(c.high for c in prev_week)
    prev_low  = min(c.low  for c in prev_week)

    recent = candles_d1[-lookback_sessions:]
    return any(c.high > prev_high or c.low < prev_low for c in recent)
