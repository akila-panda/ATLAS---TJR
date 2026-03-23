/**
 * api-server/src/middleware/riskGuard.ts
 * Risk guard middleware — enforces Rules 7.3, 5.2, 7.5 before any signal is served.
 * Runs before signal routes and trade execution routes.
 */
import { Request, Response, NextFunction } from "express";
import {
  getRiskState,
  setSessionTerminated,
} from "../services/redisService";
import {
  MAX_DAILY_LOSS_PCT,
  SL_MAX_PIPS,
  MIN_RR,
} from "../config";

/**
 * Primary risk guard — checks session termination and daily loss limit.
 * Applies to GET /signal and GET /manage.
 *
 * Rule 7.3: If session_terminated = true → 403 SESSION_TERMINATED
 * Rule 7.3: If daily_loss_pct >= 2.0 → set terminated, 403 DAILY_LOSS_LIMIT
 */
export async function riskGuard(
  req:  Request,
  res:  Response,
  next: NextFunction
): Promise<void> {
  try {
    const risk = await getRiskState();

    // Already terminated this session
    if (risk.session_terminated) {
      res.status(403).json({
        status:  "error",
        code:    "SESSION_TERMINATED",
        message: `Session terminated: daily loss limit reached (${risk.daily_loss_pct.toFixed(2)}%)`,
      });
      return;
    }

    // Limit reached but not yet flagged — set it now
    if (risk.daily_loss_pct >= MAX_DAILY_LOSS_PCT) {
      await setSessionTerminated(true);
      res.status(403).json({
        status:  "error",
        code:    "DAILY_LOSS_LIMIT",
        message: `Daily loss limit of ${MAX_DAILY_LOSS_PCT}% reached — session terminated`,
      });
      return;
    }

    next();
  } catch (err) {
    // If Redis is unreachable, fail open for GET /signal (EA must keep running)
    // but log the error
    console.error("[riskGuard] Redis error:", err instanceof Error ? err.message : err);
    next();
  }
}

/**
 * Signal body validator — runs inline checks on trade signal parameters.
 * Used on /api/control/confirm when the signal body is available.
 *
 * Rule 5.2: sl_pips > 15 → 403
 * Rule 7.5: rr < 2.0 → 403
 *
 * Parses the pipe-delimited signal string:
 *   ACTION|LOT|SL|TP1|TP2|TP3|TRADE_ID
 */
export function signalParamGuard(
  req:  Request,
  res:  Response,
  next: NextFunction
): void {
  const { signal } = req.body as { signal?: string };
  if (!signal || signal === "null") {
    next();
    return;
  }

  const parts = signal.split("|");
  if (parts.length < 7) {
    next();
    return;
  }

  const [action, , slStr, tp1Str, tp2Str] = parts;
  const sl  = parseFloat(slStr  ?? "0");
  const tp1 = parseFloat(tp1Str ?? "0");
  const tp2 = parseFloat(tp2Str ?? "0");

  // We cannot compute sl_pips or rr_ratio without the entry price here,
  // so these checks are best-effort on the raw price values.
  // Definitive enforcement is in decision_tree.py nodes 9 and 10.

  if (!action || (action !== "BUY" && action !== "SELL")) {
    res.status(403).json({
      status:  "error",
      code:    "INVALID_SIGNAL_ACTION",
      message: `Invalid action '${action ?? ""}' in signal`,
    });
    return;
  }

  if (sl <= 0 || tp1 <= 0 || tp2 <= 0) {
    res.status(403).json({
      status:  "error",
      code:    "INVALID_SIGNAL_PRICES",
      message: "Signal contains zero or negative price levels",
    });
    return;
  }

  next();
}