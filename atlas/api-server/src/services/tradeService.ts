/**
 * api-server/src/services/tradeService.ts
 * PostgreSQL trade operations and journal statistics.
 * Implements Section 9.3 statistical thresholds.
 */
import { query } from "../db/postgres";
import type {
  Trade,
  TradeEvent,
  JournalStats,
  TradeFilters,
  PaginationParams,
} from "../types";

// ─── Trade CRUD ───────────────────────────────────────────────────────────────

export async function createTrade(params: {
  id:                   string;
  session_id?:          string | null;
  direction:            string;
  entry_type:           string;
  entry_price:          number;
  sl_price:             number;
  tp1_price:            number;
  tp2_price:            number;
  tp3_price:            number;
  lot_size:             number;
  risk_usd:             number;
  rr_ratio:             number;
  sl_pips:              number;
  confluence_score:     number;
  setup_grade:          string;
  asia_high:            number;
  asia_low:             number;
  asia_range_pips:      number;
  sweep_direction:      string;
  sweep_extension_pips: number;
  account_balance:      number;
  decision_state:       Record<string, unknown>;
}): Promise<Trade> {
  const result = await query<Trade>(
    `INSERT INTO trades (
       id, session_id, direction, entry_type,
       entry_price, sl_price, tp1_price, tp2_price, tp3_price,
       lot_size, risk_usd, rr_ratio, sl_pips,
       confluence_score, setup_grade,
       asia_high, asia_low, asia_range_pips,
       sweep_direction, sweep_extension_pips,
       account_balance, decision_state,
       status, created_at
     ) VALUES (
       $1,$2,$3,$4,
       $5,$6,$7,$8,$9,
       $10,$11,$12,$13,
       $14,$15,
       $16,$17,$18,
       $19,$20,
       $21,$22,
       'PENDING', NOW()
     )
     ON CONFLICT (id) DO NOTHING
     RETURNING *`,
    [
      params.id, params.session_id ?? null, params.direction, params.entry_type,
      params.entry_price, params.sl_price, params.tp1_price, params.tp2_price, params.tp3_price,
      params.lot_size, params.risk_usd, params.rr_ratio, params.sl_pips,
      params.confluence_score, params.setup_grade,
      params.asia_high, params.asia_low, params.asia_range_pips,
      params.sweep_direction, params.sweep_extension_pips,
      params.account_balance, JSON.stringify(params.decision_state),
    ]
  );
  return result.rows[0]!;
}

export async function updateTradeStatus(
  id:      string,
  status:  string,
  ticket?: number,
): Promise<void> {
  if (ticket !== undefined) {
    await query(
      `UPDATE trades SET status = $2, mt5_ticket = $3, opened_at = NOW()
       WHERE id = $1`,
      [id, status, ticket]
    );
  } else {
    await query(
      `UPDATE trades SET status = $2 WHERE id = $1`,
      [id, status]
    );
  }
}

export async function updateTradeClose(
  id:          string,
  outcome:     string,
  pnl:         number,
  closeReason: string,
): Promise<void> {
  await query(
    `UPDATE trades
     SET status = $2, outcome = $2, pnl = $3,
         close_reason = $4, closed_at = NOW()
     WHERE id = $1`,
    [id, outcome, pnl, closeReason]
  );
}

// ─── Trade Events ─────────────────────────────────────────────────────────────

export async function insertTradeEvent(
  tradeId:   string,
  eventType: string,
  price:     number | null,
  pips:      number | null,
  meta:      Record<string, unknown> | null,
): Promise<void> {
  await query(
    `INSERT INTO trade_events (trade_id, event_type, price, pips, metadata, timestamp)
     VALUES ($1, $2, $3, $4, $5, NOW())`,
    [tradeId, eventType, price, pips, meta ? JSON.stringify(meta) : null]
  );
}

export async function getTradeEvents(tradeId: string): Promise<TradeEvent[]> {
  const result = await query<TradeEvent>(
    `SELECT * FROM trade_events WHERE trade_id = $1 ORDER BY timestamp ASC`,
    [tradeId]
  );
  return result.rows;
}

// ─── Trade Queries ────────────────────────────────────────────────────────────

export async function getTrades(
  pagination: PaginationParams,
  filters:    TradeFilters = {}
): Promise<{ trades: Trade[]; total: number }> {
  const conditions: string[] = [];
  const params: unknown[]   = [];
  let   paramIdx = 1;

  if (filters.status) {
    conditions.push(`status = $${paramIdx++}`);
    params.push(filters.status);
  }
  if (filters.direction) {
    conditions.push(`direction = $${paramIdx++}`);
    params.push(filters.direction);
  }
  if (filters.grade) {
    conditions.push(`setup_grade = $${paramIdx++}`);
    params.push(filters.grade);
  }
  if (filters.from) {
    conditions.push(`created_at >= $${paramIdx++}`);
    params.push(filters.from);
  }
  if (filters.to) {
    conditions.push(`created_at <= $${paramIdx++}`);
    params.push(filters.to);
  }

  const where = conditions.length > 0
    ? `WHERE ${conditions.join(" AND ")}`
    : "";

  // Count
  const countResult = await query<{ count: string }>(
    `SELECT COUNT(*) as count FROM trades ${where}`,
    params
  );
  const total = parseInt(countResult.rows[0]?.count ?? "0", 10);

  // Data
  const dataParams = [...params, pagination.limit, pagination.offset];
  const dataResult = await query<Trade>(
    `SELECT * FROM trades ${where}
     ORDER BY created_at DESC
     LIMIT $${paramIdx} OFFSET $${paramIdx + 1}`,
    dataParams
  );

  return { trades: dataResult.rows, total };
}

