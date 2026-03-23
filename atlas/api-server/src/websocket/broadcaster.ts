/**
 * api-server/src/websocket/broadcaster.ts
 * Socket.io broadcaster — real-time updates to dashboard clients.
 * Subscribes to Redis pub/sub channels published by Python signal engine.
 */
import { Server as HttpServer }   from "http";
import { Server as SocketServer } from "socket.io";
import {
  getMode,
  getRiskState,
  createSubscriber,
}                                  from "../services/redisService";
import { FRONTEND_ORIGIN }         from "../config";

let _io: SocketServer | null = null;

export function getIo(): SocketServer {
  if (!_io) throw new Error("Socket.io not initialised — call initBroadcaster() first");
  return _io;
}

/**
 * Initialise Socket.io on the shared HTTP server.
 * Sets up connection handlers and Redis pub/sub bridge.
 */
export function initBroadcaster(httpServer: HttpServer): SocketServer {
  _io = new SocketServer(httpServer, {
    cors: {
      origin:  FRONTEND_ORIGIN,
      methods: ["GET", "POST"],
    },
    transports: ["websocket", "polling"],
  });

  // ── New client connection ──────────────────────────────────────────────────
  _io.on("connection", async (socket) => {
    console.log(`[ws] client connected: ${socket.id}`);

    // Send current system state to newly connected client
    try {
      const [mode, risk] = await Promise.all([getMode(), getRiskState()]);
      socket.emit("status", {
        mode,
        risk,
        uptime: process.uptime(),
      });
    } catch (err) {
      console.error("[ws] failed to send initial state:", err instanceof Error ? err.message : err);
    }

    socket.on("disconnect", () => {
      console.log(`[ws] client disconnected: ${socket.id}`);
    });
  });

  // ── Redis pub/sub bridge ───────────────────────────────────────────────────
  // Subscribe to channels published by Python signal engine.
  // Broadcasts received messages to all connected Socket.io clients.
  _subscribeToRedisChannels();

  return _io;
}

function _subscribeToRedisChannels(): void {
  const subscriber = createSubscriber();

  const channels = [
    "atlas:ack",       // trade lifecycle events from Python
    "atlas:risk",      // risk state updates
    "atlas:signals",   // new signals generated
    "atlas:session",   // session state updates
  ];

  subscriber.subscribe(...channels, (err, count) => {
    if (err) {
      console.error("[ws] Redis subscribe error:", err.message);
      return;
    }
    console.log(`[ws] subscribed to ${count} Redis channels`);
  });

  subscriber.on("message", (channel: string, message: string) => {
    const io = _io;
    if (!io) return;

    try {
      const data = JSON.parse(message) as Record<string, unknown>;

      switch (channel) {
        case "atlas:ack":
          // Re-emit as appropriate trade event
          if (data["type"] === "OPEN_ACK") {
            io.emit("trade_opened", data);
          } else {
            io.emit("trade_event", data);
          }
          break;

        case "atlas:risk":
          io.emit("risk_update", data);
          break;

        case "atlas:signals":
          // signal_manual vs live signal
          if (data["mode"] === "MANUAL") {
            io.emit("signal_manual", data);
          } else {
            io.emit("signal", data);
          }
          break;

        case "atlas:session":
          io.emit("status", data);
          break;

        default:
          // Forward under the channel name as-is
          io.emit(channel.replace("atlas:", ""), data);
      }
    } catch {
      // Non-JSON message — forward as raw string under channel name
      _io?.emit(channel.replace("atlas:", ""), { raw: message });
    }
  });

  subscriber.on("error", (err: Error) => {
    console.error("[ws] subscriber error:", err.message);
  });
}