"""
signal-engine/strategy/decision_tree.py
Decision Tree — Section 11 of TJR Operational Document.
14 nodes in exact order. First FAIL = NO_TRADE with specific reason code.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from strategy.asia_range import AsiaRangeResult
from strategy.judas_sweep import SweepResult
from strategy.structure import StructureResult
from strategy.fvg import FVGResult, is_fvg_expired
from strategy.confluence_score import ConfluenceResult
from config import SL_MAX_PIPS, MIN_CONFLUENCE, MIN_RR


@dataclass
class DTNode:
    """Represents one decision tree node."""
    node_id:    int
    name:       str
    passed:     bool
    reason:     str   # reason code on FAIL, "PASS" on pass
    detail:     str   # human-readable detail for logging


@dataclass
class DTResult:
    outcome:    str              # "ENTER" | "NO_TRADE"
    reason:     str              # reason code of first failing node, or "ENTER"
    nodes:      List[DTNode] = field(default_factory=list)
    node_count: int = 0          # how many nodes were evaluated before terminal


def run_decision_tree(
    news_blocked:       bool,
    asia:               AsiaRangeResult,
    sweep:              SweepResult,
    structure:          StructureResult,
    fvg:                FVGResult,
    ob_found:           bool,
    entry_sl_pips:      float,
    entry_rr_ratio:     float,
    required_rr:        float,
    confluence:         ConfluenceResult,
    risk_state:         Dict[str, Any],
    entry_lot_size:     float,
    now_utc:            datetime,
) -> DTResult:
    """
    Implements Section 11 Decision Tree exactly.

    14 nodes evaluated in order. First node that returns False → NO_TRADE
    with that node's reason code. All 14 pass → ENTER.

    Args:
        news_blocked:     True if red-folder news blocks LKZ (Rule 7.4a)
        asia:             AsiaRangeResult
        sweep:            SweepResult
        structure:        StructureResult
        fvg:              FVGResult
        ob_found:         True if a valid OB entry zone was found (Rule 4.3)
        entry_sl_pips:    Calculated SL distance in pips from entry
        entry_rr_ratio:   Calculated R:R ratio to TP2
        required_rr:      Minimum R:R (2.0 standard, 2.5 wide range)
        confluence:       ConfluenceResult with total score
        risk_state:       Dict from Redis with session_terminated flag
        entry_lot_size:   Calculated lot size (Rule 7.1)
        now_utc:          Current UTC datetime

    Returns:
        DTResult with outcome, reason code, and all evaluated node states.
    """
    nodes: List[DTNode] = []

    def evaluate(node_id: int, name: str, condition: bool,
                 fail_reason: str, detail: str) -> bool:
        node = DTNode(
            node_id=node_id,
            name=name,
            passed=condition,
            reason="PASS" if condition else fail_reason,
            detail=detail,
        )
        nodes.append(node)
        return condition

    # ── Node 1: News filter (Rule 7.4a) ──────────────────────────────────────
    if not evaluate(
        1, "NEWS_FILTER",
        not news_blocked,
        "NEWS_FILTER_FAIL",
        "Red-folder news event scheduled within LKZ 02:00–05:00 EST",
    ):
        return DTResult("NO_TRADE", "NEWS_FILTER_FAIL", nodes, 1)

    # ── Node 2: Asia range valid (Rules 1.1–1.4) ─────────────────────────────
    if not evaluate(
        2, "ASIA_RANGE_VALID",
        asia.is_valid,
        asia.invalid_reason or "ASIA_RANGE_INVALID",
        f"Asia range {asia.range_pips}pip | valid={asia.is_valid}",
    ):
        return DTResult("NO_TRADE", asia.invalid_reason or "ASIA_RANGE_INVALID", nodes, 2)

    # ── Node 3: Sweep detected in LKZ (Rule 2.1) ─────────────────────────────
    if not evaluate(
        3, "SWEEP_DETECTED",
        sweep.detected,
        "NO_SWEEP_IN_LKZ",
        "No wick sweep of ASH or ASL detected within 02:00–05:00 EST",
    ):
        return DTResult("NO_TRADE", "NO_SWEEP_IN_LKZ", nodes, 3)

    # ── Node 4: Sweep valid (Rules 2.2, 2.3, 2.4, 2.5) ──────────────────────
    if not evaluate(
        4, "SWEEP_VALID",
        sweep.is_valid,
        sweep.invalid_reason or "SWEEP_INVALID",
        f"Sweep direction={sweep.direction} ext={sweep.extension_pips}pip "
        f"wick_only={sweep.is_wick_only} aligns_dol={sweep.aligns_with_dol}",
    ):
        return DTResult("NO_TRADE", sweep.invalid_reason or "SWEEP_INVALID", nodes, 4)

    # ── Node 5: No double sweep (Rule 2.6) ───────────────────────────────────
    double_sweep = sweep.invalid_reason == "DOUBLE_SWEEP"
    if not evaluate(
        5, "NO_DOUBLE_SWEEP",
        not double_sweep,
        "DOUBLE_SWEEP",
        "Both ASH and ASL swept within LKZ — directional intent ambiguous",
    ):
        return DTResult("NO_TRADE", "DOUBLE_SWEEP", nodes, 5)

    # ── Node 6: 15M CHoCH confirmed (Rule 3.4a) ──────────────────────────────
    if not evaluate(
        6, "CHOCH_15M",
        structure.choch_15m,
        "NO_15M_CHOCH",
        "No Change of Character on 15M timeframe post-sweep",
    ):
        return DTResult("NO_TRADE", "NO_15M_CHOCH", nodes, 6)

    # ── Node 7: Displacement candle present (Rule 4.1) ───────────────────────
    if not evaluate(
        7, "DISPLACEMENT",
        structure.displacement,
        "NO_DISPLACEMENT",
        "No displacement candle with FVG found on 5M post-CHoCH",
    ):
        return DTResult("NO_TRADE", "NO_DISPLACEMENT", nodes, 7)

    # ── Node 8: FVG or OB entry zone exists (Rules 4.2, 4.3) ────────────────
    has_entry_zone = (fvg.found and not fvg.is_violated) or ob_found
    if not evaluate(
        8, "ENTRY_ZONE",
        has_entry_zone,
        "NO_ENTRY_ZONE",
        f"FVG found={fvg.found} violated={fvg.is_violated} | OB found={ob_found}",
    ):
        return DTResult("NO_TRADE", "NO_ENTRY_ZONE", nodes, 8)

    # ── Node 9: SL distance within hard limit (Rule 5.2) ─────────────────────
    if not evaluate(
        9, "SL_MAX_CHECK",
        entry_sl_pips <= SL_MAX_PIPS,
        "SL_EXCEEDS_MAX",
        f"SL distance {entry_sl_pips:.1f}pip exceeds hard limit of {SL_MAX_PIPS}pip",
    ):
        return DTResult("NO_TRADE", "SL_EXCEEDS_MAX", nodes, 9)

    # ── Node 10: Minimum R:R met (Rule 7.5) ──────────────────────────────────
    if not evaluate(
        10, "RR_CHECK",
        entry_rr_ratio >= required_rr,
        "INSUFFICIENT_RR",
        f"R:R {entry_rr_ratio:.2f} < required {required_rr:.1f}",
    ):
        return DTResult("NO_TRADE", "INSUFFICIENT_RR", nodes, 10)

    # ── Node 11: Confluence threshold met (Section 10) ───────────────────────
    if not evaluate(
        11, "CONFLUENCE_CHECK",
        confluence.total >= MIN_CONFLUENCE,
        "CONFLUENCE_BELOW_MIN",
        f"Confluence score {confluence.total}/21 below minimum {MIN_CONFLUENCE}",
    ):
        return DTResult("NO_TRADE", "CONFLUENCE_BELOW_MIN", nodes, 11)

    # ── Node 12: Session not terminated (Rule 7.3) ───────────────────────────
    session_terminated = risk_state.get("session_terminated", False)
    if not evaluate(
        12, "SESSION_ACTIVE",
        not session_terminated,
        "SESSION_TERMINATED",
        f"Daily loss limit reached: {risk_state.get('daily_loss_pct', 0):.2f}%",
    ):
        return DTResult("NO_TRADE", "SESSION_TERMINATED", nodes, 12)

    # ── Node 13: Lot size calculable (Rule 7.1) ───────────────────────────────
    if not evaluate(
        13, "POSITION_SIZE_VALID",
        entry_lot_size >= 0.01,
        "POSITION_SIZE_ERROR",
        f"Calculated lot size {entry_lot_size:.3f} below broker minimum 0.01",
    ):
        return DTResult("NO_TRADE", "POSITION_SIZE_ERROR", nodes, 13)

    # ── Node 14: Setup not expired (Rule 4.2d) ───────────────────────────────
    expired = is_fvg_expired(now_utc)
    if not evaluate(
        14, "SETUP_NOT_EXPIRED",
        not expired,
        "SETUP_EXPIRED",
        "Current time is past 05:30 EST — limit order window closed",
    ):
        return DTResult("NO_TRADE", "SETUP_EXPIRED", nodes, 14)

    # ── All 14 nodes passed ───────────────────────────────────────────────────
    return DTResult("ENTER", "ENTER", nodes, 14)