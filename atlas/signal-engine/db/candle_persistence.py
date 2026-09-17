"""
signal-engine/db/candle_persistence.py
Persist the in-memory CandleBuffer to Redis so restarts don't wipe the Asia session.

Strategy:
  - On every M5 ingest, save the full M5 buffer to Redis (JSON, compressed).
    M5 is the only timeframe the Asia detection depends on — other TFs are nice-to-have.
  - On app startup, restore M5 (and any other TF that Redis has) back into the buffer
    before the first pipeline run.

Key schema:
  atlas:candles:{tf}   → JSON array of candle dicts, TTL 26 hours (covers Asia + London + buffer)
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import List

import redis.asyncio as aioredis
import structlog

from models.candle import Candle, CandleBuffer

log = structlog.get_logger(__name__)

_TIMEFRAMES_TO_PERSIST = ["5min", "15min", "4h", "1h", "1day"]
_TTL_SECONDS = 26 * 3600   # 26 hours — covers previous night's Asia session through end of London


def _candle_to_dict(c: Candle) -> dict:
    return {
        "symbol":    c.symbol,
        "timeframe": c.timeframe,
        "time":      c.time.isoformat(),
        "open":      c.open,
        "high":      c.high,
        "low":       c.low,
        "close":     c.close,
        "volume":    c.volume,
    }


def _dict_to_candle(d: dict) -> Candle:
    t = datetime.fromisoformat(d["time"])
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return Candle(
        symbol=d["symbol"],
        timeframe=d["timeframe"],
        time=t,
        open=float(d["open"]),
        high=float(d["high"]),
        low=float(d["low"]),
        close=float(d["close"]),
        volume=int(d.get("volume", 0)),
    )


async def save_candles(r: aioredis.Redis, buf: CandleBuffer, tf: str) -> None:
    """
    Persist all candles for `tf` to Redis.
    Called after every M5 ingest (and optionally after H4/D1 ingest).
    """
    candles = buf.get(tf, 500)  # grab everything in buffer
    if not candles:
        return
    key = f"atlas:candles:{tf}"
    payload = json.dumps([_candle_to_dict(c) for c in candles])
    await r.set(key, payload, ex=_TTL_SECONDS)


async def restore_candles(r: aioredis.Redis, buf: CandleBuffer) -> None:
    """
    On startup, load all persisted TFs back into the buffer.
    Called from main.py startup handler BEFORE the first pipeline run.
    """
    total_restored = 0
    for tf in _TIMEFRAMES_TO_PERSIST:
        key = f"atlas:candles:{tf}"
        raw = await r.get(key)
        if not raw:
            continue
        try:
            candles: List[Candle] = [_dict_to_candle(d) for d in json.loads(raw)]
            buf.append_bulk(candles)
            total_restored += len(candles)
            log.info("candles_restored", timeframe=tf, count=len(candles))
        except Exception as exc:
            log.warning("candle_restore_error", timeframe=tf, error=str(exc))

    if total_restored == 0:
        log.info("candle_restore_empty",
                 msg="No persisted candles found — waiting for MT5 to push fresh data")
    else:
        log.info("candle_restore_complete", total=total_restored)