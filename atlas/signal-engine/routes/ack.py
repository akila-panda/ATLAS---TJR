"""
signal-engine/routes/ack.py
POST /mt5/ack — EA sends acknowledgements after trade open and management actions.
Updates PostgreSQL trade records and Redis trade state.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel
import structlog

from db.redis_client import (
    clear_pending_signal,
    clear_manage_cmd,
    get_trade_state,
    set_trade_state,
    set_active_trade_id,
    clear_active_trade_id,
    get_risk_state,
    set_risk_state,
)
from db.postgres import (
    update_trade_status,
    insert_trade_event,
    update_trade_close,
)
from models.signal import TradeState
from config import ACCOUNT_BALANCE

log = structlog.get_logger(__name__)
router = APIRouter()


class AckPayload(BaseModel):
    type:       str           # "OPEN_ACK" | "MANAGE_ACK"
    trade_id:   str
    ticket:     int
    status:     str           # "OK" | "ERROR" | "PARTIAL_CLOSE_OK" | etc.
    price:      float
    error_code: int = 0
    message:    str = ""


@router.post("/mt5/ack", status_code=200)
async def receive_ack(payload: AckPayload, request: Request):
    """
    Processes acknowledgements from ATLAS_EA.mq5.

    OPEN_ACK + OK:
        - Update trade status to OPEN in PostgreSQL
        - Save TradeState to Redis for trade_manager
        - Set active_trade_id in Redis
        - Clear pending signal from Redis

    OPEN_ACK + ERROR:
        - Update trade status to ERROR in PostgreSQL
        - Log event
        - Clear pending signal

    MANAGE_ACK:
        - Insert trade_event record in PostgreSQL
        - Clear management command from Redis
        - Handle CLOSE_ALL_OK: finalise trade record
    """
    now = datetime.now(timezone.utc)
    log.info("ack_received", type=payload.type, status=payload.status,
             trade_id=payload.trade_id, ticket=payload.ticket)

    if payload.type == "OPEN_ACK":
        await _handle_open_ack(payload, now)

    elif payload.type == "MANAGE_ACK":
        await _handle_manage_ack(payload, now)

    return {"status": "acknowledged"}


async def _handle_open_ack(payload: AckPayload, now: datetime) -> None:
    """Handle trade open acknowledgement from EA."""
    if payload.status == "OK":
        # Update PostgreSQL: PENDING → OPEN
        await update_trade_status(
            trade_id=payload.trade_id,
            status="OPEN",
            mt5_ticket=payload.ticket,
            opened_at=now,
        )

        # Build and save TradeState to Redis
        # Fetch entry params from the signal log or pass them through the signal
        # We reconstruct from the pending signal string stored before clearing
        state_dict = await get_trade_state(payload.trade_id)
        if state_dict:
            state_dict["ticket"]    = payload.ticket
            state_dict["opened_at"] = now.isoformat()
            await set_trade_state(payload.trade_id, state_dict)

        await set_active_trade_id(payload.trade_id)
        await clear_pending_signal()

        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="TRADE_OPENED",
            description=f"Trade opened at {payload.price:.5f} ticket={payload.ticket}",
            price=payload.price,
            lots=state_dict.get("original_lot") if state_dict else None,
        )
        log.info("trade_opened",
                 trade_id=payload.trade_id, ticket=payload.ticket,
                 price=payload.price)

    else:
        # Trade failed to execute
        await update_trade_status(trade_id=payload.trade_id, status="ERROR")
        await clear_pending_signal()
        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="OPEN_FAILED",
            description=f"Trade open failed: {payload.message} (code {payload.error_code})",
        )
        log.warning("trade_open_failed",
                    trade_id=payload.trade_id,
                    error_code=payload.error_code,
                    message=payload.message)


async def _handle_manage_ack(payload: AckPayload, now: datetime) -> None:
    """Handle management command acknowledgement from EA."""
    # Clear the command from Redis so EA stops receiving it
    await clear_manage_cmd(payload.ticket)

    status = payload.status

    if status in ("PARTIAL_CLOSE_OK",):
        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="PARTIAL_CLOSE",
            description=f"Partial close executed at {payload.price:.5f}",
            price=payload.price,
        )
        log.info("partial_close_acked",
                 trade_id=payload.trade_id, price=payload.price)

    elif status == "MODIFY_SL_OK":
        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="SL_MODIFIED",
            description=f"SL modified to {payload.price:.5f}",
            price=payload.price,
        )

    elif status == "CLOSE_ALL_OK":
        # Finalise trade record
        state_dict = await get_trade_state(payload.trade_id)
        entry_price = state_dict.get("entry_price", 0.0) if state_dict else 0.0

        # Determine P&L direction from trade direction
        direction = state_dict.get("direction", "BUY") if state_dict else "BUY"
        remaining_lot = state_dict.get("current_lot", 0.0) if state_dict else 0.0
        if direction == "BUY":
            pnl_pips = (payload.price - entry_price) / 0.0001
        else:
            pnl_pips = (entry_price - payload.price) / 0.0001
        pnl_usd = pnl_pips * 10.0 * remaining_lot

        close_reason = payload.message or "CLOSE_ALL"
        outcome_status = "CLOSED"
        if "TP1" in close_reason:
            outcome_status = "TP1"
        elif "TP2" in close_reason:
            outcome_status = "TP2"
        elif "TP3" in close_reason:
            outcome_status = "TP3"
        elif "SL" in close_reason or "STOP" in close_reason:
            outcome_status = "SL"
        elif "BE" in close_reason:
            outcome_status = "BE"

        await update_trade_close(
            trade_id=payload.trade_id,
            close_price=payload.price,
            close_reason=close_reason,
            pnl_usd=pnl_usd,
            status=outcome_status,
            closed_at=now,
        )

        # Update daily risk state if loss
        if pnl_usd < 0:
            risk = await get_risk_state()
            risk["daily_loss_usd"] = risk.get("daily_loss_usd", 0.0) + abs(pnl_usd)
            risk["daily_loss_pct"] = risk["daily_loss_usd"] / ACCOUNT_BALANCE * 100.0
            risk["trades_today"]   = risk.get("trades_today", 0) + 1
            if risk["daily_loss_pct"] >= 2.0:
                risk["session_terminated"] = True
                log.warning("session_terminated",
                            daily_loss_pct=risk["daily_loss_pct"])
            await set_risk_state(risk)

        await clear_active_trade_id()

        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="TRADE_CLOSED",
            description=f"Trade closed at {payload.price:.5f} | "
                        f"reason={close_reason} pnl={pnl_usd:.2f}",
            price=payload.price,
            pnl_usd=pnl_usd,
        )
        log.info("trade_closed",
                 trade_id=payload.trade_id,
                 close_price=payload.price,
                 pnl_usd=pnl_usd,
                 reason=close_reason)

    elif "ERROR" in status:
        await insert_trade_event(
            trade_id=payload.trade_id,
            event_type="MANAGE_ERROR",
            description=f"Manage command failed: {payload.message} "
                        f"status={status} code={payload.error_code}",
        )
        log.error("manage_error",
                  trade_id=payload.trade_id,
                  status=status,
                  error_code=payload.error_code)