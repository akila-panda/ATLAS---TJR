"""
signal-engine/models/signal.py
SignalResult and TradeState dataclasses.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class SignalResult:
    """
    Output of run_decision_tree() / run_strategy_pipeline().
    Carries full decision state for PostgreSQL logging (Section 9.1).
    """
    # Terminal outcome
    outcome:        str           # "ENTER" | "NO_TRADE"
    reason:         str           # e.g. "NO_SWEEP_IN_LKZ", "ENTER", etc.

    # Trade direction
    direction:      Optional[str] = None    # "BUY" | "SELL"

    # Entry parameters (None when outcome == NO_TRADE)
    entry_price:    Optional[float] = None
    sl_price:       Optional[float] = None
    tp1_price:      Optional[float] = None
    tp2_price:      Optional[float] = None
    tp3_price:      Optional[float] = None
    lot_size:       Optional[float] = None
    sl_pips:        Optional[float] = None
    rr_ratio:       Optional[float] = None
    risk_pct:       Optional[float] = None

    # Setup metadata
    signal_id:      Optional[str]  = None   # UUID assigned at pipeline time
    signal_str:     Optional[str]  = None   # pipe-delimited string for EA
    setup_grade:    Optional[str]  = None   # "A+" | "A" | "B" | "C"
    confluence_score: Optional[int] = None
    is_late_lkz:    bool           = False  # Rule 2.1a flag

    # Asia range data (always populated)
    asia_high:      Optional[float] = None
    asia_low:       Optional[float] = None
    asia_range_pips: Optional[float] = None

    # Sweep data
    sweep_direction: Optional[str] = None   # "BSL" | "SSL"
    sweep_extension_pips: Optional[float] = None
    sweep_time:     Optional[datetime] = None

    # Full machine-readable decision state — stored as JSON in PostgreSQL
    decision_state: Dict[str, Any] = field(default_factory=dict)

    # Timestamp
    generated_at:   datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeState:
    """
    Live trade tracking state stored in Redis after position is opened.
    Updated by trade_manager.py as the trade progresses.
    Implements Rules 6.2c, 6.3c, 5.4, 6.4b, 8.2.
    """
    # Identity
    trade_id:       str
    ticket:         int           # MT5 position ticket

    # Direction
    direction:      str           # "BUY" | "SELL"

    # Original entry parameters
    entry_price:    float
    sl_price:       float
    tp1_price:      float
    tp2_price:      float
    tp3_price:      float
    original_lot:   float         # full lot at entry (for partial close % calc)
    current_lot:    float         # remaining lot after partial closes

    # Asia range levels (needed for management logic)
    asia_high:      float
    asia_low:       float

    # Lifecycle flags
    tp1_hit:        bool  = False  # Rule 6.2c: 40% closed, BE moved
    tp2_hit:        bool  = False  # Rule 6.3:  35% closed, runner trailing
    be_moved:       bool  = False  # Rule 5.4: SL moved to break-even
    trailing_active: bool = False  # Rule 6.4b: trailing stop on runner

    # Trailing stop state
    last_swing:     Optional[float] = None  # last swing low (LONG) or high (SHORT)
    current_sl:     float = 0.0            # current SL price (updated as trailed)

    # Timestamps
    opened_at:      Optional[datetime] = None
    tp1_hit_at:     Optional[datetime] = None
    tp2_hit_at:     Optional[datetime] = None
    closed_at:      Optional[datetime] = None

    # Closure
    close_reason:   Optional[str] = None   # e.g. "TP3", "SL", "TIME_KILL", "INVALIDATION"
    close_price:    Optional[float] = None
    pnl_usd:        Optional[float] = None