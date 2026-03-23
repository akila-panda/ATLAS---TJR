"""
signal-engine/db/redis_client.py
Async Redis client — all ATLAS state operations.
Keys are namespaced under "atlas:".
"""
from __future__ import annotations
import json
from typing import Optional, Dict, Any
import redis.asyncio as aioredis
from config import REDIS_URL

_redis: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    """Called once on FastAPI startup."""
    global _redis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await _redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def _r() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis


# ─── ATLAS Trading Mode ───────────────────────────────────────────────────────

async def get_mode() -> str:
    """Returns "AUTO" or "MANUAL". Defaults to "MANUAL" if not set."""
    val = await _r().get("atlas:mode")
    return val if val else "MANUAL"


async def set_mode(mode: str) -> None:
    """Set trading mode: "AUTO" | "MANUAL"."""
    await _r().set("atlas:mode", mode)


# ─── Pending Signal (AUTO mode — EA polls immediately) ───────────────────────

async def set_pending_signal(signal_str: str) -> None:
    """
    Write pipe-delimited signal for EA to consume (AUTO mode).
    Signal persists until ACK'd — EA polls GET /signal every second.
    """
    await _r().set("atlas:signal", signal_str)


async def get_pending_signal() -> Optional[str]:
    """Return pending signal string or None."""
    return await _r().get("atlas:signal")


async def clear_pending_signal() -> None:
    """Clear after EA ACK or manual skip."""
    await _r().delete("atlas:signal")


# ─── Pending Signal (MANUAL mode — waits for dashboard confirmation) ─────────

async def set_pending_signal_manual(signal_str: str) -> None:
    """
    Write signal to manual queue — waits for dashboard CONFIRM before
    forwarding to atlas:signal for EA consumption.
    """
    await _r().set("atlas:signal:manual", signal_str)


async def get_pending_signal_manual() -> Optional[str]:
    return await _r().get("atlas:signal:manual")


async def confirm_manual_signal() -> Optional[str]:
    """
    Called when trader clicks CONFIRM on dashboard.
    Moves signal from manual queue → live signal queue.
    Returns the signal string, or None if no manual signal pending.
    """
    sig = await _r().get("atlas:signal:manual")
    if sig:
        await _r().delete("atlas:signal:manual")
        await _r().set("atlas:signal", sig)
    return sig


async def skip_manual_signal() -> None:
    """Called when trader clicks SKIP on dashboard."""
    await _r().delete("atlas:signal:manual")


# ─── Trade Management Commands (per MT5 ticket) ───────────────────────────────

async def set_manage_cmd(ticket: int, cmd_str: str) -> None:
    """
    Write a management command for a specific MT5 ticket.
    cmd_str format: "PARTIAL_CLOSE|40|trade-id"
                    "MODIFY_SL|1.08210|trade-id"
                    "CLOSE_ALL|REASON|trade-id"
    EA polls GET /manage?ticket=N every second.
    """
    key = f"atlas:manage:{ticket}"
    await _r().set(key, cmd_str, ex=30)   # 30s expiry — prevents stale commands


async def get_manage_cmd(ticket: int) -> Optional[str]:
    """Return pending management command for ticket, or None."""
    return await _r().get(f"atlas:manage:{ticket}")


async def clear_manage_cmd(ticket: int) -> None:
    """Clear after EA ACK."""
    await _r().delete(f"atlas:manage:{ticket}")


# ─── Risk State ───────────────────────────────────────────────────────────────

async def get_risk_state() -> Dict[str, Any]:
    """
    Returns current session risk state.
    Fields: daily_loss_pct, daily_loss_usd, trades_today, session_terminated.
    """
    raw = await _r().get("atlas:risk_state")
    if raw:
        return json.loads(raw)
    return {
        "daily_loss_pct":      0.0,
        "daily_loss_usd":      0.0,
        "trades_today":        0,
        "session_terminated":  False,
    }


async def set_risk_state(state: Dict[str, Any]) -> None:
    await _r().set("atlas:risk_state", json.dumps(state))


async def reset_risk_state() -> None:
    """Call at start of each trading day (scheduler)."""
    await set_risk_state({
        "daily_loss_pct":     0.0,
        "daily_loss_usd":     0.0,
        "trades_today":       0,
        "session_terminated": False,
    })


async def record_loss(loss_usd: float, account_balance: float) -> bool:
    """
    Record a loss after trade close. Returns True if daily limit now breached.
    Implements Rule 7.3: 2% daily max → session terminated.
    """
    state = await get_risk_state()
    state["daily_loss_usd"] += loss_usd
    state["daily_loss_pct"] = (state["daily_loss_usd"] / account_balance) * 100.0
    state["trades_today"] = state.get("trades_today", 0) + 1
    if state["daily_loss_pct"] >= 2.0:
        state["session_terminated"] = True
    await set_risk_state(state)
    return state["session_terminated"]


# ─── Active Trade State ───────────────────────────────────────────────────────

async def set_trade_state(trade_id: str, state: Dict[str, Any]) -> None:
    """Store serialised TradeState for a live trade."""
    await _r().set(f"atlas:trade:{trade_id}", json.dumps(state, default=str))


async def get_trade_state(trade_id: str) -> Optional[Dict[str, Any]]:
    raw = await _r().get(f"atlas:trade:{trade_id}")
    return json.loads(raw) if raw else None


async def clear_trade_state(trade_id: str) -> None:
    await _r().delete(f"atlas:trade:{trade_id}")


async def set_active_trade_id(trade_id: str) -> None:
    """Track the currently active trade ID."""
    await _r().set("atlas:active_trade_id", trade_id)


async def get_active_trade_id() -> Optional[str]:
    return await _r().get("atlas:active_trade_id")


async def clear_active_trade_id() -> None:
    await _r().delete("atlas:active_trade_id")


# ─── Session State ────────────────────────────────────────────────────────────

async def set_session(data: Dict[str, Any]) -> None:
    """Store current session data (Asia range, sweep, last pipeline result)."""
    await _r().set("atlas:session", json.dumps(data, default=str))


async def get_session() -> Dict[str, Any]:
    raw = await _r().get("atlas:session")
    return json.loads(raw) if raw else {}


async def reset_session() -> None:
    """Call at 20:00 EST each day when new Asia session starts."""
    await _r().delete("atlas:session")


# ─── HTF Context (set by scheduler, read by pipeline) ─────────────────────────

async def set_htf_context(data: Dict[str, Any]) -> None:
    """
    Stores Daily + 4H context computed by htf_context.py.
    Updated on each new D1 or H4 bar push from MT5.
    """
    await _r().set("atlas:htf_context", json.dumps(data, default=str))


async def get_htf_context() -> Dict[str, Any]:
    raw = await _r().get("atlas:htf_context")
    return json.loads(raw) if raw else {}


# ─── News Cache ───────────────────────────────────────────────────────────────

async def set_news_cache(events: list) -> None:
    """Cache economic calendar events for the session."""
    await _r().set("atlas:news_cache", json.dumps(events, default=str), ex=3600)


async def get_news_cache() -> list:
    raw = await _r().get("atlas:news_cache")
    return json.loads(raw) if raw else []


# ─── WebSocket broadcast helpers (read by broadcaster) ───────────────────────

async def publish_event(channel: str, data: Dict[str, Any]) -> None:
    """Publish event to Redis pub/sub channel for WebSocket broadcast."""
    await _r().publish(channel, json.dumps(data, default=str))