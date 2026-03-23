/**
 * api-server/src/routes/trades.ts
 * Trade history and journal statistics endpoints for dashboard.
 */
import { Router, Request, Response } from "express";
import { z }                          from "zod";
import { auth }                       from "../middleware/auth";
import {
  getTrades,
  getTradeById,
  getJournalStats,
}                                     from "../services/tradeService";
import type { TradeFilters, PaginationParams } from "../types";

export const tradesRouter = Router();

// Auth required for all trade data routes
tradesRouter.use(auth);

// ─── GET /api/trades ──────────────────────────────────────────────────────────

const TradesQuerySchema = z.object({
  limit:     z.coerce.number().int().min(1).max(200).optional().default(50),
  offset:    z.coerce.number().int().min(0).optional().default(0),
  status:    z.string().optional(),
  direction: z.enum(["BUY", "SELL"]).optional(),
  grade:     z.enum(["A+", "A", "B", "C"]).optional(),
  from:      z.string().optional(),
  to:        z.string().optional(),
});

tradesRouter.get("/api/trades", async (req: Request, res: Response) => {
  const parsed = TradesQuerySchema.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({
      status:  "error",
      code:    "VALIDATION_ERROR",
      message: parsed.error.message,
    });
    return;
  }

  const { limit, offset, status, direction, grade, from, to } = parsed.data;

  const pagination: PaginationParams = { limit, offset };
  const filters: TradeFilters = {
    ...(status    && { status }),
    ...(direction && { direction }),
    ...(grade     && { grade }),
    ...(from      && { from }),
    ...(to        && { to }),
  };

  const { trades, total } = await getTrades(pagination, filters);

  res.status(200).json({
    status: "ok",
    data:   { trades, total, limit, offset },
  });
});

// ─── GET /api/trades/:id ──────────────────────────────────────────────────────

const UUIDSchema = z.string().uuid();

tradesRouter.get("/api/trades/:id", async (req: Request, res: Response) => {
  const idParsed = UUIDSchema.safeParse(req.params["id"]);
  if (!idParsed.success) {
    res.status(400).json({
      status:  "error",
      code:    "INVALID_ID",
      message: "Trade ID must be a valid UUID",
    });
    return;
  }

  const trade = await getTradeById(idParsed.data);
  if (!trade) {
    res.status(404).json({
      status:  "error",
      code:    "NOT_FOUND",
      message: `Trade ${idParsed.data} not found`,
    });
    return;
  }

  res.status(200).json({ status: "ok", data: trade });
});

// ─── GET /api/journal ─────────────────────────────────────────────────────────
// Returns Section 9.3 statistical edge metrics.

tradesRouter.get("/api/journal", async (_req: Request, res: Response) => {
  const stats = await getJournalStats();
  res.status(200).json({ status: "ok", data: stats });
});