/// <reference types="vite/client" />
/**
 * frontend/src/lib/api.ts
 * ATLAS typed API client — axios with x-atlas-key header.
 */
import axios from "axios";

const BASE_URL = import.meta.env["VITE_API_URL"] as string ?? "http://localhost:3001";
const API_KEY  = import.meta.env["VITE_API_KEY"]  as string ?? "";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type":  "application/json",
    "x-atlas-key":   API_KEY,
  },
  timeout: 10_000,
});

// ─── Types ────────────────────────────────────────────────────────────────────

export type AtlasMode = "AUTO" | "MANUAL";

export interface JournalStats {
  total_trades:           number;
  winning_trades:         number;
  losing_trades:          number;
  win_rate_tp1:           number;
  win_rate_tp2:           number;
  avg_rr:                 number;
  expectancy:             number;
  profit_factor:          number;
  max_consecutive_losses: number;
  total_pnl_usd:          number;
  sample_size:            number;
}

export interface TradeRecord {
  id:               string;
  direction:        string;
  entry_type:       string;
  entry_price:      number;
  sl_price:         number;
  tp1_price:        number;
  tp2_price:        number;
  lot_size:         number;
  risk_usd:         number;
  rr_ratio:         number;
  sl_pips:          number;
  confluence_score: number;
  setup_grade:      string;
  mt5_ticket:       number | null;
  status:           string;
  opened_at:        string | null;
  closed_at:        string | null;
  outcome:          string | null;
  close_reason:     string | null;
  pnl:              number | null;
  created_at:       string;
  decision_state:   Record<string, unknown> | null;
}

export interface TradesResponse {
  trades: TradeRecord[];
  total:  number;
  limit:  number;
  offset: number;
}

export interface TradesParams {
  limit?:     number;
  offset?:    number;
  status?:    string;
  direction?: string;
  grade?:     string;
  from?:      string;
  to?:        string;
}

// ─── API functions ────────────────────────────────────────────────────────────

export async function setMode(mode: AtlasMode): Promise<void> {
  await apiClient.post("/api/control/mode", { mode });
}

export async function confirmTrade(signalId: string): Promise<{ trade_id: string }> {
  const res = await apiClient.post<{ status: string; trade_id: string }>(
    "/api/control/confirm",
    { signal_id: signalId }
  );
  return { trade_id: res.data.trade_id };
}

export async function skipTrade(): Promise<void> {
  await apiClient.post("/api/control/skip");
}

export async function getTrades(params: TradesParams = {}): Promise<TradesResponse> {
  const res = await apiClient.get<{ status: string; data: TradesResponse }>(
    "/api/trades",
    { params }
  );
  return res.data.data;
}

export async function getJournalStats(): Promise<JournalStats> {
  const res = await apiClient.get<{ status: string; data: JournalStats }>(
    "/api/journal"
  );
  return res.data.data;
}

export async function closeTrade(id: string): Promise<void> {
  await apiClient.post(`/api/trades/${id}/close`);
}

export async function getStatus(): Promise<{
  mode: AtlasMode;
  risk_state: { daily_loss_pct: number; session_terminated: boolean; trades_today: number };
  uptime_sec: number;
}> {
  const res = await apiClient.get("/api/status");
  return res.data.data as {
    mode: AtlasMode;
    risk_state: { daily_loss_pct: number; session_terminated: boolean; trades_today: number };
    uptime_sec: number;
  };
}