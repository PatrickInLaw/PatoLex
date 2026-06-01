/**
 * PatoLex 1850 Lineage Query + Benchmark JSON Update
 *
 * Runs the recursive CTE lineage query on the already-ingested 1850 data
 * and appends the results to the benchmark JSON.
 *
 * Usage (from repo root):
 *   npx tsx scripts/ingest/query-1850-lineage.ts
 */

import { appendFileSync, readFileSync, writeFileSync } from "fs";
import postgres from "postgres";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });

const SCRATCH_HIST =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-historical";
const BENCHMARK_OUTPUT = SCRATCH_HIST + "\\ingest_benchmark.json";
const LOG_FILE =
  "docs\\80_PROJECT_HISTORY\\run-logs\\ingest-benchmark-run.log";

function logRun(phase: string, desc: string, status: "OK" | "WARN" | "FAIL") {
  const d = new Date(Date.now() - 7 * 3600 * 1000);
  const ts = d.toISOString().replace("T", " ").slice(0, 16) + " PT";
  const line = `[${ts}] ${phase} | ${desc} | ${status}\n`;
  process.stderr.write(line);
  try { appendFileSync(LOG_FILE, line, "utf-8"); } catch { /* non-fatal */ }
}

function now(): bigint { return process.hrtime.bigint(); }
function ms(start: bigint): number { return Number(process.hrtime.bigint() - start) / 1e6; }

