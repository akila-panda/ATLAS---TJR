/**
 * api-server/src/db/postgres.ts
 * PostgreSQL connection pool and migration runner.
 * Uses the `pg` library with full TypeScript generics.
 */
import { Pool, PoolClient, QueryResult, QueryResultRow } from "pg";
import * as fs from "fs";
import * as path from "path";
import { DATABASE_URL } from "../config";

let _pool: Pool | null = null;

export function getPool(): Pool {
  if (!_pool) {
    throw new Error("PostgreSQL pool not initialised — call init() first");
  }
  return _pool;
}

/**
 * Initialise the connection pool and run migrations.
 * Called once on server startup.
 */
export async function init(): Promise<void> {
  _pool = new Pool({
    connectionString: DATABASE_URL,
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });

  // Verify connectivity
  const client = await _pool.connect();
  try {
    await client.query("SELECT 1");
    console.log("[postgres] connected");
    await runMigrations(client);
  } finally {
    client.release();
  }
}

/**
 * Execute a parameterised query against the pool.
 * Generic T allows typed row returns.
 */
export async function query<T extends QueryResultRow = QueryResultRow>(
  sql:    string,
  params: unknown[] = []
): Promise<QueryResult<T>> {
  return getPool().query<T>(sql, params);
}

/**
 * Run 001_initial.sql migration.
 * Uses IF NOT EXISTS guards so it is safe to re-run on every startup.
 */
async function runMigrations(client: PoolClient): Promise<void> {
  const migrationPath = path.join(__dirname, "migrations", "001_initial.sql");

  if (!fs.existsSync(migrationPath)) {
    console.warn("[postgres] migration file not found:", migrationPath);
    return;
  }

  const sql = fs.readFileSync(migrationPath, "utf-8");

  try {
    await client.query(sql);
    console.log("[postgres] migration 001_initial applied");
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    // Re-throw migration errors — they indicate a schema problem that must be fixed
    throw new Error(`[postgres] migration failed: ${msg}`);
  }
}

export async function close(): Promise<void> {
  if (_pool) {
    await _pool.end();
    _pool = null;
    console.log("[postgres] pool closed");
  }
}