"""
signal-engine/main.py
ATLAS Signal Engine — FastAPI application entry point.
Mounts all routers, initialises Redis/Postgres, runs strategy pipeline.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from models.candle import CandleBuffer
from models.signal import TradeState
from db.redis_client import (
    init_redis, close_redis,
    get_mode, get_htf_context, get_news_cache, get_risk_state,
    set_pending_signal, set_pending_signal_manual,
    set_trade_state, get_active_trade_id, get_trade_state,
)
from db.candle_persistence import restore_candles
from db.postgres import init_postgres, close_postgres, insert_signal_log, insert_trade
from routes.candles import router as candles_router
from routes.signal  import router as signal_router
from routes.manage  import router as manage_router
from routes.ack     import router as ack_router
from strategy.asia_range      import detect_asia_range
from strategy.judas_sweep     import detect_sweep
from strategy.structure       import detect_post_sweep_structure
from strategy.fvg             import detect_fvg
from strategy.order_block     import detect_ob
from strategy.confluence_score import score_confluence
from strategy.decision_tree   import run_decision_tree
from strategy.entry_model     import calculate_entry
from strategy.risk_manager    import validate_final
from strategy.news_filter     import is_news_blocked
from strategy.trade_manager   import process_trade_management, _state_to_dict
from scheduler             import start_scheduler, stop_scheduler
from config import ACCOUNT_BALANCE, ATLAS_MODE

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    log.info("atlas_engine_starting")
    app.state.buffer = CandleBuffer()
    await init_redis()
    await init_postgres()
    # Restore candle buffer from Redis — Asia range detection survives restarts
    from db.redis_client import _r
    await restore_candles(_r(), app.state.buffer)
    # Daily risk/session resets at 20:00 EST (Rule 7.3). Without this the
    # session_terminated flag never clears and the engine stays dead after the
    # first 2% loss day.
    start_scheduler()
    log.info("atlas_engine_ready", mode=ATLAS_MODE, account_balance=ACCOUNT_BALANCE)
    yield
    log.info("atlas_engine_shutting_down")
    stop_scheduler()
    await close_redis()
    await close_postgres()


app = FastAPI(
    title="ATLAS Signal Engine",
    version="1.0.0",
    description="TJR EUR/USD London Session — Strategy Pipeline",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(candles_router)
app.include_router(signal_router)
app.include_router(manage_router)
app.include_router(ack_router)


@app.get("/health")
async def health():
    """Health check for Docker Compose and monitoring."""
    buf: CandleBuffer = app.state.buffer
    return {
        "status":    "ok",
        "mode":      ATLAS_MODE,
        "candles":   {tf: buf.count(tf) for tf in buf.all_timeframes()},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Strategy Pipeline ────────────────────────────────────────────────────────

async def run_strategy_pipeline(app_ref: Any) -> None:
    """
    Full TJR strategy pipeline — runs on every new M5 candle close.

    Pipeline order (must not change — Section 11 Decision Tree):
    1. Load candles from buffer
    2. asia_range detection
    3. judas_sweep detection
    4. post_sweep structure (CHoCH, displacement)
    5. FVG / OB entry zone
    6. Load HTF context + news cache from Redis
    7. confluence_score
    8. decision_tree (14 nodes)
    9. entry_model (only if ENTER)
    10. risk_manager final validation
    11. Write signal to Redis + trade to PostgreSQL
    12. If open trade: run trade_manager

    Also handles open trade management if active_trade_id is set.
    """
    buf: CandleBuffer = app_ref.state.buffer
    now_utc = datetime.now(timezone.utc)

    # ── Minimum data check ────────────────────────────────────────────────────
    if buf.count("5min") < 20:
        log.debug("pipeline_skip", reason="insufficient_m5_candles",
                  count=buf.count("5min"))
        return

    candles_m5  = buf.get("5min",  100)
    candles_m15 = buf.get("15min", 80)
    candles_h4  = buf.get("4h",    50)
    candles_d1  = buf.get("1day",  30)

    # ── Open trade management (runs regardless of new signal) ─────────────────
    active_trade_id = await get_active_trade_id()
    if active_trade_id:
        state_dict = await get_trade_state(active_trade_id)
        if state_dict:
            try:
                ts = TradeState(**state_dict)
                await process_trade_management(
                    state=ts,
                    candles_m5=candles_m5,
                    now_utc=now_utc,
                    set_manage_cmd_fn=_write_manage_cmd,
                    update_state_fn=_write_trade_state,
                    insert_event_fn=_write_trade_event,
                )
            except Exception as exc:
                log.error("trade_manager_error", error=str(exc), exc_info=True)
        return  # Do not generate new signals while a trade is active

    # ── Step 1: Asia range (Rules 1.1–1.4) ───────────────────────────────────
    asia = detect_asia_range(candles_m5, now_utc)

    # ── Step 2: HTF context and news (load from Redis) ────────────────────────
    htf_context = await get_htf_context()
    news_events = await get_news_cache()
    news_bl     = is_news_blocked(news_events, now_utc)

    # ── Step 3: Judas sweep (Rules 2.1–2.6) ──────────────────────────────────
    sweep = detect_sweep(candles_m5, asia, htf_context, now_utc)

    # ── Step 4: Post-sweep structure (Rules 3.4, 4.1) ────────────────────────
    structure = detect_post_sweep_structure(candles_m5, candles_m15, sweep) \
                if sweep.is_valid else _null_structure()

    # ── Step 5: FVG and OB entry zones (Rules 4.2, 4.3) ─────────────────────
    fvg = detect_fvg(candles_m5, sweep, structure, now_utc) \
          if structure.choch_15m else _null_fvg()
    ob  = detect_ob(candles_m5, sweep, structure) \
          if structure.choch_15m else _null_ob()

    # ── Step 6: Entry parameters ──────────────────────────────────────────────
    entry = calculate_entry(sweep, asia, fvg, ob, htf_context, ACCOUNT_BALANCE) \
            if (fvg.found or ob.found) else None

    # Compute defaults for decision tree even if entry is None
    sl_pips   = entry.sl_pips   if entry else 999.0
    rr_ratio  = entry.rr_ratio  if entry else 0.0
    lot_size  = entry.lot_size  if entry else 0.0

    # ── Step 7: Confluence score (Section 10) ─────────────────────────────────
    confluence = score_confluence(
        asia, sweep, structure, fvg, htf_context, news_events, sweep.sweep_time
    )

    # ── Step 8: Risk state ────────────────────────────────────────────────────
    risk_state = await get_risk_state()

    # ── Step 9: Decision tree (Section 11 — 14 nodes) ────────────────────────
    dt = run_decision_tree(
        news_blocked=news_bl,
        asia=asia,
        sweep=sweep,
        structure=structure,
        fvg=fvg,
        ob_found=ob.found,
        entry_sl_pips=sl_pips,
        entry_rr_ratio=rr_ratio,
        required_rr=asia.required_rr if asia.is_valid else 2.0,
        confluence=confluence,
        risk_state=risk_state,
        entry_lot_size=lot_size,
        now_utc=now_utc,
    )

    # ── Build decision_state for full PostgreSQL logging ──────────────────────
    decision_state = {
        "outcome":    dt.outcome,
        "reason":     dt.reason,
        "nodes":      [{"id": n.node_id, "name": n.name,
                        "passed": n.passed, "reason": n.reason,
                        "detail": n.detail}
                       for n in dt.nodes],
        "asia": {
            "valid":        asia.is_valid,
            "high":         asia.asia_high,
            "low":          asia.asia_low,
            "range_pips":   asia.range_pips,
            "wide_range":   asia.is_wide_range,
            "required_rr":  asia.required_rr,
        },
        "sweep": {
            "detected":   sweep.detected,
            "valid":      sweep.is_valid,
            "direction":  sweep.direction,
            "ext_pips":   sweep.extension_pips,
            "is_late_lkz": sweep.is_late_lkz,
            "aligns_dol": sweep.aligns_with_dol,
        },
        "structure": {
            "choch_15m":    structure.choch_15m,
            "choch_5m":     structure.choch_5m,
            "displacement": structure.displacement,
            "bos_5m":       structure.bos_5m,
        },
        "fvg": {
            "found":     fvg.found,
            "violated":  fvg.is_violated,
            "expired":   fvg.is_expired,
            "midpoint":  fvg.fvg_midpoint,
            "size_pips": fvg.fvg_size_pips,
        },
        "confluence": {
            "total":   confluence.total,
            "grade":   confluence.grade,
            "factors": confluence.factors,
        },
        "htf_bias":   htf_context.get("dol_direction", "AMBIGUOUS"),
        "news_blocked": news_bl,
    }
    if entry:
        decision_state["entry"] = {
            "price":  entry.entry_price,
            "sl":     entry.sl_price,
            "tp1":    entry.tp1_price,
            "tp2":    entry.tp2_price,
            "tp3":    entry.tp3_price,
            "sl_pips": entry.sl_pips,
            "rr":     entry.rr_ratio,
            "lot":    entry.lot_size,
            "method": entry.entry_method,
        }

    signal_id = str(uuid.uuid4())

    # ── Always log to PostgreSQL (including all NO_TRADE outcomes) ────────────
    try:
        await insert_signal_log(
            signal_id=signal_id,
            outcome=dt.outcome,
            reason=dt.reason,
            direction=entry.direction if entry and dt.outcome == "ENTER" else None,
            confluence_score=confluence.total,
            setup_grade=confluence.grade,
            asia_high=asia.asia_high,
            asia_low=asia.asia_low,
            asia_range_pips=asia.range_pips,
            sweep_direction=sweep.direction,
            sweep_extension_pips=sweep.extension_pips,
            decision_state=decision_state,
            generated_at=now_utc,
        )
    except Exception as exc:
        log.error("signal_log_error", error=str(exc))

    # ── Exit here if not ENTER ────────────────────────────────────────────────
    if dt.outcome != "ENTER" or entry is None:
        log.info("pipeline_no_trade",
                 reason=dt.reason,
                 node_count=dt.node_count,
                 confluence=confluence.total)
        return

    # ── Step 10: Final risk validation ────────────────────────────────────────
    risk_ok = validate_final(
        entry=entry,
        required_rr=asia.required_rr,
        confluence=confluence.total,
        risk_state=risk_state,
    )
    if not risk_ok.passed:
        log.warning("risk_validation_failed", reason=risk_ok.reason,
                    detail=risk_ok.detail)
        return

    # ── Step 11: Build and publish signal ────────────────────────────────────
    trade_id   = str(uuid.uuid4())
    signal_str = (
        f"{entry.direction}|{entry.lot_size:.2f}|"
        f"{entry.sl_price:.5f}|{entry.tp1_price:.5f}|"
        f"{entry.tp2_price:.5f}|{entry.tp3_price:.5f}|"
        f"{trade_id}"
    )

    # Persist trade record to PostgreSQL
    try:
        await insert_trade(
            trade_id=trade_id,
            signal_id=signal_id,
            direction=entry.direction,
            entry_price=entry.entry_price,
            sl_price=entry.sl_price,
            tp1_price=entry.tp1_price,
            tp2_price=entry.tp2_price,
            tp3_price=entry.tp3_price,
            sl_pips=entry.sl_pips,
            rr_ratio=entry.rr_ratio,
            lot_size=entry.lot_size,
            risk_pct=entry.risk_pct,
            risk_usd=entry.risk_usd,
            account_balance=ACCOUNT_BALANCE,
            asia_high=asia.asia_high,
            asia_low=asia.asia_low,
            asia_range_pips=asia.range_pips,
            sweep_direction=sweep.direction or "",
            sweep_extension_pips=sweep.extension_pips,
            confluence_score=confluence.total,
            setup_grade=confluence.grade,
            decision_state=decision_state,
        )
    except Exception as exc:
        log.error("insert_trade_error", error=str(exc))

    # Persist initial TradeState to Redis (ticket updated later via ACK)
    ts_dict = {
        "trade_id":     trade_id,
        "ticket":       0,          # filled by OPEN_ACK
        "direction":    entry.direction,
        "entry_price":  entry.entry_price,
        "sl_price":     entry.sl_price,
        "tp1_price":    entry.tp1_price,
        "tp2_price":    entry.tp2_price,
        "tp3_price":    entry.tp3_price,
        "original_lot": entry.lot_size,
        "current_lot":  entry.lot_size,
        "asia_high":    asia.asia_high,
        "asia_low":     asia.asia_low,
        "tp1_hit":      False,
        "tp2_hit":      False,
        "be_moved":     False,
        "trailing_active": False,
        "last_swing":   None,
        "current_sl":   entry.sl_price,
        "opened_at":    None,
        "close_reason": None,
        "close_price":  None,
        "pnl_usd":      None,
    }
    await set_trade_state(trade_id, ts_dict)

    # Publish to correct Redis key based on mode
    mode = await get_mode()
    if mode == "AUTO":
        await set_pending_signal(signal_str)
        log.info("signal_published_auto",
                 trade_id=trade_id, signal=signal_str[:60],
                 grade=confluence.grade, rr=entry.rr_ratio)
    else:
        await set_pending_signal_manual(signal_str)
        log.info("signal_pending_manual_confirm",
                 trade_id=trade_id, signal=signal_str[:60],
                 grade=confluence.grade, rr=entry.rr_ratio)


# ─── Null object helpers (avoids conditional import chains) ───────────────────

def _null_structure():
    from strategy.structure import StructureResult
    return StructureResult()

def _null_fvg():
    from strategy.fvg import FVGResult
    return FVGResult(found=False)

def _null_ob():
    from strategy.order_block import OBResult
    return OBResult(found=False)


# ─── Trade manager Redis helpers (passed as callbacks) ───────────────────────

async def _write_manage_cmd(ticket: int, cmd: str) -> None:
    from db.redis_client import set_manage_cmd
    await set_manage_cmd(ticket, cmd)

async def _write_trade_state(trade_id: str, state_dict: dict) -> None:
    await set_trade_state(trade_id, state_dict)

async def _write_trade_event(
    trade_id: str, event_type: str, description: str,
    price=None, lots=None, pnl_usd=None,
) -> None:
    from db.postgres import insert_trade_event
    try:
        await insert_trade_event(trade_id, event_type, description,
                                 price, lots, pnl_usd)
    except Exception as exc:
        log.error("trade_event_error", error=str(exc))