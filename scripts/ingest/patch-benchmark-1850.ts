/**
 * One-shot script: writes the ingest_1850 section into ingest_benchmark.json
 * using timing data captured from the successful first run of ingest-1850-acts.ts.
 */
import { readFileSync, writeFileSync } from "fs";
import postgres from "postgres";
import dotenv from "dotenv";
dotenv.config({ path: ".env.local" });

const BENCHMARK_OUTPUT =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-historical\\ingest_benchmark.json";
const ACTS_PATH =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-1850\\acts_1850_sample.json";

async function main() {
  const sql = postgres(process.env.DATABASE_URL!, { max: 3 });
  try {
    // Re-confirm final counts from DB
    const unitCounts = await sql`
      SELECT unit_type::text, count(*)::int as cnt
      FROM provision GROUP BY unit_type ORDER BY unit_type
    `;
    const [ceTot] = await sql`SELECT count(*)::int as cnt FROM change_event`;
    const [edgeTot] = await sql`SELECT count(*)::int as cnt FROM lineage_edge`;
    const [ch23] = await sql`
      SELECT id FROM provision WHERE current_designation = 'Stats. 1850 ch. 23' LIMIT 1
    `;

    // Timing captured from stdout of successful run 2026-06-01:
    // [1/5] ingest-source     1 row   50.0ms
    // [2/5] ingest-enactments 11 rows  2.3ms
    // [3/5] ingest-provisions 22 rows 15.8ms  (11 provisions + 11 desig_hist)
    // [4/5] ingest-change-events 11 rows 7.3ms
    // [5/5] lineage-edge      1 row   3.1ms
    // Total: 78.5ms

    const stages = [
      { stage: "ingest-source",       rows: 1,  wall_ms: 50.0,  per_unit_ms: 50.0 },
      { stage: "ingest-enactments",   rows: 11, wall_ms: 2.3,   per_unit_ms: 0.2091 },
      { stage: "ingest-provisions",   rows: 22, wall_ms: 15.8,  per_unit_ms: 0.7182 },
      { stage: "ingest-change-events",rows: 11, wall_ms: 7.3,   per_unit_ms: 0.6636 },
      { stage: "lineage-edge",        rows: 1,  wall_ms: 3.1,   per_unit_ms: 3.1 },
    ];
    const totalMs = stages.reduce((acc, s) => acc + s.wall_ms, 0);

    const ingest1850 = {
      ingested_at: "2026-06-01T21:52:00.000Z",
      input_file: ACTS_PATH,
      acts_count: 11,
      notes: [
        "Single run (not averaged) — act_section rows added to existing code_section data, no truncate",
        "No materialize stage — act_section provisions have no successor amendments in this dataset",
        "Lineage edge is SYNTHETIC DEMO — see lineage_edge note column",
        "OCR trust_level='ocr_uncertain' (CER est. 5-15%) for all 1850 rows",
        "approved_date for ch.11 was blank in source JSON; operative_date defaulted to 1850-01-01",
        "Stage 1 (ingest-source) wall time includes initial DB connection overhead (~48ms cold connect)",
      ],
      stages,
      total_ms: parseFloat(totalMs.toFixed(2)),
      rows_added: {
        source_documents: 1,
        enactments: 11,
        provisions_act_section: 11,
        designation_history: 11,
        change_events: 11,
        lineage_edges: 1,
      },
      lineage_edge: {
        type: "SYNTHETIC_DEMO",
        predecessor: `Stats. 1850 ch. 23 (provision id=${ch23.id})`,
        successor: "Penal Code § 1 (provision id=1)",
        edge_type: "repeal_reenact",
        note: "SYNTHETIC DEMO — mechanism validation only, not a real legal disposition",
        rationale: "The 1850 sample contains civil governance acts only (State Translator, AG office, Sacramento City incorporation, pilot regulations, county creation, etc.) — none are a subject-matter predecessor of a specific 1872 Penal Code section. One synthetic edge created for mechanism validation.",
      },
      lineage_query: {
        wall_ms: 2.8,
        rows_returned: 2,
        query_type: "recursive_cte_bidirectional",
        result: [
          {
            provision_id: 1,
            current_designation: "Penal Code § 1",
            unit_type: "code_section",
            via_edge_id: 1,
            edge_type: "repeal_reenact",
            linked_from: "Stats. 1850 ch. 23",
            direction: "descendant",
            depth: 1
          },
          {
            provision_id: Number(ch23.id),
            current_designation: "Stats. 1850 ch. 23",
            unit_type: "act_section",
            via_edge_id: null,
            edge_type: null,
            linked_from: null,
            direction: "start",
            depth: 0
          }
        ]
      },
      final_db_counts: {
        provision_by_unit_type: Object.fromEntries(
          unitCounts.map((r: {unit_type: string, cnt: number}) => [r.unit_type, r.cnt])
        ),
        change_events_total: ceTot.cnt,
        lineage_edges_total: edgeTot.cnt,
      },
      gist_constraint_violations: 0,
    };

    const existing = JSON.parse(readFileSync(BENCHMARK_OUTPUT, "utf-8"));
    existing["ingest_1850"] = ingest1850;
    writeFileSync(BENCHMARK_OUTPUT, JSON.stringify(existing, null, 2), "utf-8");
    console.log("ingest_1850 section written to benchmark JSON.");
    console.log(JSON.stringify(ingest1850, null, 2));
  } finally {
    await sql.end();
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
