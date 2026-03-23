"""
signal-engine/models/trade.py
Trade record model matching PostgreSQL schema (001_initial.sql).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class TradeRecord:
    """
    Mirrors the `trades` table in PostgreSQL.
    Populated at signal generation and updated through the trade lifecycle.
    """
    trade_id:        str
    signal_id:       str
    direction:       str           # "BUY" | "SELL"
    symbol:          str = "EURUSD"
    setup_grade:     str = "B"

    # Prices
    entry_price:     float = 0.0
    sl_price:        float = 0.0
    tp1_price:       float = 0.0
    tp2_price:       float = 0.0
    tp3_price:       float = 0.0
    sl_pips:         float = 0.0
    rr_ratio:        float = 0.0

    # Sizing
    lot_size:        float = 0.0
    risk_pct:        float = 1.0
    risk_usd:        float = 0.0
    account_balance: float = 0.0

    # Asia range
    asia_high:       float = 0.0
    asia_low:        float = 0.0
    asia_range_pips: float = 0.0

    # Sweep
    sweep_direction:       str   = ""
    sweep_extension_pips:  float = 0.0

    # Confluence
    confluence_score: int = 0

    # Status
    status:          str = "PENDING"   # PENDING | OPEN | TP1 | TP2 | TP3 | SL | BE | CLOSED
    mt5_ticket:      Optional[int]   = None
    close_reason:    Optional[str]   = None
    close_price:     Optional[float] = None
    pnl_usd:         Optional[float] = None

    # Timestamps
    created_at:      datetime = field(default_factory=datetime.utcnow)
    opened_at:       Optional[datetime] = None
    closed_at:       Optional[datetime] = None

    # Full JSON decision state for journal review (Section 9.1)
    decision_state:  Dict[str, Any] = field(default_factory=dict)