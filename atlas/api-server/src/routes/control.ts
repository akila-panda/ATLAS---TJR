/**
 * api-server/src/routes/control.ts
 * Dashboard control endpoints — mode toggle and manual signal confirmation.
 * auth middleware required on all routes.
 */
import { Router, Request, Response } from "express";
import { z }                          from "zod";
import { auth }                       from "../middleware/auth";
import { signalParamGuard }           from "../middleware/riskGuard";
import {
  getMode,
  setMode,
  confirmManualSignal,
  clearPendingSignalManual,
}                                     from "../services/redisService";
import { getIo }                      from "../websocket/broadcaster";
import type { AtlasMode }             from "../types";

export const controlRouter = Router();

// All control routes require API key auth
controlRouter.use(auth);

// ─── POST /api/control/mode ───────────────────────────────────────────────────

const ModeSchema = z.object({
  mode: z.enum(["AUTO", "MANUAL"]),
});

controlRouter.post(
  "/api/control/mode",
  async (req: Request, res: Response) => {
    const parsed = ModeSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({
        status:  "error",
        code:    "VALIDATION_ERROR",
        message: `mode must be 'AUTO' or 'MANUAL'`,
      });
      return;
    }

    const { mode } = parsed.data;
    await setMode(mode as AtlasMode);

    // Broadcast mode change to all connected dashboard clients
    getIo().emit("mode_change", { mode });

    console.log(`[control] mode changed to ${mode}`);
    res.status(200).json({ status: "ok", mode });
  }
);

// ─── POST /api/control/confirm ────────────────────────────────────────────────
// MANUAL mode: trader clicks CONFIRM on dashboard.
// Moves signal from manual queue → live signal queue for EA consumption.

controlRouter.post(
  "/api/control/confirm",
  signalParamGuard,
  async (req: Request, res: Response) => {
    const currentMode = await getMode();

    if (currentMode !== "MANUAL") {
      res.status(400).json({
        status:  "error",
        code:    "NOT_MANUAL_MODE",
        message: "Signal confirmation is only available in MANUAL mode",
      });
      return;
    }

    const sig = await confirmManualSignal();

    if (!sig) {
      res.status(404).json({
        status:  "error",
        code:    "NO_PENDING_SIGNAL",
        message: "No manual signal is pending confirmation",
      });
      return;
    }

    // Extract trade_id from signal for broadcast
    const parts   = sig.split("|");
    const tradeId = parts[6] ?? "unknown";

    // Broadcast signal confirmed to dashboard
    getIo().emit("signal", {
      signal_str: sig,
      mode:       "MANUAL" as AtlasMode,
      trade_id:   tradeId,
    });

    console.log(`[control] manual signal confirmed — trade_id=${tradeId}`);
    res.status(200).json({ status: "ok", trade_id: tradeId });
  }
);

// ─── POST /api/control/skip ───────────────────────────────────────────────────
// MANUAL mode: trader clicks SKIP on dashboard.

controlRouter.post(
  "/api/control/skip",
  async (req: Request, res: Response) => {
    const currentMode = await getMode();

    if (currentMode !== "MANUAL") {
      res.status(400).json({
        status:  "error",
        code:    "NOT_MANUAL_MODE",
        message: "Skip is only relevant in MANUAL mode",
      });
      return;
    }

    await clearPendingSignalManual();
    console.log("[control] manual signal skipped");
    res.status(200).json({ status: "ok", skipped: true });
  }
);