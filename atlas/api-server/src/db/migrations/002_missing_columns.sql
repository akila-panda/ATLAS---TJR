-- api-server/src/db/migrations/002_missing_columns.sql
-- Fixes all column mismatches between signal-engine/db/postgres.py and the schema.
-- Applied automatically on a fresh `docker compose down -v && docker compose up`.
-- For a running cluster, apply via the one-liner in fix_all.md instead.

-- ─── signal_logs: add generated_at ──────────────────────────────────────────
-- Python insert_signal_log() passes generated_at as $13.
ALTER TABLE signal_logs
  ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ;

-- ─── trades: add columns Python insert_trade() requires ──────────────────────
-- trade_id: Python uses its own UUID; migration PK is `id`.
ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS trade_id UUID UNIQUE DEFAULT gen_random_uuid();

-- signal_id: foreign reference to signal_logs.signal_id.
ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS signal_id UUID;

-- risk_pct: percentage risk per trade (e.g. 0.01 = 1%).
ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS risk_pct NUMERIC(5,4);

-- close_price: Python update_trade_close() writes this; migration only had pnl.
ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS close_price NUMERIC(10,5);

-- symbol: Python hardcodes 'EURUSD'; keep for multi-pair future-proofing.
ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS symbol VARCHAR(10) DEFAULT 'EURUSD';

-- ─── trade_events: add description ──────────────────────────────────────────
-- Python insert_trade_event() passes description as $3; migration only had metadata.
ALTER TABLE trade_events
  ADD COLUMN IF NOT EXISTS description TEXT;

-- ─── Backfill trade_id for any rows created before this migration ─────────────
UPDATE trades
SET trade_id = gen_random_uuid()
WHERE trade_id IS NULL;
