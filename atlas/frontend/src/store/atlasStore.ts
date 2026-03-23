/**
 * frontend/src/store/atlasStore.ts
 * ATLAS Zustand store — single source of truth for all live data.
 */
import { create } from "zustand";

// ─── Types ────────────────────────────────────────────────────────────────────

export type AtlasMode = "AUTO" | "MANUAL";
export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

export interface CandleBar {
  datetime: string;
  open:     number;
  high:     number;
  low:      number;
  close:    number;
  volume:   number;
}

export interface RiskState {
  daily_loss_pct:     number;
  daily_loss_usd:     number;
  trades_today:       number;
  session_terminated: boolean;
}

export interface SessionState {
  session_date:         string;
  asia_high:            number | null;
  asia_low:             number | null;
  asia_range_pips:      number | null;
  range_valid:          boolean;
  invalid_reason:       string | null;
  htf_bias:             string | null;
  judas_direction:      string | null;
  sweep_time:           string | null;
  sweep_extension_pips: number | null;
  confluence_score:     number | null;
  setup_grade:          string | null;
  outcome:              string | null;
}

export interface SignalData {
  signal_str:      string;
  trade_id:        string;
  direction:       string;    // "BUY" | "SELL"
  entry_price:     number;
  sl_price:        number;
  tp1_price:       number;
  tp2_price:       number;
  tp3_price:       number;
  lot_size:        number;
  sl_pips:         number;
  rr_ratio:        number;
  setup_grade:     string;
  confluence_score: number;
  outcome:         string;    // "ENTER" | "NO_TRADE"
  reason:          string;
  decision_state:  Record<string, unknown> | null;
}

export interface OpenTrade {
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
  tp1_hit:        boolean;
  tp2_hit:        boolean;
  be_moved:       boolean;
  trailing_active: boolean;
  current_sl:     number;
  opened_at:      string | null;
  unrealized_pnl: number;
}

export interface TradeEvent {
  trade_id:   string;
  event_type: string;
  price:      number | null;
}

// ─── Store interface ──────────────────────────────────────────────────────────

interface AtlasState {
  // System state
  mode:             AtlasMode;
  connectionStatus: ConnectionStatus;
  lastUpdated:      Date | null;

  // Session data
  session:          SessionState | null;

  // Trade data
  openTrade:        OpenTrade | null;
  latestSignal:     SignalData | null;
  pendingSignal:    SignalData | null;   // MANUAL mode — awaiting confirm

  // Candle data (capped at 200 per timeframe)
  candles:          Map<string, CandleBar[]>;

  // Risk state
  riskState:        RiskState;

  // Actions
  setMode:              (mode: AtlasMode) => void;
  setConnectionStatus:  (status: ConnectionStatus) => void;
  setSession:           (session: SessionState) => void;
  setOpenTrade:         (trade: OpenTrade | null) => void;
  clearOpenTrade:       () => void;
  setLatestSignal:      (signal: SignalData) => void;
  setPendingSignal:     (signal: SignalData | null) => void;
  clearPendingSignal:   () => void;
  appendCandle:         (timeframe: string, bar: CandleBar) => void;
  setCandles:           (timeframe: string, bars: CandleBar[]) => void;
  setRiskState:         (risk: RiskState) => void;
  setLastUpdated:       (date: Date) => void;
  handleTradeOpened:    (payload: { trade_id: string; ticket: number; price: number; direction: string }) => void;
  handleTradeEvent:     (event: TradeEvent) => void;
}

const MAX_CANDLES = 200;

const DEFAULT_RISK: RiskState = {
  daily_loss_pct:     0,
  daily_loss_usd:     0,
  trades_today:       0,
  session_terminated: false,
};

// ─── Store implementation ─────────────────────────────────────────────────────

export const useAtlasStore = create<AtlasState>((set, get) => ({
  mode:             "MANUAL",
  connectionStatus: "disconnected",
  lastUpdated:      null,
  session:          null,
  openTrade:        null,
  latestSignal:     null,
  pendingSignal:    null,
  candles:          new Map(),
  riskState:        DEFAULT_RISK,

  setMode: (mode) => set({ mode }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setSession: (session) => set({ session }),

  setOpenTrade: (trade) => set({ openTrade: trade }),

  clearOpenTrade: () => set({ openTrade: null }),

  setLatestSignal: (signal) => set({ latestSignal: signal }),

  setPendingSignal: (signal) => set({ pendingSignal: signal }),

  clearPendingSignal: () => set({ pendingSignal: null }),

  appendCandle: (timeframe, bar) => {
    const current = new Map(get().candles);
    const existing = current.get(timeframe) ?? [];
    const updated = [...existing, bar].slice(-MAX_CANDLES);
    current.set(timeframe, updated);
    set({ candles: current, lastUpdated: new Date() });
  },

  setCandles: (timeframe, bars) => {
    const current = new Map(get().candles);
    current.set(timeframe, bars.slice(-MAX_CANDLES));
    set({ candles: current });
  },

  setRiskState: (risk) => set({ riskState: risk }),

  setLastUpdated: (date) => set({ lastUpdated: date }),

  handleTradeOpened: (payload) => {
    const existing = get().openTrade;
    const latest   = get().latestSignal;
    if (existing) return; // already tracking one

    const newTrade: OpenTrade = {
      trade_id:       payload.trade_id,
      ticket:         payload.ticket,
      direction:      payload.direction || latest?.direction || "BUY",
      entry_price:    payload.price,
      sl_price:       latest?.sl_price    ?? 0,
      tp1_price:      latest?.tp1_price   ?? 0,
      tp2_price:      latest?.tp2_price   ?? 0,
      tp3_price:      latest?.tp3_price   ?? 0,
      original_lot:   latest?.lot_size    ?? 0,
      current_lot:    latest?.lot_size    ?? 0,
      tp1_hit:        false,
      tp2_hit:        false,
      be_moved:       false,
      trailing_active: false,
      current_sl:     latest?.sl_price    ?? 0,
      opened_at:      new Date().toISOString(),
      unrealized_pnl: 0,
    };
    set({ openTrade: newTrade });
  },

  handleTradeEvent: (event) => {
    const trade = get().openTrade;
    if (!trade || trade.trade_id !== event.trade_id) return;

    switch (event.event_type) {
      case "TP1_HIT":
        set({ openTrade: { ...trade, tp1_hit: true, be_moved: true } });
        break;
      case "TP2_HIT":
        set({ openTrade: { ...trade, tp2_hit: true, trailing_active: true } });
        break;
      case "MODIFY_SL_OK":
      case "TRAILING_SL_MOVED":
        set({ openTrade: { ...trade, current_sl: event.price ?? trade.current_sl } });
        break;
      case "CLOSE_ALL_OK":
      case "TRADE_CLOSED":
        set({ openTrade: null, pendingSignal: null });
        break;
      default:
        break;
    }
  },
}));