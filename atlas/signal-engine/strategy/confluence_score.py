"""
signal-engine/strategy/confluence_score.py
Confluence Stack Scorecard — Section 10 of TJR Operational Document.
Implements all 8 factors exactly per the scoring table.
Maximum score: 21. Minimum to trade: 10.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional
import pytz

from strategy.asia_range import AsiaRangeResult
from strategy.judas_sweep import SweepResult
from strategy.structure import StructureResult
from strategy.fvg import FVGResult
from config import (
    GRADE_APLUS_MIN, GRADE_A_MIN, GRADE_B_MIN, MIN_CONFLUENCE,
    WIDE_RANGE_PIPS,
)

EST = pytz.timezone("America/New_York")


@dataclass
class ConfluenceResult:
    total:      int
    grade:      str                          # "A+" | "A" | "B" | "C"
    factors:    Dict[str, int] = field(default_factory=dict)   # factor_name → score
    reasons:    Dict[str, str] = field(default_factory=dict)   # factor_name → reason string
    passes_threshold: bool = False


def score_confluence(
    asia:        AsiaRangeResult,
    sweep:       SweepResult,
    structure:   StructureResult,
    fvg:         FVGResult,
    htf_context: dict,
    news_events: list,
    sweep_time_utc: Optional[datetime],
) -> ConfluenceResult:
    """
    Implements all 8 confluence factors from Section 10.
    Each factor scores 1 (weak), 2 (standard), or 3 (high-conviction).

    Args:
        asia:           AsiaRangeResult
        sweep:          SweepResult
        structure:      StructureResult
        fvg:            FVGResult
        htf_context:    Dict from Redis (computed by htf_context.py)
        news_events:    List of news event dicts from news_cache
        sweep_time_utc: Sweep candle datetime (UTC)

    Returns:
        ConfluenceResult with total, grade, factor scores, and reasons.
    """
    factors: Dict[str, int] = {}
    reasons: Dict[str, str] = {}

    # ── Factor 1: Daily HTF Bias (max 3) ──────────────────────────────────────
    # 1 = ambiguous (3.1a & 3.1b conflict)
    # 2 = one of 3.1a OR 3.1b confirmed
    # 3 = both confirmed + weekly alignment
    htf_score = htf_context.get("htf_bias_score", 1)
    # Clamp to 1–3
    f1 = max(1, min(3, int(htf_score)))
    factors["f1_htf_bias"] = f1
    reasons["f1_htf_bias"] = {
        1: "HTF ambiguous — 3.1a and 3.1b conflict",
        2: "One HTF factor confirmed (3.1a OR 3.1b)",
        3: "Both HTF factors confirmed + Weekly alignment",
    }.get(f1, "")

    # ── Factor 2: 4H Structural Context (max 3) ───────────────────────────────
    # 1 = 4H neutral/sideways
    # 2 = 4H BOS in reversal direction
    # 3 = 4H CHoCH + unmitigated 4H OB/FVG in reversal direction
    reversal_dir = "BULLISH" if sweep.direction == "SSL" else "BEARISH"
    h4_bos   = htf_context.get("h4_bos_direction")
    h4_choch = htf_context.get("h4_choch_direction")
    h4_fvg_valid = htf_context.get("h4_fvg_high", 0) > 0 and htf_context.get("h4_fvg_low", 0) > 0

    if h4_choch == reversal_dir and h4_fvg_valid:
        f2 = 3
        reasons["f2_h4_structure"] = "4H CHoCH + unmitigated 4H FVG in reversal direction"
    elif h4_bos == reversal_dir:
        f2 = 2
        reasons["f2_h4_structure"] = "4H BOS in reversal direction"
    else:
        f2 = 1
        reasons["f2_h4_structure"] = "4H structure neutral or opposing"
    factors["f2_h4_structure"] = f2

    # ── Factor 3: Sweep Quality (max 3) ───────────────────────────────────────
    # 1 = non-primary side (opposite to DOL framing)
    # 2 = primary side, 3–5 pip extension, wick-only
    # 3 = primary side, 3–8 pip single clean spike, closes mid-range
    ext = sweep.extension_pips
    aligns = sweep.aligns_with_dol
    is_wick = sweep.is_wick_only

    if aligns and is_wick and 3 <= ext <= 8:
        f3 = 3
        reasons["f3_sweep_quality"] = f"Primary side sweep, {ext}pip wick-only clean spike"
    elif aligns and is_wick and ext <= 5:
        f3 = 2
        reasons["f3_sweep_quality"] = f"Primary side sweep, {ext}pip wick-only"
    else:
        f3 = 1
        reasons["f3_sweep_quality"] = f"Non-primary or body-close sweep ({ext}pip)"
    factors["f3_sweep_quality"] = f3

    # ── Factor 4: Session Timing (max 3) ──────────────────────────────────────
    # 1 = sweep 04:00–05:00 EST
    # 2 = sweep 03:00–04:00 EST
    # 3 = sweep 02:00–03:00 EST (classic London open manipulation)
    f4 = 1
    timing_reason = "Sweep outside scored window"
    if sweep_time_utc:
        if sweep_time_utc.tzinfo is None:
            sweep_time_utc = sweep_time_utc.replace(tzinfo=timezone.utc)
        sweep_est = sweep_time_utc.astimezone(EST)
        h = sweep_est.hour
        if h == 2:
            f4 = 3
            timing_reason = "Sweep 02:00–03:00 EST (peak LKZ)"
        elif h == 3:
            f4 = 2
            timing_reason = "Sweep 03:00–04:00 EST"
        elif h == 4:
            f4 = 1
            timing_reason = "Sweep 04:00–05:00 EST (late LKZ)"
    factors["f4_timing"] = f4
    reasons["f4_timing"] = timing_reason

    # ── Factor 5: Asia Range Quality (max 3) ──────────────────────────────────
    # 1 = 35–40 pip (wide)
    # 2 = 20–34 pip (standard)
    # 3 = 12–19 pip (tight, clean structure)
    rp = asia.range_pips
    if 12 <= rp <= 19:
        f5 = 3
        reasons["f5_asia_range"] = f"{rp}pip tight range (12–19)"
    elif 20 <= rp <= 34:
        f5 = 2
        reasons["f5_asia_range"] = f"{rp}pip standard range (20–34)"
    else:
        f5 = 1
        reasons["f5_asia_range"] = f"{rp}pip wide range (35–40)"
    factors["f5_asia_range"] = f5

    # ── Factor 6: Structural Confirmation (max 3) ─────────────────────────────
    # 1 = 5M CHoCH only
    # 2 = 15M CHoCH confirmed
    # 3 = 15M CHoCH + 5M BOS + displacement candle all present
    if structure.full_confirmation:
        f6 = 3
        reasons["f6_structure"] = "15M CHoCH + 5M BOS + Displacement all confirmed"
    elif structure.choch_15m:
        f6 = 2
        reasons["f6_structure"] = "15M CHoCH confirmed"
    elif structure.choch_5m:
        f6 = 1
        reasons["f6_structure"] = "5M CHoCH only (no 15M confirmation)"
    else:
        f6 = 1
        reasons["f6_structure"] = "Minimal structural confirmation"
    factors["f6_structure"] = f6

    # ── Factor 7: Entry Zone Quality (max 3) ──────────────────────────────────
    # 1 = OB entry only, no FVG
    # 2 = FVG present, entry at 50% midpoint
    # 3 = FVG present + confluent with 4H OB or Daily OB zone
    h4_fvg_h = htf_context.get("h4_fvg_high", 0)
    h4_fvg_l = htf_context.get("h4_fvg_low", 0)
    fvg_in_h4_zone = False
    if fvg.found and h4_fvg_h > 0 and h4_fvg_l > 0:
        fvg_in_h4_zone = h4_fvg_l <= fvg.fvg_midpoint <= h4_fvg_h

    if fvg.found and fvg_in_h4_zone:
        f7 = 3
        reasons["f7_entry_zone"] = "FVG at 4H OB/FVG confluence"
    elif fvg.found:
        f7 = 2
        reasons["f7_entry_zone"] = "FVG entry at 50% midpoint"
    else:
        f7 = 1
        reasons["f7_entry_zone"] = "OB entry only (no FVG present)"
    factors["f7_entry_zone"] = f7

    # ── Factor 8: Macro Calendar (max 3) ──────────────────────────────────────
    # 1 = orange-folder event within LKZ
    # 2 = no events 02:00–08:00 EST
    # 3 = no events all session + prior day data absorbed
    red_in_lkz    = _has_news_in_window(news_events, impact="red",    h_start=2, h_end=5)
    orange_in_lkz = _has_news_in_window(news_events, impact="orange", h_start=2, h_end=5)
    any_02_08     = _has_news_in_window(news_events, impact=None,     h_start=2, h_end=8)

    if red_in_lkz:
        # Red-folder in LKZ → should have been caught by news_filter, but score low anyway
        f8 = 1
        reasons["f8_news"] = "Red-folder event within LKZ (should be NO_TRADE)"
    elif orange_in_lkz:
        f8 = 1
        reasons["f8_news"] = "Orange-folder event within LKZ"
    elif any_02_08:
        f8 = 1
        reasons["f8_news"] = "Event scheduled 02:00–08:00 EST"
    elif not any_02_08:
        f8 = 2
        reasons["f8_news"] = "No events scheduled 02:00–08:00 EST"
    else:
        f8 = 2
        reasons["f8_news"] = "Calendar clear"
    # Check if prior session was also clean (score 3)
    prior_day_red = _has_news_in_window(news_events, impact="red", h_start=0, h_end=2)
    if f8 == 2 and not prior_day_red:
        f8 = 3
        reasons["f8_news"] = "No events all session + prior data absorbed"
    factors["f8_news"] = f8

    # ── Total and Grade ────────────────────────────────────────────────────────
    total = sum(factors.values())

    if total >= GRADE_APLUS_MIN:
        grade = "A+"
    elif total >= GRADE_A_MIN:
        grade = "A"
    elif total >= GRADE_B_MIN:
        grade = "B"
    else:
        grade = "C"

    return ConfluenceResult(
        total=total,
        grade=grade,
        factors=factors,
        reasons=reasons,
        passes_threshold=total >= MIN_CONFLUENCE,
    )


def _has_news_in_window(
    events:  list,
    impact:  Optional[str],   # "red" | "orange" | None (any)
    h_start: int,
    h_end:   int,
) -> bool:
    """Check if any news event of given impact falls within EST hour window."""
    for ev in events:
        ev_hour = ev.get("hour_est", -1)
        ev_impact = ev.get("impact", "").lower()
        if h_start <= ev_hour < h_end:
            if impact is None or ev_impact == impact:
                return True
    return False