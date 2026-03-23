/**
 * api-server/src/services/signalService.ts
 * Forwards candle payloads to the Python signal engine.
 * Acts as the HTTP proxy layer between MT5 and FastAPI.
 */
import axios, { AxiosError } from "axios";
import { SIGNAL_ENGINE_URL } from "../config";
import type { CandlePayload } from "../types";

/**
 * Forward a candle batch to the Python signal engine.
 * The signal engine runs the full TJR pipeline on each M5 close.
 *
 * Non-blocking: failures are logged but do not propagate to MT5.
 * The EA should not be kept waiting on Python processing time.
 */
export async function forwardCandlesToEngine(
  payload: CandlePayload
): Promise<void> {
  try {
    await axios.post(
      `${SIGNAL_ENGINE_URL}/mt5/candles`,
      payload,
      {
        timeout: 5_000,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (err) {
    const axErr = err as AxiosError;
    const status = axErr.response?.status ?? "network_error";
    // Log but do not throw — MT5 must receive 200 regardless of engine state
    console.error(
      `[signalService] forward failed: ${status} — ${axErr.message}`
    );
  }
}

/**
 * Forward ACK to the Python signal engine for trade state updates.
 * Used when Node receives /mt5/ack from EA — Python also needs to know.
 */
export async function forwardAckToEngine(
  payload: Record<string, unknown>
): Promise<void> {
  try {
    await axios.post(
      `${SIGNAL_ENGINE_URL}/mt5/ack`,
      payload,
      {
        timeout: 3_000,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (err) {
    const axErr = err as AxiosError;
    console.error(
      `[signalService] ack forward failed: ${axErr.response?.status ?? "network_error"}`
    );
  }
}