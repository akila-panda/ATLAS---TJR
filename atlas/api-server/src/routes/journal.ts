/**
 * api-server/src/routes/journal.ts
 * Extended journal routes — signal logs and session history.
 */
import { Router, Request, Response } from "express";
import { z }                          from "zod";
import { auth }                       from "../middleware/auth";
import { query }                      from "../db/postgres";
import type { SignalLog }             from "../types";

export const journalRouter = Router();
journalRouter.use(auth);

// ─── GET /api/journal/signals ─────────────────────────────────────────────────
// Returns recent pipeline runs including NO_TRADE outcomes.

const PaginationSchema = z.object({
  limit:   z.coerce.number().int().min(1).max(200).optional().default(100),
  offset:  z.coerce.number().int().min(0).optional().default(0),
  outcome: z.enum(["ENTER", "NO_TRADE"]).optional(),
});

journalRouter.get("/api/journal/signals", async (req: Request, res: Response) => {
  const parsed = PaginationSchema.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ status: "error", code: "VALIDATION_ERROR", message: parsed.error.message });
    return;
  }

  const { limit, offset, outcome } = parsed.data;
  const params: unknown[] = [];
  const conditions: string[] = [];
  let idx = 1;

  if (outcome) {
    conditions.push(`outcome = $${idx++}`);
    params.push(outcome);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

  const countResult = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM signal_logs ${where}`, params
  );
  const total = parseInt(countResult.rows[0]?.count ?? "0", 10);

  const dataResult = await query<SignalLog>(
    `SELECT id, outcome, reason, confluence_score, asia_range_pips,
            sweep_direction, sweep_extension_pips, setup_grade,
            created_at
     FROM signal_logs ${where}
     ORDER BY created_at DESC
     LIMIT $${idx} OFFSET $${idx + 1}`,
    [...params, limit, offset]
  );

  res.status(200).json({
    status: "ok",
    data:   { signals: dataResult.rows, total, limit, offset },
  });
});

// ─── GET /api/journal/signals/:id ────────────────────────────────────────────

journalRouter.get("/api/journal/signals/:id", async (req: Request, res: Response) => {
  const id = req.params["id"];
  const result = await query<SignalLog>(
    `SELECT * FROM signal_logs WHERE id = $1`, [id]
  );

  if (result.rows.length === 0) {
    res.status(404).json({ status: "error", code: "NOT_FOUND", message: "Signal log not found" });
    return;
  }

  res.status(200).json({ status: "ok", data: result.rows[0] });
});