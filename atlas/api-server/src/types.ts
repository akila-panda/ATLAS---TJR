/**
 * api-server/src/types.ts
 * ATLAS API Server — shared TypeScript interfaces.
 * Strict mode: no `any` types anywhere.
 */

// ─── Trading Mode ─────────────────────────────────────────────────────────────
export type AtlasMode = "AUTO" | "MANUAL";

// ─── Database Models ──────────────────────────────────────────────────────────

export interface Session {
  id:                   string;
  session_date:         string;          // ISO date "YYYY-MM-DD"
  asia_high:            number | null;
  asia_low:             number | null;
  asia_range_pips:      number | null;
  range_valid:          boolean | null;
  invalid_reason:       string | null;
  htf_bias:             string | null;   // "BULLISH" | "BEARISH" | "AMBIGUOUS"
  judas_direction:      string | null;   // "BSL" | "SSL"
  sweep_time:           string | null;   // ISO timestamp
  sweep_extension_pips: number | null;
  confluence_score:     number | null;
  setup_grade:          string | null;   // "A+" | "A" | "B" | "C"
  outcome:              string | null;   // "ENTER" | "NO_TRADE"
  created_at:           string;
}

export interface Trade {
  id:           string;
  session_id:   string | null;
  direction:    string;          // "BUY" | "SELL"
  entry_type:   string;          // "FVG_LIMIT" | "OB_LIMIT" | "MSS_MARKET"
  entry_price:  number;
  sl_price:     number;
  tp1_price:    number;
  tp2_price:    number;
  tp3_price:    number;
  lot_size:     number;
  risk_usd:     number;
  rr_ratio:     number;
  mt5_ticket:   number | null;
  status:       string;          // "PENDING" | "OPEN" | "TP1" | "TP2" | "TP3" | "SL" | "BE" | "CLOSED" | "ERROR"
  opened_at:    string | null;
  closed_at:    string | null;
  outcome:      string | null;
  pnl:          number | null;
  created_at:   string;
}

export interface SignalLog {
  id:               string;
  session_id:       string | null;
  timestamp:        string;
  outcome:          string;       // "ENTER" | "NO_TRADE"
  reason:           string | null;
  confluence_score: number | null;
  decision_state:   DecisionState | null;
  created_at:       string;
}

export interface TradeEvent {
  id:         string;
  trade_id:   string;
  event_type: string;   // "TRADE_OPENED" | "TP1_HIT" | "TP2_HIT" | "SL_HIT" | "PARTIAL_CLOSE" | "MODIFY_SL" | "CLOSE_ALL" | etc.
  price:      number | null;
  pips:       number | null;
  timestamp:  string;
  metadata:   Record<string, unknown> | null;
}

// ─── Redis State ──────────────────────────────────────────────────────────────

export interface RiskState {
  daily_loss_pct:    number;
  daily_loss_usd:    number;
  trades_today:      number;
  session_terminated: boolean;
}

export interface TradeState {
  trade_id:       string;
  ticket:         number;
  direction:      string;
  entry_price:    number;
  sl_price:       number;
  tp1_price:      number;
  tp2_price:      number;
  tp3_price:      number;
  original_lot:   number;
  current_lot:    number;
  asia_high:      number;
  asia_low:       number;
  tp1_hit:        boolean;
  tp2_hit:        boolean;
  be_moved:       boolean;
  trailing_active: boolean;
  last_swing:     number | null;
  current_sl:     number;
  opened_at:      string | null;
  close_reason:   string | null;
  close_price:    number | null;
  pnl_usd:        number | null;
}

export interface HTFContext {
  dol_direction:         string;   // "BULLISH" | "BEARISH" | "AMBIGUOUS"
  dol_target_price:      number;
  daily_fvg_above:       boolean;
  daily_fvg_below:       boolean;
  daily_bsl_above:       boolean;
  daily_ssl_below:       boolean;
  htf_bias_score:        number;
  h4_bos_direction:      string | null;
  h4_choch_direction:    string | null;
  h4_fvg_high:           number;
  h4_fvg_low:            number;
  counter_trend_permitted: boolean;
}

