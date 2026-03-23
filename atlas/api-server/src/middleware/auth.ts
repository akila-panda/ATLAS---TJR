/**
 * api-server/src/middleware/auth.ts
 * API key authentication middleware.
 * Applied to all POST routes except /mt5/* (EA does not carry API keys).
 */
import { Request, Response, NextFunction } from "express";
import { ATLAS_API_KEY } from "../config";

export function auth(
  req:  Request,
  res:  Response,
  next: NextFunction
): void {
  const key = req.headers["x-atlas-key"];

  if (!key || key !== ATLAS_API_KEY) {
    res.status(401).json({
      status:  "error",
      code:    "UNAUTHORIZED",
      message: "Missing or invalid x-atlas-key header",
    });
    return;
  }

  next();
}