"""
signal-engine/routes/manage.py
GET /manage?ticket=N — polled by ATLAS_EA.mq5 every second when position is open.
Returns pending management command for the given ticket or "null".
"""
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
import structlog

from db.redis_client import get_manage_cmd

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/manage", response_class=PlainTextResponse)
async def get_manage_command(
    ticket: int = Query(..., description="MT5 position ticket number"),
) -> str:
    """
    EA polls this endpoint every second when a position is open.

    Returns pipe-delimited management command:
        "PARTIAL_CLOSE|40|trade-uuid-abc123"
        "MODIFY_SL|1.08210|trade-uuid-abc123"
        "CLOSE_ALL|NY_OPEN_TIME_KILL|trade-uuid-abc123"

    Returns "null" if no command is pending for this ticket.

    Commands are written to Redis by trade_manager.py (called on each M5 close)
    and cleared after EA ACK via /mt5/ack.
    """
    cmd = await get_manage_cmd(ticket)
    if cmd:
        log.info("manage_cmd_polled", ticket=ticket, cmd=cmd[:50])
        return cmd
    return "null"