async function main() {
  console.log("PatoLex 1850 Lineage CTE Query");
  console.log("==============================");

  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set — check .env.local");

  const sql = postgres(url, { max: 3 });

  try {
    // Find the Stats. 1850 ch. 23 provision (already ingested)
    const [ch23Row] = await sql`
      SELECT id, current_designation FROM provision WHERE current_designation = 'Stats. 1850 ch. 23' LIMIT 1
    `;
    if (!ch23Row) throw new Error("Stats. 1850 ch. 23 provision not found — run ingest-1850-acts.ts first");
    const predProvId = BigInt(ch23Row.id);
    console.log(`\nStarting provision: ${ch23Row.current_designation} (id=${predProvId})`);

    // Verify lineage edge exists
    const [edgeCheck] = await sql`
      SELECT id, edge_type::text, note FROM lineage_edge WHERE predecessor_provision_id = ${predProvId} LIMIT 1
    `;
    if (!edgeCheck) throw new Error("No lineage_edge found for this provision");
    console.log(`Lineage edge id=${edgeCheck.id} type=${edgeCheck.edge_type}`);
    console.log(`Note: ${edgeCheck.note}`);

    // ---- Recursive CTE: full ancestor+descendant chain ----
    console.log("\n=== RECURSIVE CTE LINEAGE QUERY ===");
    const tCte = now();

    const lineageRows = await sql`
      WITH RECURSIVE
      descendants AS (
        SELECT
          p.id             AS provision_id,
          p.current_designation,
          p.unit_type::text,
          NULL::bigint     AS via_edge_id,
          NULL::text       AS edge_type,
          NULL::text       AS linked_from,
          'start'          AS direction,
          0                AS depth
        FROM provision p
        WHERE p.id = ${predProvId}

        UNION ALL

        SELECT
          succ.id,
          succ.current_designation,
          succ.unit_type::text,
          le.id,
          le.edge_type::text,
          d.current_designation,
          'descendant',
          d.depth + 1
        FROM descendants d
        JOIN lineage_edge le ON le.predecessor_provision_id = d.provision_id
        JOIN provision succ ON succ.id = le.successor_provision_id
        WHERE d.depth < 10
      ),
      ancestors AS (
        SELECT
          p.id             AS provision_id,
          p.current_designation,
          p.unit_type::text,
          NULL::bigint     AS via_edge_id,
          NULL::text       AS edge_type,
          NULL::text       AS linked_from,
          'start'          AS direction,
          0                AS depth
        FROM provision p
        WHERE p.id = ${predProvId}

        UNION ALL

        SELECT
          pred.id,
          pred.current_designation,
          pred.unit_type::text,
          le.id,
          le.edge_type::text,
          a.current_designation,
          'ancestor',
          a.depth + 1
        FROM ancestors a
        JOIN lineage_edge le ON le.successor_provision_id = a.provision_id
        JOIN provision pred ON pred.id = le.predecessor_provision_id
        WHERE a.depth < 10
      )
      SELECT provision_id, current_designation, unit_type, via_edge_id, edge_type, linked_from, direction, depth
      FROM descendants
      UNION
      SELECT provision_id, current_designation, unit_type, via_edge_id, edge_type, linked_from, direction, depth
      FROM ancestors WHERE direction = 'ancestor'
      ORDER BY direction, depth, provision_id
    `;

    const cteMs = ms(tCte);

    console.log(`\n${lineageRows.length} row(s) returned in ${cteMs.toFixed(1)}ms`);
    console.log("\nprovision_id | current_designation              | unit_type     | edge_type       | linked_from                      | direction  | depth");
    console.log("-".repeat(140));
    for (const r of lineageRows) {
      console.log(
        String(r.provision_id).padEnd(13) + "| " +
        String(r.current_designation ?? "").slice(0, 33).padEnd(33) + " | " +
        String(r.unit_type ?? "").padEnd(13) + " | " +
        String(r.edge_type ?? "").padEnd(16) + "| " +
        String(r.linked_from ?? "").slice(0, 33).padEnd(33) + " | " +
        String(r.direction).padEnd(11) + "| " +
        String(r.depth)
      );
    }

    // ---- Final DB counts ----
    console.log("\n=== FINAL DB COUNTS ===");
    const unitCounts = await sql`
      SELECT unit_type::text, count(*)::int as cnt
      FROM provision GROUP BY unit_type ORDER BY unit_type
    `;
    console.log("unit_type     | count");
    console.log("-".repeat(30));
    for (const r of unitCounts) {
      console.log(`${String(r.unit_type).padEnd(14)}| ${r.cnt}`);
    }
    const [ceTot] = await sql`SELECT count(*)::int as cnt FROM change_event`;
    const [edgeTot] = await sql`SELECT count(*)::int as cnt FROM lineage_edge`;
    console.log(`\nchange_events total:  ${ceTot.cnt}`);
    console.log(`lineage_edges total:  ${edgeTot.cnt}`);

    // ---- GiST constraint check ----
    // If any provision_version ranges overlap for same provision, the GiST would have fired
    // during insert. We can confirm by checking no violations exist now.
    console.log("\n=== GIST EXCLUSION CONSTRAINT CHECK ===");
    const gistCheck = await sql`
      SELECT pv1.provision_id, count(*) as overlapping_pairs
      FROM provision_version pv1
      JOIN provision_version pv2
        ON pv1.provision_id = pv2.provision_id
        AND pv1.id < pv2.id
        AND pv1.valid_range && pv2.valid_range
      GROUP BY pv1.provision_id
      HAVING count(*) > 0
    `;
    if (gistCheck.length === 0) {
      console.log("OK — no overlapping provision_version ranges detected");
    } else {
      console.log(`WARN — ${gistCheck.length} provision(s) have overlapping ranges (GiST should have prevented this)`);
      for (const r of gistCheck) {
        console.log(`  provision_id=${r.provision_id} overlapping_pairs=${r.overlapping_pairs}`);
      }
    }

    // ---- Per-stage timing from this run (stages already recorded in prior run) ----
    // Read existing benchmark and update the ingest_1850 section with lineage results
    const existing = JSON.parse(readFileSync(BENCHMARK_OUTPUT, "utf-8"));
    if (existing.ingest_1850) {
      existing.ingest_1850.lineage_query = {
        wall_ms: parseFloat(cteMs.toFixed(2)),
        rows_returned: lineageRows.length,
        query_type: "recursive_cte_bidirectional",
        result: lineageRows.map((r) => ({
          provision_id: Number(r.provision_id),
          current_designation: r.current_designation,
          unit_type: r.unit_type,
          via_edge_id: r.via_edge_id ? Number(r.via_edge_id) : null,
          edge_type: r.edge_type ?? null,
          linked_from: r.linked_from ?? null,
          direction: r.direction,
          depth: r.depth,
        })),
      };
      existing.ingest_1850.final_db_counts = {
        provision_by_unit_type: Object.fromEntries(unitCounts.map((r: {unit_type: string, cnt: number}) => [r.unit_type, r.cnt])),
        change_events_total: ceTot.cnt,
        lineage_edges_total: edgeTot.cnt,
      };
      existing.ingest_1850.gist_constraint_violations = gistCheck.length;
    } else {
      console.warn("WARN: ingest_1850 section not found in benchmark JSON — was the main ingest script run?");
    }
    writeFileSync(BENCHMARK_OUTPUT, JSON.stringify(existing, null, 2), "utf-8");
    console.log(`\nBenchmark JSON updated: ${BENCHMARK_OUTPUT}`);

    logRun("1850-CTE-QUERY", `rows=${lineageRows.length} cte_ms=${cteMs.toFixed(0)} gist_violations=${gistCheck.length}`, "OK");
    console.log("\nDone.");

  } finally {
    await sql.end();
  }
}

main().catch((err) => {
  console.error("FATAL:", err);
  logRun("1850-CTE-FAIL", String(err), "FAIL");
  process.exit(1);
});