// ─── Candle Payloads ──────────────────────────────────────────────────────────

export interface CandleBar {
  datetime: string;   // ISO-8601 "YYYY-MM-DDTHH:MM:SS"
  open:     number;
  high:     number;
  low:      number;
  close:    number;
  volume:   number;
}

export interface CandlePayload {
  symbol:    string;      // "EURUSD" | "GBPUSD"
  timeframe: string;      // "5min" | "15min" | "4h" | "1h" | "1day"
  candles:   CandleBar[];
}

// ─── MT5 ACK Payload ──────────────────────────────────────────────────────────

export interface AckPayload {
  type:        string;   // "OPEN_ACK" | "MANAGE_ACK"
  trade_id:    string;
  ticket:      number;
  status:      string;   // "OK" | "ERROR" | "PARTIAL_CLOSE_OK" | "MODIFY_SL_OK" | "CLOSE_ALL_OK" | etc.
  price:       number;
  error_code:  number;
  message:     string;
}

// ─── Decision Tree State (stored as JSONB) ────────────────────────────────────

export interface DTNode {
  id:     number;
  name:   string;
  passed: boolean;
  reason: string;
  detail: string;
}

export interface DecisionState {
  outcome:    string;
  reason:     string;
  nodes:      DTNode[];
  asia: {
    valid:       boolean;
    high:        number;
    low:         number;
    range_pips:  number;
    wide_range:  boolean;
    required_rr: number;
  };
  sweep: {
    detected:   boolean;
    valid:      boolean;
    direction:  string | null;
    ext_pips:   number;
    is_late_lkz: boolean;
    aligns_dol: boolean;
  };
  structure: {
    choch_15m:    boolean;
    choch_5m:     boolean;
    displacement: boolean;
    bos_5m:       boolean;
  };
  fvg: {
    found:     boolean;
    violated:  boolean;
    expired:   boolean;
    midpoint:  number;
    size_pips: number;
  };
  confluence: {
    total:   number;
    grade:   string;
    factors: Record<string, number>;
  };
  htf_bias:    string;
  news_blocked: boolean;
  entry?: {
    price:   number;
    sl:      number;
    tp1:     number;
    tp2:     number;
    tp3:     number;
    sl_pips: number;
    rr:      number;
    lot:     number;
    method:  string;
  };
}

// ─── Journal Statistics ───────────────────────────────────────────────────────

export interface JournalStats {
  total_trades:          number;
  winning_trades:        number;
  losing_trades:         number;
  win_rate_tp1:          number;
  win_rate_tp2:          number;
  avg_rr:                number;
  expectancy:            number;   // = win_rate * avg_rr - (1 - win_rate)
  profit_factor:         number;
  max_consecutive_losses: number;
  total_pnl_usd:         number;
  sample_size:           number;
}

// ─── API Response wrappers ────────────────────────────────────────────────────

export interface ApiSuccess<T> {
  status: "ok";
  data:   T;
}

export interface ApiError {
  status:  "error";
  code:    string;
  message: string;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;

// ─── Socket.io Event Map ──────────────────────────────────────────────────────

export interface SocketEventMap {
  // Server → Client
  candle:        { symbol: string; timeframe: string; bar: CandleBar };
  signal:        { signal_str: string; mode: AtlasMode; trade_id: string };
  signal_manual: { signal_str: string; trade_id: string };
  trade_opened:  { trade_id: string; ticket: number; price: number; direction: string };
  trade_event:   { trade_id: string; event_type: string; price: number | null };
  mode_change:   { mode: AtlasMode };
  risk_update:   RiskState;
  status:        { mode: AtlasMode; risk: RiskState; uptime: number };

  // Client → Server (control events)
  confirm_signal: Record<string, never>;
  skip_signal:    Record<string, never>;
}

// ─── Query filters ────────────────────────────────────────────────────────────

export interface TradeFilters {
  status?:    string;
  direction?: string;
  grade?:     string;
  from?:      string;   // ISO date
  to?:        string;
}

export interface PaginationParams {
  limit:  number;
  offset: number;
}