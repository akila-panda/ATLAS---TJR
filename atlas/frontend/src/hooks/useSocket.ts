/// <reference types="vite/client" />
/**
 * frontend/src/hooks/useSocket.ts
 * Socket.io connection with exponential reconnect backoff.
 * Wires all server events to Zustand store.
 */
import { useEffect, useRef } from "react";
import { io, Socket }        from "socket.io-client";
import { useAtlasStore }     from "../store/atlasStore";
import type { SignalData, RiskState, SessionState, CandleBar, OpenTrade } from "../store/atlasStore";

const WS_URL = import.meta.env["VITE_WS_URL"] as string ?? "http://localhost:3001";

// Reconnect delays in ms: 1s → 2s → 4s → 8s → 30s (then stays at 30s)
const BACKOFF = [1_000, 2_000, 4_000, 8_000, 30_000];

export function useSocket(): void {
  const socketRef   = useRef<Socket | null>(null);
  const attemptRef  = useRef(0);
  const timerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    setMode,
    setConnectionStatus,
    setSession,
    setOpenTrade,
    clearOpenTrade,
    setLatestSignal,
    setPendingSignal,
    clearPendingSignal,
    appendCandle,
    setRiskState,
    setLastUpdated,
    handleTradeOpened,
    handleTradeEvent,
  } = useAtlasStore.getState();

  useEffect(() => {
    let destroyed = false;

    function connect() {
      if (destroyed) return;

      const socket = io(WS_URL, {
        transports:      ["websocket", "polling"],
        reconnection:    false,   // manual backoff
        timeout:         8_000,
      });
      socketRef.current = socket;

      // ── Connection lifecycle ────────────────────────────────────────────────

      socket.on("connect", () => {
        if (destroyed) return;
        attemptRef.current = 0;
        setConnectionStatus("connected");
        console.log("[ws] connected:", socket.id);
      });

      socket.on("disconnect", (reason) => {
        if (destroyed) return;
        setConnectionStatus("disconnected");
        console.warn("[ws] disconnected:", reason);
        scheduleReconnect();
      });

      socket.on("connect_error", (err) => {
        if (destroyed) return;
        setConnectionStatus("reconnecting");
        console.warn("[ws] connect error:", err.message);
        socket.disconnect();
        scheduleReconnect();
      });

      // ── ATLAS events ────────────────────────────────────────────────────────

      socket.on("status", (data: { mode: string; risk: RiskState; uptime: number }) => {
        if (data.mode === "AUTO" || data.mode === "MANUAL") setMode(data.mode);
        if (data.risk) setRiskState(data.risk);
        setLastUpdated(new Date());
      });

      socket.on("mode_change", (data: { mode: string }) => {
        if (data.mode === "AUTO" || data.mode === "MANUAL") setMode(data.mode);
      });

      socket.on("risk_update", (data: RiskState) => {
        setRiskState(data);
      });

      socket.on("candle", (data: { symbol: string; timeframe: string; bar: CandleBar }) => {
        appendCandle(data.timeframe, data.bar);
        setLastUpdated(new Date());
      });

      // Signal generated — AUTO mode (immediate execution)
      socket.on("signal", (data: Partial<SignalData> & { signal_str?: string; trade_id?: string }) => {
        const parsed = parseSignalStr(data.signal_str ?? "", data.trade_id ?? "");
        if (parsed) {
          setLatestSignal({ ...parsed, ...(data as Partial<SignalData>) });
          clearPendingSignal();
        }
      });

      // Signal generated — MANUAL mode (awaiting confirmation)
      socket.on("signal_manual", (data: Partial<SignalData> & { signal_str?: string; trade_id?: string }) => {
        const parsed = parseSignalStr(data.signal_str ?? "", data.trade_id ?? "");
        if (parsed) {
          setPendingSignal({ ...parsed, ...(data as Partial<SignalData>) });
        }
      });

      socket.on("trade_opened", (data: { trade_id: string; ticket: number; price: number; direction: string }) => {
        handleTradeOpened(data);
        clearPendingSignal();
      });

      socket.on("trade_event", (data: { trade_id: string; event_type: string; price: number | null }) => {
        handleTradeEvent(data);
      });

      socket.on("session", (data: SessionState) => {
        setSession(data);
      });
    }

    function scheduleReconnect() {
      if (destroyed) return;
      setConnectionStatus("reconnecting");
      const delay = BACKOFF[Math.min(attemptRef.current, BACKOFF.length - 1)] ?? 30_000;
      attemptRef.current++;
      console.log(`[ws] reconnecting in ${delay}ms (attempt ${attemptRef.current})`);
      timerRef.current = setTimeout(connect, delay);
    }

    connect();

    return () => {
      destroyed = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.disconnect();
      socketRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

/**
 * Parse pipe-delimited signal string into SignalData fields.
 * Format: ACTION|LOT|SL|TP1|TP2|TP3|TRADE_ID
 */
function parseSignalStr(signalStr: string, tradeId: string): SignalData | null {
  if (!signalStr || signalStr === "null") return null;
  const parts = signalStr.split("|");
  if (parts.length < 7) return null;

  const [action, lotStr, slStr, tp1Str, tp2Str, tp3Str, tid] = parts;

  return {
    signal_str:      signalStr,
    trade_id:        tid ?? tradeId,
    direction:       action === "BUY" ? "BUY" : "SELL",
    entry_price:     0,  // populated via decision_state in full signal event
    sl_price:        parseFloat(slStr  ?? "0"),
    tp1_price:       parseFloat(tp1Str ?? "0"),
    tp2_price:       parseFloat(tp2Str ?? "0"),
    tp3_price:       parseFloat(tp3Str ?? "0"),
    lot_size:        parseFloat(lotStr ?? "0"),
    sl_pips:         0,
    rr_ratio:        0,
    setup_grade:     "",
    confluence_score: 0,
    outcome:         "ENTER",
    reason:          "ENTER",
    decision_state:  null,
  };
}