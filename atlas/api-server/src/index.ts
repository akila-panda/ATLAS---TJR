/**
 * api-server/src/index.ts
 * ATLAS API Server — Express + Socket.io entry point.
 * Bridges MT5 EA ↔ Python signal engine ↔ React dashboard.
 */
import * as http    from "http";
import express      from "express";
import helmet       from "helmet";
import cors         from "cors";

import { PORT, FRONTEND_ORIGIN, NODE_ENV } from "./config";
import { init as initPostgres, close as closePostgres } from "./db/postgres";
import { initRedis, closeRedis, getMode, getRiskState } from "./services/redisService";
import { initBroadcaster }  from "./websocket/broadcaster";
import { mt5Router }        from "./routes/mt5";
import { signalRouter }     from "./routes/signal";
import { controlRouter }    from "./routes/control";
import { tradesRouter }     from "./routes/trades";
import { journalRouter }    from "./routes/journal";

const app    = express();
const server = http.createServer(app);

// ─── Middleware ───────────────────────────────────────────────────────────────

app.use(helmet({
  // Allow WebSocket upgrades through helmet
  contentSecurityPolicy: false,
}));

app.use(cors({
  origin:  FRONTEND_ORIGIN,
  methods: ["GET", "POST", "PUT", "DELETE"],
  allowedHeaders: ["Content-Type", "x-atlas-key"],
}));

// 2MB limit covers the largest candle batch (500 candles × ~100 bytes)
app.use(express.json({ limit: "2mb" }));

// ─── Routes ───────────────────────────────────────────────────────────────────

// MT5 EA routes — no auth (EA cannot carry API keys on Mac via Wine)
app.use(mt5Router);

// Signal polling — no auth, riskGuard applied per-route
app.use(signalRouter);

// Dashboard control routes — auth required
app.use(controlRouter);

// Trade data routes — auth required
app.use(tradesRouter);

// Journal routes — auth required
app.use(journalRouter);

// ─── System status ────────────────────────────────────────────────────────────

app.get("/api/status", async (_req, res) => {
  const [mode, risk] = await Promise.all([getMode(), getRiskState()]);
  res.status(200).json({
    status: "ok",
    data: {
      mode,
      risk_state:   risk,
      uptime_sec:   Math.floor(process.uptime()),
      environment:  NODE_ENV,
      version:      "1.0.0",
    },
  });
});

app.get("/health", (_req, res) => {
  res.status(200).json({ status: "ok" });
});

// ─── 404 handler ──────────────────────────────────────────────────────────────

app.use((_req, res) => {
  res.status(404).json({ status: "error", code: "NOT_FOUND", message: "Route not found" });
});

// ─── Global error handler ─────────────────────────────────────────────────────

app.use((
  err:  Error,
  _req: express.Request,
  res:  express.Response,
  _next: express.NextFunction
) => {
  console.error("[server] unhandled error:", err.message);
  res.status(500).json({
    status:  "error",
    code:    "INTERNAL_ERROR",
    message: NODE_ENV === "development" ? err.message : "Internal server error",
  });
});

// ─── Startup ──────────────────────────────────────────────────────────────────

async function start(): Promise<void> {
  try {
    // Init Redis first — signal delivery depends on it
    initRedis();
    console.log("[server] Redis initialised");

    // Init PostgreSQL and run migrations
    await initPostgres();
    console.log("[server] PostgreSQL initialised");

    // Init Socket.io broadcaster
    initBroadcaster(server);
    console.log("[server] WebSocket broadcaster initialised");

    // Start HTTP server
    server.listen(PORT, () => {
      console.log(`[server] ATLAS API Server running on port ${PORT}`);
      console.log(`[server] Mode: ${NODE_ENV} | Origin: ${FRONTEND_ORIGIN}`);
    });
  } catch (err) {
    console.error("[server] startup failed:", err instanceof Error ? err.message : err);
    process.exit(1);
  }
}

// ─── Graceful shutdown ────────────────────────────────────────────────────────

async function shutdown(signal: string): Promise<void> {
  console.log(`[server] ${signal} received — shutting down gracefully`);

  server.close(async () => {
    console.log("[server] HTTP server closed");
    await Promise.all([closePostgres(), closeRedis()]);
    console.log("[server] shutdown complete");
    process.exit(0);
  });

  // Force exit after 10 seconds if graceful shutdown stalls
  setTimeout(() => {
    console.error("[server] forced shutdown after timeout");
    process.exit(1);
  }, 10_000);
}

process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT",  () => void shutdown("SIGINT"));

void start();