export async function getTradeById(
  id: string
): Promise<(Trade & { events: TradeEvent[] }) | null> {
  const tradeResult = await query<Trade>(
    `SELECT * FROM trades WHERE id = $1`,
    [id]
  );
  if (tradeResult.rows.length === 0) return null;

  const trade  = tradeResult.rows[0]!;
  const events = await getTradeEvents(id);
  return { ...trade, events };
}

// ─── Journal Statistics (Section 9.3) ────────────────────────────────────────

export async function getJournalStats(): Promise<JournalStats> {
  /**
   * Computes Section 9.3 edge metrics from the last 50 closed trades.
   * Minimum thresholds:
   *   win_rate_tp1 >= 55%, win_rate_tp2 >= 40%
   *   avg_rr >= 1.8, expectancy >= +0.3R
   *   profit_factor >= 1.4
   */
  const result = await query<{
    total:            string;
    tp1_wins:         string;
    tp2_wins:         string;
    gross_profit:     string | null;
    gross_loss:       string | null;
    avg_rr:           string | null;
    total_pnl:        string | null;
  }>(
    `WITH recent AS (
       SELECT *
       FROM trades
       WHERE status NOT IN ('PENDING', 'OPEN', 'ERROR')
       ORDER BY closed_at DESC
       LIMIT 50
     )
     SELECT
       COUNT(*)                                              AS total,
       COUNT(*) FILTER (WHERE outcome IN ('TP1','TP2','TP3')) AS tp1_wins,
       COUNT(*) FILTER (WHERE outcome IN ('TP2','TP3'))       AS tp2_wins,
       SUM(pnl)  FILTER (WHERE pnl > 0)                      AS gross_profit,
       ABS(SUM(pnl) FILTER (WHERE pnl < 0))                  AS gross_loss,
       AVG(rr_ratio) FILTER (WHERE outcome IN ('TP1','TP2','TP3')) AS avg_rr,
       SUM(pnl)                                              AS total_pnl
     FROM recent`
  );

  const row = result.rows[0];
  if (!row) {
    return {
      total_trades: 0, winning_trades: 0, losing_trades: 0,
      win_rate_tp1: 0, win_rate_tp2: 0, avg_rr: 0,
      expectancy: 0, profit_factor: 0, max_consecutive_losses: 0,
      total_pnl_usd: 0, sample_size: 0,
    };
  }

  const total      = parseInt(row.total, 10);
  const tp1Wins    = parseInt(row.tp1_wins, 10);
  const tp2Wins    = parseInt(row.tp2_wins, 10);
  const grossProfit = parseFloat(row.gross_profit ?? "0");
  const grossLoss   = parseFloat(row.gross_loss   ?? "0");
  const avgRR       = parseFloat(row.avg_rr       ?? "0");
  const totalPnl    = parseFloat(row.total_pnl    ?? "0");

  const winRate1 = total > 0 ? tp1Wins / total : 0;
  const winRate2 = total > 0 ? tp2Wins / total : 0;

  // Expectancy = win_rate * avg_rr - (1 - win_rate) * 1
  const expectancy = winRate1 * avgRR - (1 - winRate1) * 1.0;

  // Profit factor = gross_profit / gross_loss
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

  // Max consecutive losses from trade_events ordered by close date
  const clResult = await query<{ outcome: string }>(
    `SELECT outcome FROM trades
     WHERE status NOT IN ('PENDING','OPEN','ERROR')
     ORDER BY closed_at DESC LIMIT 50`
  );
  const maxConsec = _calcMaxConsecutiveLosses(clResult.rows.map((r) => r.outcome));

  return {
    total_trades:          total,
    winning_trades:        tp1Wins,
    losing_trades:         total - tp1Wins,
    win_rate_tp1:          Math.round(winRate1 * 1000) / 10,
    win_rate_tp2:          Math.round(winRate2 * 1000) / 10,
    avg_rr:                Math.round(avgRR * 100) / 100,
    expectancy:            Math.round(expectancy * 1000) / 1000,
    profit_factor:         Math.round(profitFactor * 100) / 100,
    max_consecutive_losses: maxConsec,
    total_pnl_usd:         Math.round(totalPnl * 100) / 100,
    sample_size:           total,
  };
}

function _calcMaxConsecutiveLosses(outcomes: string[]): number {
  let max = 0;
  let cur = 0;
  for (const o of outcomes) {
    if (o === "SL") {
      cur++;
      max = Math.max(max, cur);
    } else {
      cur = 0;
    }
  }
  return max;
}