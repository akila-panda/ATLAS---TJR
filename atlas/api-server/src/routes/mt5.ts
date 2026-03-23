/**
 * api-server/src/routes/mt5.ts
 * MT5 EA → Node.js bridge routes.
 * No auth required — EA cannot carry API keys (Wine/MT5 constraint).
 */
import { Router, Request, Response } from "express";
import { z }                          from "zod";
import { appendCandles }              from "../services/redisService";
import { forwardCandlesToEngine, forwardAckToEngine } from "../services/signalService";
import {
  updateTradeStatus,
  insertTradeEvent,
  updateTradeClose,
} from "../services/tradeService";
import { getIo }                      from "../websocket/broadcaster";
import type { CandlePayload, AckPayload } from "../types";

export const mt5Router = Router();

// ─── Zod validation schemas ───────────────────────────────────────────────────

const CandleBarSchema = z.object({
  datetime: z.string(),
  open:     z.number(),
  high:     z.number(),
  low:      z.number(),
  close:    z.number(),
  volume:   z.number().optional().default(0),
});

const CandleBatchSchema = z.object({
  symbol:    z.string().min(1),
  timeframe: z.enum(["5min", "15min", "4h", "1h", "1day"]),
  candles:   z.array(CandleBarSchema).min(1).max(500),
});

const AckSchema = z.object({
  type:        z.string(),
  trade_id:    z.string().min(1),
  ticket:      z.number().int(),
  status:      z.string(),
  price:       z.number(),
  error_code:  z.number().int().optional().default(0),
  message:     z.string().optional().default(""),
});

// ─── POST /mt5/candles ────────────────────────────────────────────────────────

mt5Router.post("/mt5/candles", async (req: Request, res: Response) => {
  const parsed = CandleBatchSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      status:  "error",
      code:    "VALIDATION_ERROR",
      message: parsed.error.message,
    });
    return;
  }

  const payload = parsed.data as CandlePayload;
  const io      = getIo();

  // 1. Store latest candles in Redis buffer (trimmed to 200 per timeframe)
  await appendCandles(payload.timeframe, payload.candles);

  // 2. Broadcast latest candle to dashboard via Socket.io
  const latestBar = payload.candles[payload.candles.length - 1];
  if (latestBar) {
    io.emit("candle", {
      symbol:    payload.symbol,
      timeframe: payload.timeframe,
      bar:       latestBar,
    });
  }

  // 3. Forward full batch to Python signal engine (non-blocking)
  // Fire-and-forget — EA must receive 200 immediately
  void forwardCandlesToEngine(payload);

  res.status(200).json({ status: "ok", ingested: payload.candles.length });
});

// ─── POST /mt5/ack ────────────────────────────────────────────────────────────

mt5Router.post("/mt5/ack", async (req: Request, res: Response) => {
  const parsed = AckSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      status:  "error",
      code:    "VALIDATION_ERROR",
      message: parsed.error.message,
    });
    return;
  }

  const ack: AckPayload = {
    type:       parsed.data.type,
    trade_id:   parsed.data.trade_id,
    ticket:     parsed.data.ticket,
    status:     parsed.data.status,
    price:      parsed.data.price,
    error_code: parsed.data.error_code,
    message:    parsed.data.message,
  };

  const io = getIo();

  try {
    if (ack.type === "OPEN_ACK") {
      if (ack.status === "OK") {
        // Update DB: PENDING → OPEN with MT5 ticket
        await updateTradeStatus(ack.trade_id, "OPEN", ack.ticket);

        // Broadcast to dashboard
        io.emit("trade_opened", {
          trade_id:  ack.trade_id,
          ticket:    ack.ticket,
          price:     ack.price,
          direction: "", // direction populated from client state
        });

        console.log(
          `[mt5/ack] trade opened — id=${ack.trade_id} ticket=${ack.ticket} @ ${ack.price}`
        );
      } else {
        await updateTradeStatus(ack.trade_id, "ERROR");
        console.warn(
          `[mt5/ack] trade open FAILED — id=${ack.trade_id} code=${ack.error_code} msg=${ack.message}`
        );
      }
    } else if (ack.type === "MANAGE_ACK") {
      // Record event in trade_events table
      const isClose = ack.status.includes("CLOSE");
      const meta: Record<string, unknown> = {
        status:     ack.status,
        error_code: ack.error_code,
        message:    ack.message,
      };

      await insertTradeEvent(ack.trade_id, ack.status, ack.price, null, meta);

      // If CLOSE_ALL_OK: finalise trade record
      if (ack.status === "CLOSE_ALL_OK") {
        const closeReason = ack.message || "CLOSE_ALL";
        // P&L computed by Python signal engine — pass 0 here;
        // Python's /mt5/ack handler calculates and persists the definitive P&L
        await updateTradeClose(ack.trade_id, closeReason, 0, closeReason);
      }

      // Broadcast event to dashboard
      io.emit("trade_event", {
        trade_id:   ack.trade_id,
        event_type: ack.status,
        price:      ack.price,
      });
    }

    // Forward ACK to Python engine for definitive state updates
    void forwardAckToEngine(ack as unknown as Record<string, unknown>);

  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[mt5/ack] error: ${msg}`);
    // Return 200 regardless — EA must not retry ACKs
  }

  res.status(200).json({ status: "ok" });
});