-- api-server/src/db/migrations/001_initial.sql
-- ATLAS System — PostgreSQL schema
-- Run automatically on first docker-compose up via postgres entrypoint

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Sessions ─────────────────────────────────────────────────────────────────
-- One row per trading day (Asia session + LKZ).
-- Records whether a valid TJR setup was identified and its outcome.
CREATE TABLE IF NOT EXISTS sessions (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_date         DATE        NOT NULL UNIQUE,
  asia_high            NUMERIC(10,5),
  asia_low             NUMERIC(10,5),
  asia_range_pips      NUMERIC(6,2),
  range_valid          BOOLEAN,
  invalid_reason       TEXT,
  htf_bias             VARCHAR(10),          -- 'BULLISH' | 'BEARISH' | 'AMBIGUOUS'
  judas_direction      VARCHAR(10),          -- 'BSL' | 'SSL'
  sweep_time           TIMESTAMPTZ,
  sweep_extension_pips NUMERIC(5,2),
  confluence_score     INT,
  setup_grade          VARCHAR(3),           -- 'A+' | 'A' | 'B' | 'C'
  outcome              VARCHAR(20),          -- 'ENTER' | 'NO_TRADE'
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Trades ───────────────────────────────────────────────────────────────────
-- Every trade that passed the decision tree (status starts as PENDING).
CREATE TABLE IF NOT EXISTS trades (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID        REFERENCES sessions(id) ON DELETE SET NULL,
  direction    VARCHAR(5)  NOT NULL,          -- 'BUY' | 'SELL'
  entry_type   VARCHAR(15) NOT NULL,          -- 'FVG_LIMIT' | 'OB_LIMIT' | 'MSS_MARKET'
  entry_price  NUMERIC(10,5) NOT NULL,
  sl_price     NUMERIC(10,5) NOT NULL,
  tp1_price    NUMERIC(10,5) NOT NULL,
  tp2_price    NUMERIC(10,5) NOT NULL,
  tp3_price    NUMERIC(10,5),
  lot_size     NUMERIC(6,2)  NOT NULL,
  risk_usd     NUMERIC(8,2)  NOT NULL,
  rr_ratio     NUMERIC(5,2)  NOT NULL,
  sl_pips      NUMERIC(5,2),
  confluence_score INT,
  setup_grade  VARCHAR(3),
  asia_high    NUMERIC(10,5),
  asia_low     NUMERIC(10,5),
  asia_range_pips NUMERIC(6,2),
  sweep_direction VARCHAR(5),
  sweep_extension_pips NUMERIC(5,2),
  mt5_ticket   INT,
  status       VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  -- PENDING | OPEN | TP1 | TP2 | TP3 | SL | BE | CLOSED | ERROR
  opened_at    TIMESTAMPTZ,
  closed_at    TIMESTAMPTZ,
  outcome      VARCHAR(20),
  close_reason TEXT,
  pnl          NUMERIC(10,2),
  account_balance NUMERIC(12,2),
  decision_state JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Signal Log ───────────────────────────────────────────────────────────────
-- Every pipeline run — including all NO_TRADE outcomes (Section 9.1).
-- Enables full backtesting review and edge analysis.
CREATE TABLE IF NOT EXISTS signal_logs (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id        UUID        UNIQUE,
  session_id       UUID        REFERENCES sessions(id) ON DELETE SET NULL,
  timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  outcome          VARCHAR(20) NOT NULL,       -- 'ENTER' | 'NO_TRADE'
  reason           VARCHAR(100),
  direction        VARCHAR(5),
  confluence_score INT,
  setup_grade      VARCHAR(3),
  asia_high        NUMERIC(10,5),
  asia_low         NUMERIC(10,5),
  asia_range_pips  NUMERIC(6,2),
  sweep_direction  VARCHAR(5),
  sweep_extension_pips NUMERIC(5,2),
  decision_state   JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Trade Events ─────────────────────────────────────────────────────────────
-- Granular lifecycle events per trade (Section 9.1 journaling).
CREATE TABLE IF NOT EXISTS trade_events (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_id    UUID        NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
  event_type  VARCHAR(30) NOT NULL,
  -- TRADE_OPENED | PARTIAL_CLOSE | SL_MODIFIED | TP1_HIT | TP2_HIT |
  -- TRAILING_SL_MOVED | TRADE_CLOSED | TIME_KILL | INVALIDATION_EXIT |
  -- TP1_REVERSAL_EXIT | OPEN_FAILED | MANAGE_ERROR
  price       NUMERIC(10,5),
  pips        NUMERIC(6,2),
  lots        NUMERIC(6,2),
  pnl_usd     NUMERIC(10,2),
  timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata    JSONB
);

-- ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sessions_date
  ON sessions(session_date DESC);

CREATE INDEX IF NOT EXISTS idx_trades_session_status
  ON trades(session_id, status);

CREATE INDEX IF NOT EXISTS idx_trades_created
  ON trades(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trades_status
  ON trades(status);

CREATE INDEX IF NOT EXISTS idx_signal_logs_timestamp
  ON signal_logs(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_signal_logs_outcome
  ON signal_logs(outcome);

CREATE INDEX IF NOT EXISTS idx_trade_events_trade_id
  ON trade_events(trade_id);

CREATE INDEX IF NOT EXISTS idx_trade_events_timestamp
  ON trade_events(timestamp DESC);