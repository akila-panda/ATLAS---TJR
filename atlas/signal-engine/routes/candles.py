"""
signal-engine/routes/candles.py
Candle ingestion endpoint — receives M5/M15/H4/D1 pushes from MT5 EA.
Triggers the full TJR strategy pipeline on every new M5 bar close.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel
import structlog

from models.candle import Candle, CandleBuffer
from config import BROKER_UTC_OFFSET_HOURS
from db.candle_persistence import save_candles

log = structlog.get_logger(__name__)
router = APIRouter()

# Pre-compute the broker → UTC correction offset once at import time.
# MT5 sends candle open times in broker server time (UTC+2 or UTC+3).
# Subtracting this offset converts broker time → UTC for all strategy code.
_BROKER_OFFSET = timedelta(hours=BROKER_UTC_OFFSET_HOURS)


class CandleIn(BaseModel):
    datetime: str    # ISO-8601 "YYYY-MM-DDTHH:MM:SS" (broker time, no tz suffix)
    open:     float
    high:     float
    low:      float
    close:    float
    volume:   Optional[int] = 0


class CandleBatch(BaseModel):
    symbol:    str          # "EURUSD" | "GBPUSD"
    timeframe: str          # "5min" | "15min" | "4h" | "1h" | "1day"
    candles:   List[CandleIn]


@router.post("/mt5/candles", status_code=200)
async def receive_mt5_candles(batch: CandleBatch, request: Request):
    """
    Receives OHLCV candle batch from ATLAS_EA.mq5.
    Called on every new M5 bar for EURUSD M5/M15,
    every new H4 bar for EURUSD H4 and GBPUSD H1,
    every new D1 bar for EURUSD D1.

    Triggers run_strategy_pipeline() as a background task on M5 receipt.
    """
    buf: CandleBuffer = request.app.state.buffer
    ingested = _ingest_batch(batch, buf)

    log.info("candles_received",
             symbol=batch.symbol,
             timeframe=batch.timeframe,
             count=len(batch.candles),
             ingested=ingested)

    # Trigger strategy pipeline on every new EURUSD M5 close
    if batch.symbol == "EURUSD" and batch.timeframe == "5min" and ingested > 0:
        # Persist buffer to Redis before pipeline runs — survives restarts
        asyncio.create_task(_persist_candles(request.app, "5min"))
        asyncio.create_task(_safe_pipeline(request.app))

    # Update HTF context on new D1 or H4 bar
    if batch.symbol == "EURUSD" and batch.timeframe in ("1day", "4h"):
        asyncio.create_task(_persist_candles(request.app, batch.timeframe))
        asyncio.create_task(_update_htf_context(request.app))

    return {"status": "ok", "ingested": ingested}


@router.post("/internal/candles", status_code=200)
async def receive_internal_candles(batch: CandleBatch, request: Request):
    """
    Internal endpoint for injecting candles during testing/backtesting.
    Same logic as /mt5/candles but no pipeline trigger.
    """
    buf: CandleBuffer = request.app.state.buffer
    ingested = _ingest_batch(batch, buf)
    return {"status": "ok", "ingested": ingested}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ingest_batch(batch: CandleBatch, buf: CandleBuffer) -> int:
    """
    Parse and append candles to buffer. Returns count of new candles added.

    Timezone correction:
    MT5 sends datetimes in broker server time (no tz suffix, e.g. UTC+3).
    datetime.fromisoformat() produces a naive datetime.
    We treat it as broker time and subtract _BROKER_OFFSET to get UTC,
    then attach timezone.utc so all downstream strategy code is tz-aware.
    """
    count = 0
    for c in batch.candles:
        try:
            dt_naive = datetime.fromisoformat(c.datetime)

            if dt_naive.tzinfo is None:
                # Broker time → UTC: attach UTC marker then subtract offset
                dt = (dt_naive.replace(tzinfo=timezone.utc) - _BROKER_OFFSET)
            else:
                # Already tz-aware (EA was fixed to send UTC+Z) — normalise to UTC
                dt = dt_naive.astimezone(timezone.utc)

        except ValueError:
            log.warning("candle_parse_error", raw=c.datetime)
            continue

        candle = Candle(
            symbol=batch.symbol,
            timeframe=batch.timeframe,
            time=dt,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume or 0,
        )
        buf.append(candle)
        count += 1
    return count


async def _persist_candles(app, tf: str) -> None:
    """Persist candle buffer for `tf` to Redis — survives container restarts."""
    try:
        from db.redis_client import _r
        buf: CandleBuffer = app.state.buffer
        await save_candles(_r(), buf, tf)
    except Exception as exc:
        log.warning("candle_persist_error", timeframe=tf, error=str(exc))


async def _safe_pipeline(app) -> None:
    """Run strategy pipeline with error isolation — errors must not crash the server."""
    try:
        from main import run_strategy_pipeline
        await run_strategy_pipeline(app)
    except Exception as exc:
        log.error("pipeline_error", error=str(exc), exc_info=True)


async def _update_htf_context(app) -> None:
    """Recompute and cache HTF context on new D1 or H4 bar."""
    try:
        buf: CandleBuffer = app.state.buffer
        from strategy.htf_context import compute_htf_context
        from db.redis_client import set_htf_context

        candles_d1 = buf.get("1day", 30)
        candles_h4 = buf.get("4h",   50)

        if len(candles_d1) >= 5:
            ctx = compute_htf_context(candles_d1, candles_h4)
            await set_htf_context(ctx.to_dict())
            log.info("htf_context_updated", dol=ctx.dol_direction,
                     bias_score=ctx.htf_bias_score)
    except Exception as exc:
        log.error("htf_context_error", error=str(exc), exc_info=True)