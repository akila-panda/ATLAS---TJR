/**
 * frontend/src/lib/formatters.ts
 * ATLAS formatting utilities — used throughout all components.
 */

/** Format any date as EST time string "HH:MM:SS" */
export function formatEST(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    timeZone:     "America/New_York",
    hour:         "2-digit",
    minute:       "2-digit",
    second:       "2-digit",
    hour12:       false,
  });
}

/** Format date portion in EST "YYYY-MM-DD" */
export function formatDateEST(date: Date): string {
  return date.toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });
}

/** Format price to 5 decimal places */
export function formatPrice(n: number): string {
  return n.toFixed(5);
}

/** Format pips value to 1 decimal */
export function formatPips(n: number): string {
  return `${n.toFixed(1)} pips`;
}

/** Format P&L with sign and $ symbol */
export function formatPnL(n: number): string {
  const abs = Math.abs(n).toFixed(2);
  return n >= 0 ? `+$${abs}` : `-$${abs}`;
}

/** Format percentage to 1 decimal */
export function formatPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

/** Format R:R ratio to 2 decimals */
export function formatRR(n: number): string {
  return `${n.toFixed(2)}R`;
}

/**
 * Map setup grade to Tailwind color class for text.
 * Uses atlas color tokens from tailwind.config.ts.
 */
export function gradeColor(grade: string): string {
  switch (grade) {
    case "A+": return "text-atlas-long";
    case "A":  return "text-atlas-accent";
    case "B":  return "text-atlas-neutral";
    case "C":  return "text-atlas-short";
    default:   return "text-atlas-text-dim";
  }
}

/** Map setup grade to Tailwind border color class */
export function gradeBorderColor(grade: string): string {
  switch (grade) {
    case "A+": return "border-atlas-long";
    case "A":  return "border-atlas-accent";
    case "B":  return "border-atlas-neutral";
    case "C":  return "border-atlas-short";
    default:   return "border-atlas-border";
  }
}

/** Get current EST hour (0–23) */
export function getCurrentESTHour(): number {
  const now = new Date();
  const estStr = now.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour:     "numeric",
    hour12:   false,
  });
  return parseInt(estStr, 10);
}

/**
 * LKZ status based on current EST time.
 * 02:00–05:00 EST = ACTIVE, 05:00–20:00 = CLOSED, 20:00–02:00 = WAITING
 */
export function getLKZStatus(): "WAITING" | "ACTIVE" | "CLOSED" {
  const h = getCurrentESTHour();
  if (h >= 2 && h < 5)  return "ACTIVE";
  if (h >= 5 && h < 20) return "CLOSED";
  return "WAITING";
}

/** Truncate long strings with ellipsis */
export function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}