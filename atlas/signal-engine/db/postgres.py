"""
signal-engine/db/postgres.py
asyncpg connection pool and all PostgreSQL operations.
Tables defined in api-server/src/db/migrations/001_initial.sql.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncpg
from config import POSTGRES_DSN

_pool: Optional[asyncpg.Pool] = None


async def init_postgres() -> None:
    """Called once on FastAPI startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=POSTGRES_DSN,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_postgres() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _p() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Postgres pool not initialised — call init_postgres() first")
    return _pool


# ─── Signal Log ───────────────────────────────────────────────────────────────

async def insert_signal_log(
    signal_id:      str,
    outcome:        str,
    reason:         str,
    direction:      Optional[str],
    confluence_score: Optional[int],
    setup_grade:    Optional[str],
    asia_high:      Optional[float],
    asia_low:       Optional[float],
    asia_range_pips: Optional[float],
    sweep_direction: Optional[str],
    sweep_extension_pips: Optional[float],
    decision_state: Dict[str, Any],
    generated_at:   datetime,
) -> None:
    """
    Log every pipeline run to signal_logs table — including all NO_TRADE outcomes.
    Implements the journaling requirement from Section 9.1.
    """
    await _p().execute(
        """
        INSERT INTO signal_logs (
            signal_id, outcome, reason, direction,
            confluence_score, setup_grade,
            asia_high, asia_low, asia_range_pips,
            sweep_direction, sweep_extension_pips,
            decision_state, generated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
        ON CONFLICT (signal_id) DO NOTHING
        """,
        signal_id, outcome, reason, direction,
        confluence_score, setup_grade,
        asia_high, asia_low, asia_range_pips,
        sweep_direction, sweep_extension_pips,
        json.dumps(decision_state), generated_at,
    )


# ─── Trades ───────────────────────────────────────────────────────────────────

async def insert_trade(
    trade_id:        str,
    signal_id:       str,
    direction:       str,
    entry_price:     float,
    sl_price:        float,
    tp1_price:       float,
    tp2_price:       float,
    tp3_price:       float,
    sl_pips:         float,
    rr_ratio:        float,
    lot_size:        float,
    risk_pct:        float,
    risk_usd:        float,
    account_balance: float,
    asia_high:       float,
    asia_low:        float,
    asia_range_pips: float,
    sweep_direction: str,
    sweep_extension_pips: float,
    confluence_score: int,
    setup_grade:     str,
    decision_state:  Dict[str, Any],
) -> None:
    """Insert a new trade record at signal generation time (status='PENDING')."""
    await _p().execute(
        """
        INSERT INTO trades (
            trade_id, signal_id, direction, symbol,
            entry_price, sl_price, tp1_price, tp2_price, tp3_price,
            sl_pips, rr_ratio, lot_size, risk_pct, risk_usd, account_balance,
            asia_high, asia_low, asia_range_pips,
            sweep_direction, sweep_extension_pips,
            confluence_score, setup_grade,
            status, decision_state, created_at
        ) VALUES (
            $1,$2,$3,'EURUSD',
            $4,$5,$6,$7,$8,
            $9,$10,$11,$12,$13,$14,
            $15,$16,$17,
            $18,$19,
            $20,$21,
            'PENDING',$22,NOW()
        )
        ON CONFLICT (trade_id) DO NOTHING
        """,
        trade_id, signal_id, direction,
        entry_price, sl_price, tp1_price, tp2_price, tp3_price,
        sl_pips, rr_ratio, lot_size, risk_pct, risk_usd, account_balance,
        asia_high, asia_low, asia_range_pips,
        sweep_direction, sweep_extension_pips,
        confluence_score, setup_grade,
        json.dumps(decision_state),
    )


async def update_trade_status(
    trade_id: str,
    status:   str,
    mt5_ticket: Optional[int] = None,
    opened_at:  Optional[datetime] = None,
) -> None:
    """Update trade status after EA ACK (PENDING → OPEN)."""
    if mt5_ticket is not None and opened_at is not None:
        await _p().execute(
            """
            UPDATE trades
            SET status=$2, mt5_ticket=$3, opened_at=$4
            WHERE trade_id=$1
            """,
            trade_id, status, mt5_ticket, opened_at,
        )
    else:
        await _p().execute(
            "UPDATE trades SET status=$2 WHERE trade_id=$1",
            trade_id, status,
        )


async def insert_trade_event(
    trade_id:    str,
    event_type:  str,
    description: str,
    price:       Optional[float] = None,
    lots:        Optional[float] = None,
    pnl_usd:     Optional[float] = None,
) -> None:
    """
    Record a lifecycle event for a trade (TP1 hit, SL moved, partial close, etc.).
    Implements Section 9.1 journaling granularity.
    """
    await _p().execute(
        """
        INSERT INTO trade_events (
            trade_id, event_type, description, price, lots, pnl_usd, created_at
        ) VALUES ($1,$2,$3,$4,$5,$6,NOW())
        """,
        trade_id, event_type, description, price, lots, pnl_usd,
    )


async def update_trade_close(
    trade_id:    str,
    close_price: float,
    close_reason: str,
    pnl_usd:     float,
    status:      str,
    closed_at:   datetime,
) -> None:
    """Finalise trade record on position close."""
    await _p().execute(
        """
        UPDATE trades
        SET close_price=$2, close_reason=$3, pnl_usd=$4,
            status=$5, closed_at=$6
        WHERE trade_id=$1
        """,
        trade_id, close_price, close_reason, pnl_usd, status, closed_at,
    )


async def get_daily_stats(date_str: str) -> Dict[str, Any]:
    """
    Return aggregated stats for a given date (YYYY-MM-DD).
    Used by risk_manager and dashboard.
    """
    row = await _p().fetchrow(
        """
        SELECT
            COUNT(*)                                        AS total_trades,
            COUNT(*) FILTER (WHERE pnl_usd > 0)            AS winning_trades,
            COUNT(*) FILTER (WHERE pnl_usd <= 0)           AS losing_trades,
            COALESCE(SUM(pnl_usd), 0)                      AS total_pnl_usd,
            COALESCE(SUM(pnl_usd) FILTER (WHERE pnl_usd < 0), 0) AS total_loss_usd,
            COALESCE(AVG(rr_ratio) FILTER (WHERE pnl_usd > 0), 0) AS avg_rr
        FROM trades
        WHERE DATE(created_at) = $1::date
          AND status NOT IN ('PENDING')
        """,
        date_str,
    )
    if row is None:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "total_pnl_usd": 0.0, "total_loss_usd": 0.0, "avg_rr": 0.0,
        }
    return dict(row)


async def get_recent_trades(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent N trades for journal display."""
    rows = await _p().fetch(
        """
        SELECT trade_id, direction, setup_grade, entry_price, sl_price,
               tp1_price, tp2_price, lot_size, sl_pips, rr_ratio,
               confluence_score, status, close_price, close_reason,
               pnl_usd, created_at, opened_at, closed_at
        FROM trades
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]