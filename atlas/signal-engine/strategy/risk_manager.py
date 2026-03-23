"""
signal-engine/strategy/risk_manager.py
Risk Management Final Validation — Section 7 of TJR Operational Document.
Implements Rules 7.2, 7.3, 7.5 and Section 5.2 hard limit check.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any

from strategy.entry_model import EntryParams
from config import SL_MAX_PIPS, MIN_RR, MIN_CONFLUENCE, MAX_DAILY_LOSS_PCT


@dataclass
class RiskValidationResult:
    passed:       bool
    reason:       str   # "" if passed, fail reason if not
    detail:       str


def validate_final(
    entry:        EntryParams,
    required_rr:  float,
    confluence:   int,
    risk_state:   Dict[str, Any],
) -> RiskValidationResult:
    """
    Final risk gate — called by run_strategy_pipeline() after decision_tree.

    Validates:
    1. Session not terminated (Rule 7.3)
    2. SL distance <= 15 pips (Rule 5.2 hard limit)
    3. R:R >= required minimum (Rule 7.5, adjusted for wide range)
    4. Confluence >= 10 (Section 10 minimum)

    These checks are redundant with decision_tree nodes 9–12 but provide
    a defence-in-depth layer before writing to Redis/PostgreSQL.

    Returns:
        RiskValidationResult with passed=True if all checks pass.
    """
    # Check 1: Session terminated (Rule 7.3)
    if risk_state.get("session_terminated", False):
        return RiskValidationResult(
            passed=False,
            reason="SESSION_TERMINATED",
            detail=f"Daily loss {risk_state.get('daily_loss_pct', 0):.2f}% "
                   f">= {MAX_DAILY_LOSS_PCT}% limit — session closed",
        )

    # Check 2: SL hard limit (Rule 5.2)
    if entry.sl_pips > SL_MAX_PIPS:
        return RiskValidationResult(
            passed=False,
            reason="SL_EXCEEDS_MAX",
            detail=f"SL {entry.sl_pips:.1f}pip exceeds {SL_MAX_PIPS}pip hard limit",
        )

    # Check 3: Minimum R:R (Rule 7.5)
    if entry.rr_ratio < required_rr:
        return RiskValidationResult(
            passed=False,
            reason="INSUFFICIENT_RR",
            detail=f"R:R {entry.rr_ratio:.2f} < required minimum {required_rr:.1f}",
        )

    # Check 4: Confluence minimum (Section 10)
    if confluence < MIN_CONFLUENCE:
        return RiskValidationResult(
            passed=False,
            reason="CONFLUENCE_BELOW_MIN",
            detail=f"Score {confluence}/21 < minimum {MIN_CONFLUENCE}",
        )

    # Check 5: Lot size calculable (Rule 7.1)
    if entry.lot_size < 0.01:
        return RiskValidationResult(
            passed=False,
            reason="POSITION_SIZE_ERROR",
            detail=f"Lot size {entry.lot_size:.3f} < broker minimum 0.01",
        )

    return RiskValidationResult(
        passed=True,
        reason="",
        detail=f"All risk checks passed | SL={entry.sl_pips:.1f}pip "
               f"R:R={entry.rr_ratio:.2f} lot={entry.lot_size:.2f}",
    )