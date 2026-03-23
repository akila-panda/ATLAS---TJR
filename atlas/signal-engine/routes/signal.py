"""
signal-engine/routes/signal.py
GET /signal — polled by ATLAS_EA.mq5 every second.
Returns pending signal string or "null".
"""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
import structlog

from db.redis_client import get_mode, get_pending_signal

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/signal", response_class=PlainTextResponse)
async def get_signal(request: Request) -> str:
    """
    EA polls this endpoint every second when no position is open.

    In AUTO mode:  returns the pending signal immediately.
    In MANUAL mode: returns "null" until trader confirms on dashboard.
                   The confirmed signal is moved to atlas:signal by
                   confirm_manual_signal() when CONFIRM is clicked.

    Returns pipe-delimited signal string:
        "BUY|0.09|1.08000|1.08200|1.08350|1.08500|trade-uuid"
    or "null" if no signal is pending.
    """
    mode = await get_mode()
    sig  = await get_pending_signal()

    if sig:
        log.info("signal_polled", mode=mode, signal=sig[:40])
        return sig

    return "null"