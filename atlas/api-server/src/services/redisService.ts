/**
 * api-server/src/services/redisService.ts
 * ATLAS Redis service — all state read/write operations.
 * Keys mirror signal-engine/db/redis_client.py exactly.
 */
import Redis from "ioredis";
import { REDIS_URL, MAX_DAILY_LOSS_PCT, CANDLE_BUFFER_SIZE } from "../config";
import type { AtlasMode, RiskState, TradeState, CandleBar } from "../types";

let _client: Redis | null = null;

export function getClient(): Redis {
  if (!_client) throw new Error("Redis not initialised — call initRedis() first");
  return _client;
}

export function initRedis(): void {
  _client = new Redis(REDIS_URL, {
    maxRetriesPerRequest: 3,
    lazyConnect: false,
    enableReadyCheck: true,
  });

  _client.on("connect",  () => console.log("[redis] connected"));
  _client.on("error",    (err: Error) => console.error("[redis] error:", err.message));
  _client.on("reconnecting", () => console.warn("[redis] reconnecting..."));
}

export async function closeRedis(): Promise<void> {
  if (_client) {
    await _client.quit();
    _client = null;
  }
}

// ─── Trading Mode ─────────────────────────────────────────────────────────────

export async function getMode(): Promise<AtlasMode> {
  const val = await getClient().get("atlas:mode");
  return (val === "AUTO" || val === "MANUAL") ? val : "MANUAL";
}

export async function setMode(mode: AtlasMode): Promise<void> {
  await getClient().set("atlas:mode", mode);
}

// ─── Risk State ───────────────────────────────────────────────────────────────

const DEFAULT_RISK: RiskState = {
  daily_loss_pct:    0,
  daily_loss_usd:    0,
  trades_today:      0,
  session_terminated: false,
};

export async function getRiskState(): Promise<RiskState> {
  const raw = await getClient().get("atlas:risk");
  if (!raw) return { ...DEFAULT_RISK };
  try {
    return JSON.parse(raw) as RiskState;
  } catch {
    return { ...DEFAULT_RISK };
  }
}

export async function updateDailyLoss(
  lossUsd:        number,
  accountBalance: number
): Promise<RiskState> {
  const state = await getRiskState();
  state.daily_loss_usd += lossUsd;
  state.daily_loss_pct  = (state.daily_loss_usd / accountBalance) * 100;
  state.trades_today   += 1;

  if (state.daily_loss_pct >= MAX_DAILY_LOSS_PCT) {
    state.session_terminated = true;
  }

  await getClient().set("atlas:risk", JSON.stringify(state));
  return state;
}

export async function setSessionTerminated(terminated: boolean): Promise<void> {
  const state = await getRiskState();
  state.session_terminated = terminated;
  await getClient().set("atlas:risk", JSON.stringify(state));
}

export async function resetRiskState(): Promise<void> {
  await getClient().set("atlas:risk", JSON.stringify({ ...DEFAULT_RISK }));
}

// ─── Pending Signal (AUTO mode) ───────────────────────────────────────────────

export async function getPendingSignal(): Promise<string | null> {
  return getClient().get("atlas:signal");
}

export async function setPendingSignal(
  signal: string,
  ttlSeconds: number = 300
): Promise<void> {
  await getClient().set("atlas:signal", signal, "EX", ttlSeconds);
}

export async function clearPendingSignal(): Promise<void> {
  await getClient().del("atlas:signal");
}

// ─── Pending Signal (MANUAL mode) ────────────────────────────────────────────

export async function getPendingSignalManual(): Promise<string | null> {
  return getClient().get("atlas:signal:manual");
}

export async function setPendingSignalManual(
  signal: string,
  ttlSeconds: number = 300
): Promise<void> {
  await getClient().set("atlas:signal:manual", signal, "EX", ttlSeconds);
}

export async function clearPendingSignalManual(): Promise<void> {
  await getClient().del("atlas:signal:manual");
}

/**
 * Moves signal from manual queue → live queue.
 * Called when trader clicks CONFIRM on dashboard.
 * Returns the signal string, or null if no manual signal exists.
 */
export async function confirmManualSignal(): Promise<string | null> {
  const sig = await getPendingSignalManual();
  if (!sig) return null;
  await clearPendingSignalManual();
  await setPendingSignal(sig);
  return sig;
}

// ─── Management Commands ──────────────────────────────────────────────────────

export async function getManageCmd(ticket: number): Promise<string | null> {
  return getClient().get(`atlas:manage:${ticket}`);
}

export async function setManageCmd(
  ticket:     number,
  cmd:        string,
  ttlSeconds: number = 60
): Promise<void> {
  await getClient().set(`atlas:manage:${ticket}`, cmd, "EX", ttlSeconds);
}

export async function clearManageCmd(ticket: number): Promise<void> {
  await getClient().del(`atlas:manage:${ticket}`);
}

// ─── Trade State ──────────────────────────────────────────────────────────────

export async function getTradeState(tradeId: string): Promise<TradeState | null> {
  const raw = await getClient().get(`atlas:trade:${tradeId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TradeState;
  } catch {
    return null;
  }
}

export async function setTradeState(
  tradeId: string,
  state:   TradeState
): Promise<void> {
  await getClient().set(`atlas:trade:${tradeId}`, JSON.stringify(state));
}

export async function getActiveTradeId(): Promise<string | null> {
  return getClient().get("atlas:active_trade_id");
}

// ─── Candle Buffer ────────────────────────────────────────────────────────────

/**
 * Append candles to the Redis list for a given timeframe.
 * Trims to CANDLE_BUFFER_SIZE (200) — oldest entries removed first.
 * Used for WebSocket broadcasting and frontend chart display.
 */
export async function appendCandles(
  timeframe: string,
  bars:      CandleBar[]
): Promise<void> {
  const client = getClient();
  const key    = `atlas:candles:${timeframe}`;

  const pipeline = client.pipeline();
  for (const bar of bars) {
    pipeline.rpush(key, JSON.stringify(bar));
  }
  pipeline.ltrim(key, -CANDLE_BUFFER_SIZE, -1);
  await pipeline.exec();
}

export async function getCandles(
  timeframe: string,
  count:     number = 100
): Promise<CandleBar[]> {
  const raw = await getClient().lrange(`atlas:candles:${timeframe}`, -count, -1);
  return raw
    .map((r) => {
      try { return JSON.parse(r) as CandleBar; }
      catch { return null; }
    })
    .filter((b): b is CandleBar => b !== null);
}

// ─── HTF Context ──────────────────────────────────────────────────────────────

export async function getHTFContext(): Promise<Record<string, unknown> | null> {
  const raw = await getClient().get("atlas:htf_context");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

// ─── News Cache ───────────────────────────────────────────────────────────────

export async function getNewsCache(): Promise<unknown[]> {
  const raw = await getClient().get("atlas:news_cache");
  if (!raw) return [];
  try {
    return JSON.parse(raw) as unknown[];
  } catch {
    return [];
  }
}

// ─── Pub/Sub ──────────────────────────────────────────────────────────────────

export async function publish(channel: string, message: string): Promise<void> {
  await getClient().publish(channel, message);
}

/**
 * Create a dedicated subscriber client for a channel.
 * Returns the subscriber instance — caller must handle messages.
 */
export function createSubscriber(): Redis {
  return new Redis(REDIS_URL, { lazyConnect: false });
}