"""
signal-engine/strategy/entry_model.py
Entry Execution Model — Sections 4, 5, 6 of TJR Operational Document.
Calculates entry price, SL, TP1/TP2/TP3, lot size, and R:R.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from strategy.asia_range import AsiaRangeResult
from strategy.judas_sweep import SweepResult
from strategy.fvg import FVGResult
from strategy.order_block import OBResult
from config import (
    SL_BUFFER_PIPS, SL_BUFFER_ELEVATED_PIPS, SL_MAX_PIPS,
    SWEEP_MAX_PIPS,
    MAX_RISK_PCT, LATE_LKZ_RISK_PCT,
    PIP_SIZE, PIP_VALUE_STD,
    ACCOUNT_BALANCE,
)


@dataclass
class EntryParams:
    direction:   str        # "BUY" | "SELL"
    entry_price: float
    sl_price:    float
    tp1_price:   float      # Rule 6.2: 40% close at midpoint of Asia range
    tp2_price:   float      # Rule 6.3: 35% close at opposing Asia level
    tp3_price:   float      # Rule 6.4: HTF DOL runner (25%)
    sl_pips:     float      # distance from entry to SL
    rr_ratio:    float      # abs(tp2 - entry) / abs(entry - sl)
    lot_size:    float      # Rule 7.1 position sizing
    risk_pct:    float      # 1.0 standard, 0.5 late LKZ
    risk_usd:    float      # dollar risk on this trade
    entry_method: str       # "FVG_LIMIT" | "OB_LIMIT"
    sl_buffer_used: float   # actual buffer applied (3 or 5 pips)


def calculate_entry(
    sweep:       SweepResult,
    asia:        AsiaRangeResult,
    fvg:         FVGResult,
    ob:          OBResult,
    htf_context: dict,
    account_balance: float = ACCOUNT_BALANCE,
) -> Optional[EntryParams]:
    """
    Implements Sections 4, 5, 6.

    Entry price priority: FVG midpoint (Rule 4.2) > OB entry (Rule 4.3).

    SL placement:
    - Rule 5.1: beyond sweep wick + buffer
    - Rule 5.1c: elevated buffer (5 pips) for deep sweeps (>5 pips extension)
    - Rule 5.3: entry adjustment on deep sweeps to stay within 15-pip SL limit

    TP structure (Rules 6.2, 6.3, 6.4):
    - LONG: TP1=ASL+(range/2), TP2=ASH, TP3=HTF DOL target
    - SHORT: TP1=ASH-(range/2), TP2=ASL, TP3=HTF DOL target

    Lot sizing (Rule 7.1):
    - lot = (balance * risk_pct/100) / (sl_pips * PIP_VALUE_STD)

    Returns None if no valid entry zone is available.
    """
    if not sweep.is_valid:
        return None

    reversal_up = sweep.direction == "SSL"   # SSL sweep → LONG trade
    direction   = "BUY" if reversal_up else "SELL"

    # ── Determine entry price ─────────────────────────────────────────────────
    entry_method = "FVG_LIMIT"
    if fvg.found and not fvg.is_violated and not fvg.is_expired:
        entry_price = fvg.fvg_midpoint
        entry_method = "FVG_LIMIT"
    elif ob.found:
        entry_price = ob.entry_price
        entry_method = "OB_LIMIT"
    else:
        return None

    # ── SL placement (Rules 5.1–5.3) ─────────────────────────────────────────
    # Rule 5.1c: Use elevated buffer for deep sweeps (extension > 5 pips)
    # or when sweep was close to a significant level (handled at elevated threshold)
    is_deep_sweep = sweep.extension_pips > 5.0
    sl_buffer = SL_BUFFER_ELEVATED_PIPS if is_deep_sweep else SL_BUFFER_PIPS

    if sweep.sweep_candle is None:
        return None

    if reversal_up:
        # LONG: SL below the SSL sweep candle's wick low − buffer (Rule 5.1a)
        raw_sl = sweep.sweep_candle.low - (sl_buffer * PIP_SIZE)
        sl_price = raw_sl
    else:
        # SHORT: SL above the BSL sweep candle's wick high + buffer (Rule 5.1b)
        raw_sl = sweep.sweep_candle.high + (sl_buffer * PIP_SIZE)
        sl_price = raw_sl

    sl_pips = abs(entry_price - sl_price) / PIP_SIZE

    # ── Rule 5.3c: Deep sweep SL adjustment ──────────────────────────────────
    # If SL from entry exceeds 15 pips, adjust entry closer to OB boundary
    # to compress SL distance. Do NOT widen the SL.
    if sl_pips > SL_MAX_PIPS:
        # Attempt to adjust entry price to bring SL within 15-pip limit
        max_sl_distance = SL_MAX_PIPS * PIP_SIZE
        if reversal_up:
            # Move entry DOWN closer to SL to reduce distance
            entry_price = sl_price + max_sl_distance
        else:
            # Move entry UP closer to SL
            entry_price = sl_price - max_sl_distance
        sl_pips = abs(entry_price - sl_price) / PIP_SIZE

    # Still exceeds max after adjustment — entry_model returns params;
    # decision_tree node 9 will catch this and return NO_TRADE
    sl_pips = round(sl_pips, 1)

    # ── Geometry guard ────────────────────────────────────────────────────────
    # A long's stop must sit below its entry and a short's above it. Rule 5.1
    # anchors the stop to the sweep candle's wick, but the FVG can form beyond
    # that wick — price sweeps, keeps running, then displaces from a level past
    # the original extreme — which puts the stop on the wrong side of the entry.
    # Nothing downstream checked this: risk became abs(entry - sl), so a short
    # with its stop below entry was recorded as hitting that stop for +1R, and
    # MT5 would have rejected the live order as invalid.
    if reversal_up and sl_price >= entry_price:
        return None
    if not reversal_up and sl_price <= entry_price:
        return None

    # Same problem on the target side: rr_ratio uses abs(), so a TP2 on the
    # wrong side of entry still produced a healthy-looking R:R.
    tp2_check = asia.asia_high if reversal_up else asia.asia_low
    if reversal_up and tp2_check <= entry_price:
        return None
    if not reversal_up and tp2_check >= entry_price:
        return None

    # ── TP structure (Rules 6.2, 6.3, 6.4) ───────────────────────────────────
    half_range = (asia.range_pips / 2.0) * PIP_SIZE

    if reversal_up:
        # LONG TPs
        tp1_price = asia.asia_low  + half_range          # Rule 6.2a: ASL + range/2
        tp2_price = asia.asia_high                        # Rule 6.3a: ASH
    else:
        # SHORT TPs
        tp1_price = asia.asia_high - half_range          # Rule 6.2b: ASH − range/2
        tp2_price = asia.asia_low                        # Rule 6.3b: ASL

    # TP3: HTF DOL target price from context (Rule 6.4a)
    tp3_price = htf_context.get("dol_target_price", tp2_price)
    if tp3_price == 0.0:
        tp3_price = tp2_price  # fallback to TP2 if no HTF target set

    # ── R:R ratio (to TP2) ────────────────────────────────────────────────────
    rr_ratio = abs(tp2_price - entry_price) / abs(entry_price - sl_price) \
               if abs(entry_price - sl_price) > 0 else 0.0
    rr_ratio = round(rr_ratio, 2)

    # ── Risk allocation (Rules 7.2 and 2.1a) ─────────────────────────────────
    risk_pct = LATE_LKZ_RISK_PCT if sweep.is_late_lkz else MAX_RISK_PCT

    # ── Lot sizing (Rule 7.1) ─────────────────────────────────────────────────
    # lot = (balance × risk%) / (sl_pips × $10 per pip per standard lot)
    risk_usd = account_balance * (risk_pct / 100.0)
    lot_size = risk_usd / (sl_pips * PIP_VALUE_STD) if sl_pips > 0 else 0.0
    # Round to 2 decimal places (standard lot sizing)
    lot_size = round(lot_size, 2)

    return EntryParams(
        direction=direction,
        entry_price=round(entry_price, 5),
        sl_price=round(sl_price, 5),
        tp1_price=round(tp1_price, 5),
        tp2_price=round(tp2_price, 5),
        tp3_price=round(tp3_price, 5),
        sl_pips=sl_pips,
        rr_ratio=rr_ratio,
        lot_size=lot_size,
        risk_pct=risk_pct,
        risk_usd=round(risk_usd, 2),
        entry_method=entry_method,
        sl_buffer_used=sl_buffer,
    )