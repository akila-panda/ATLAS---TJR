/**
 * api-server/src/config.ts
 * ATLAS API Server — environment configuration.
 * All constants sourced from .env.example defaults.
 */
import * as dotenv from "dotenv";
dotenv.config();

function required(key: string): string {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required env var: ${key}`);
  return val;
}

function optional(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

// ─── Server ───────────────────────────────────────────────────────────────────
export const PORT             = parseInt(optional("PORT", "3001"), 10);
export const NODE_ENV         = optional("NODE_ENV", "development");
export const FRONTEND_ORIGIN  = optional("FRONTEND_ORIGIN", "http://localhost:5173");
export const LOG_LEVEL        = optional("LOG_LEVEL", "info");

// ─── Security ─────────────────────────────────────────────────────────────────
export const ATLAS_API_KEY    = optional("ATLAS_API_KEY", "dev-key-change-me");

// ─── Databases ────────────────────────────────────────────────────────────────
export const DATABASE_URL     = optional(
  "DATABASE_URL",
  "postgresql://atlas_user:atlas@postgres:5432/atlas"
);
export const REDIS_URL        = optional("REDIS_URL", "redis://redis:6379");

// ─── Service URLs ─────────────────────────────────────────────────────────────
export const SIGNAL_ENGINE_URL = optional(
  "SIGNAL_ENGINE_URL",
  "http://signal-engine:8001"
);

// ─── Strategy Constants (mirrored from TJR document) ─────────────────────────
/** Rule 7.3: Daily loss limit — session terminated when reached */
export const MAX_DAILY_LOSS_PCT = 2.0;

/** Rule 5.2: Hard SL distance limit from entry */
export const SL_MAX_PIPS = 15;

/** Rule 7.5: Minimum R:R to TP2 (standard sessions) */
export const MIN_RR = 2.0;

/** Rule 1.4: Elevated R:R for wide-range sessions (38–40 pip Asia range) */
export const MIN_RR_WIDE_RANGE = 2.5;

/** Signal expiry TTL in Redis (seconds) — covers LKZ window */
export const SIGNAL_TTL_SECONDS = 300;

/** Management command TTL in Redis (seconds) */
export const MANAGE_CMD_TTL_SECONDS = 60;

/** Maximum candles to retain per timeframe in Redis */
export const CANDLE_BUFFER_SIZE = 200;