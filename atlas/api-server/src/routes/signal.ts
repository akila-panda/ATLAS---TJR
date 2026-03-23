/**
 * api-server/src/routes/signal.ts
 * EA polling endpoints — GET /signal and GET /manage.
 * Plain-text responses (no JSON) — EA parses raw string.
 * riskGuard applied before signal delivery.
 */
import { Router, Request, Response } from "express";
import { riskGuard }                  from "../middleware/riskGuard";
import {
  getMode,
  getPendingSignal,
  getPendingSignalManual,
  getManageCmd,
}                                     from "../services/redisService";

export const signalRouter = Router();

// ─── GET /signal ──────────────────────────────────────────────────────────────
// Polled by ATLAS_EA.mq5 every second when no position is open.
// Returns the pending signal string or "null".

signalRouter.get("/signal", riskGuard, async (req: Request, res: Response) => {
  const mode = await getMode();

  // AUTO mode: return signal immediately for EA execution
  // MANUAL mode: signal sits in manual queue until dashboard confirms
  const sig = mode === "AUTO"
    ? await getPendingSignal()
    : await getPendingSignalManual();

  res.setHeader("Content-Type", "text/plain");
  res.send(sig ?? "null");
});

// ─── GET /manage ──────────────────────────────────────────────────────────────
// Polled by ATLAS_EA.mq5 every second when a position is open.
// Returns the pending management command for the given ticket or "null".

signalRouter.get("/manage", async (req: Request, res: Response) => {
  const ticketStr = req.query["ticket"];
  const ticket    = typeof ticketStr === "string" ? parseInt(ticketStr, 10) : NaN;

  if (isNaN(ticket) || ticket <= 0) {
    res.setHeader("Content-Type", "text/plain");
    res.send("null");
    return;
  }

  const cmd = await getManageCmd(ticket);
  res.setHeader("Content-Type", "text/plain");
  res.send(cmd ?? "null");
});