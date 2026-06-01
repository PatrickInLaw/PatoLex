/**
 * PatoLex DB client — lazy postgres-js + Drizzle wrapper.
 *
 * The connection and Drizzle instance are initialized on first use (lazy
 * singleton via getDb() / getSql()). This means importing this module —
 * including importing schema types — does NOT require DATABASE_URL to be
 * present at module load time. CI type-checks and schema-only imports work
 * without a live database.
 *
 * Connection URLs:
 * - Use the DIRECT URL (port 5432) for: drizzle-kit migrate, the C# pipeline,
 *   and any Node.js script that runs DDL or long transactions.
 * - Use the PGBOUNCER URL (port 6543) for Vercel serverless functions (import
 *   from a separate pooled-client module in that case).
 *
 * DATABASE_URL must be set in .env.local (local dev) or as an environment
 * variable in the deployment environment. Never hardcode connection strings.
 *
 * Example .env.local:
 *   DATABASE_URL=postgres://postgres:password@db.nqigiiyurwlmruexircz.supabase.co:5432/postgres
 *
 * See .env.example for the format.
 */

import dotenv from "dotenv";
import { drizzle } from "drizzle-orm/postgres-js";
import type { PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema/index.js";

type Schema = typeof schema;

let _sql: postgres.Sql | null = null;
let _db: PostgresJsDatabase<Schema> | null = null;

function getConnectionString(): string {
  // Load .env.local if DATABASE_URL is not already set (covers tsx scripts and
  // other Node.js runtimes that don't pre-load the env file).
  if (!process.env.DATABASE_URL) {
    dotenv.config({ path: ".env.local" });
  }
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL environment variable is not set. " +
        "Copy .env.example to .env.local and fill in the direct PostgreSQL URL (port 5432)."
    );
  }
  return url;
}

/**
 * Lazy singleton: raw postgres-js connection pool.
 * Initialized on first call. Use in scripts that need direct SQL access
 * (e.g. migrations that include hand-written DDL not expressible in Drizzle).
 *
 * The connection string is read from DATABASE_URL at first call — not at
 * module import time — so importing this module in CI does not require a DB.
 */
export function getSql(): postgres.Sql {
  if (!_sql) {
    _sql = postgres(getConnectionString(), {
      // Max connections. Keep low for serverless; higher is fine for pipeline scripts.
      max: 10,
    });
  }
  return _sql;
}

/**
 * Lazy singleton: Drizzle ORM instance with full schema types.
 * Initialized on first call. Use in service-layer code (src/server/) and
 * pipeline scripts.
 *
 * Usage:
 *   import { getDb } from "@/lib/db/client";
 *   const provisions = await getDb().select().from(schema.provision).limit(10);
 *
 * DATABASE_URL is read on first call, not at import time.
 */
export function getDb(): PostgresJsDatabase<Schema> {
  if (!_db) {
    _db = drizzle(getSql(), { schema });
  }
  return _db;
}
