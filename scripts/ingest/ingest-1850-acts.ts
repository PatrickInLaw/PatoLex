/**
 * PatoLex 1850 Session-Law Act Ingestion
 *
 * Ingests 11 parsed 1850 First-Session acts into the live PatoLex PostgreSQL DB
 * as pre-code `act_section` provisions, with full lineage_edge + benchmark instrumentation.
 *
 * Stages:
 *   1. ingest-source      — insert source_document row for the 1850 Statutes volume
 *   2. ingest-enactments  — insert one enactment per act (11 rows)
 *   3. ingest-provisions  — insert one act_section provision + designation_history per act
 *   4. ingest-change-events — insert one `enact` change_event per act
 *   5. lineage-edge       — create a synthetic demo edge + query recursive CTE
 *
 * Does NOT truncate existing data. Does NOT materialize provision_version for act_sections
 * (those have no successor amendments — the existing Penal Code data is left intact).
 *
 * Usage (from repo root):
 *   npx tsx scripts/ingest/ingest-1850-acts.ts
 *
 * Reads DATABASE_URL from .env.local.
 */

import { appendFileSync, readFileSync, writeFileSync } from "fs";
import postgres from "postgres";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });

// ---------------------------------------------------------------------------
// PATHS
// ---------------------------------------------------------------------------
const SCRATCH_1850 =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-1850";
const SCRATCH_HIST =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-historical";
const BENCHMARK_OUTPUT = SCRATCH_HIST + "\\ingest_benchmark.json";
const LOG_FILE =
  "docs\\80_PROJECT_HISTORY\\run-logs\\ingest-benchmark-run.log";
const ACTS_1850_PATH = SCRATCH_1850 + "\\acts_1850_sample.json";

// ---------------------------------------------------------------------------
// LOG HELPER
// ---------------------------------------------------------------------------
function logRun(phase: string, desc: string, status: "OK" | "WARN" | "FAIL") {
  const d = new Date(Date.now() - 7 * 3600 * 1000);
  const ts = d.toISOString().replace("T", " ").slice(0, 16) + " PT";
  const line = `[${ts}] ${phase} | ${desc} | ${status}\n`;
  process.stderr.write(line);
  try {
    appendFileSync(LOG_FILE, line, "utf-8");
  } catch { /* non-fatal */ }
}

// ---------------------------------------------------------------------------
// TIMER
// ---------------------------------------------------------------------------
function now(): bigint { return process.hrtime.bigint(); }
function ms(start: bigint): number { return Number(process.hrtime.bigint() - start) / 1e6; }

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------
interface Act1850 {
  chapter: string;
  title: string;
  approved_date: string;
  text: string;
  source_page: number;
}

interface StageTiming {
  stage: string;
  rows: number;
  wallMs: number;
  perUnitMs: number;
}

// ---------------------------------------------------------------------------
// PARSE OPERATIVE DATE
// ---------------------------------------------------------------------------
function parseOperativeDate(approvedDate: string): string | null {
  // Formats: "Passed January 31, 1850", "Passed February 2, 1850", etc.
  const m = approvedDate.match(/(\w+ \d+,?\s*\d{4})/);
  if (!m) return null;
  const d = new Date(m[1].replace(",", ""));
  if (isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// MAIN INGEST
// ---------------------------------------------------------------------------
async function main() {
  console.log("PatoLex 1850 Act Ingestion");
  console.log("==========================");

  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set — check .env.local");

  logRun("1850-INIT", "1850 act ingest started", "OK");

  const sql = postgres(url, { max: 5 });
  const stages: StageTiming[] = [];

  try {
    // ---- Load input ----
    console.log(`Loading ${ACTS_1850_PATH}...`);
    const acts: Act1850[] = JSON.parse(readFileSync(ACTS_1850_PATH, "utf-8"));
    console.log(`  Loaded ${acts.length} acts`);

    // ---- STAGE 1: source_document ----
    console.log("\n[1/5] ingest-source...");
    const t1 = now();
    const [srcDoc] = await sql`
      INSERT INTO source_document (
        type, citation, jurisdiction, source_channel,
        scan_quality, ocr_engine, ocr_cer_estimate,
        trust_level, retrieved_at, clean_channel
      ) VALUES (
        'session_law',
        'Stats. 1850, First Session',
        'CA',
        'clerk.assembly.ca.gov',
        NULL,
        NULL,
        0.10,
        'ocr_uncertain',
        NOW(),
        true
      )
      RETURNING id
    `;
    const srcDocId = BigInt(srcDoc.id);
    const s1ms = ms(t1);
    stages.push({ stage: "ingest-source", rows: 1, wallMs: s1ms, perUnitMs: s1ms });
    console.log(`  source_document id=${srcDocId}  ${s1ms.toFixed(1)}ms`);
    logRun("1850-STAGE1", `source_document id=${srcDocId}`, "OK");

    // ---- STAGE 2: enactments ----
    console.log("\n[2/5] ingest-enactments...");
    const t2 = now();
    const enactVals = acts.map((a) => {
      const chNum = parseInt(a.chapter, 10);
      const opDate = parseOperativeDate(a.approved_date);
      return {
        source_document_id: srcDocId.toString(),
        citation: `Stats. 1850 ch. ${chNum}`,
        jurisdiction: "CA",
        session: "1849-1850",
        legislature: "1st",
        chapter_number: chNum,
        chaptered_date: opDate,
        effective_date: opDate,
        operative_date: opDate,
        title: a.title.trim().slice(0, 500),
        bill_number: null as string | null,
        kind: "statute" as const,
      };
    });

    const enactRows = await sql`
      INSERT INTO enactment (
        source_document_id, citation, jurisdiction, session, legislature,
        chapter_number, chaptered_date, effective_date, operative_date,
        title, bill_number, kind
      )
      SELECT
        v.source_document_id::bigint,
        v.citation,
        v.jurisdiction,
        v.session,
        v.legislature,
        v.chapter_number::int,
        v.chaptered_date::date,
        v.effective_date::date,
        v.operative_date::date,
        v.title,
        v.bill_number,
        v.kind::enactment_kind
      FROM jsonb_to_recordset(${sql.json(enactVals)})
        AS v(
          source_document_id text, citation text, jurisdiction text,
          session text, legislature text, chapter_number text,
          chaptered_date text, effective_date text, operative_date text,
          title text, bill_number text, kind text
        )
      RETURNING id, chapter_number
    `;
    const s2ms = ms(t2);
    stages.push({ stage: "ingest-enactments", rows: enactRows.length, wallMs: s2ms, perUnitMs: s2ms / enactRows.length });

    // Build chapter -> enactment_id map
    const chapterToEnactId = new Map<number, bigint>();
    for (const r of enactRows) {
      chapterToEnactId.set(r.chapter_number, BigInt(r.id));
    }
    console.log(`  ${enactRows.length} enactments  ${s2ms.toFixed(1)}ms`);
    logRun("1850-STAGE2", `${enactRows.length} enactments`, "OK");

    // ---- STAGE 3: provisions + designation_history ----
    console.log("\n[3/5] ingest-provisions...");
    const t3 = now();

    const provVals = acts.map((a) => {
      const chNum = parseInt(a.chapter, 10);
      const opDate = parseOperativeDate(a.approved_date) ?? "1850-01-01";
      return {
        jurisdiction: "CA",
        unit_type: "act_section" as const,
        current_designation: `Stats. 1850 ch. ${chNum}`,
        status: "active" as const,
        chapter_number: chNum,
        operative_date: opDate,
      };
    });

    const provRows = await sql`
      INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
      SELECT v.jurisdiction, v.unit_type::unit_type, v.current_designation, v.status::provision_status
      FROM jsonb_to_recordset(${sql.json(provVals)})
        AS v(jurisdiction text, unit_type text, current_designation text, status text)
      RETURNING id, current_designation
    `;

    // Map chapter number -> provision id
    const chapterToProvId = new Map<number, bigint>();
    for (let i = 0; i < provRows.length; i++) {
      const chNum = parseInt(acts[i].chapter, 10);
      chapterToProvId.set(chNum, BigInt(provRows[i].id));
    }

    // Insert designation_history rows
    const desigVals = acts.map((a) => {
      const chNum = parseInt(a.chapter, 10);
      const pid = chapterToProvId.get(chNum)!;
      const opDate = parseOperativeDate(a.approved_date) ?? "1850-01-01";
      return {
        provision_id: pid.toString(),
        code: "Statutes of California 1850",
        section_number: a.chapter,
        label: `Stats. 1850 ch. ${chNum}`,
        valid_range: `[${opDate},)`,
      };
    });

    await sql`
      INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
      SELECT v.provision_id::bigint, v.code, v.section_number, v.label, v.valid_range::daterange
      FROM jsonb_to_recordset(${sql.json(desigVals)})
        AS v(provision_id text, code text, section_number text, label text, valid_range text)
    `;

    const s3ms = ms(t3);
    const s3rows = provRows.length + desigVals.length;
    stages.push({ stage: "ingest-provisions", rows: s3rows, wallMs: s3ms, perUnitMs: s3ms / s3rows });
    console.log(`  ${provRows.length} provisions + ${desigVals.length} designation_history rows  ${s3ms.toFixed(1)}ms`);
    logRun("1850-STAGE3", `${provRows.length} provisions`, "OK");

    // ---- STAGE 4: change_events (one enact per act) ----
    console.log("\n[4/5] ingest-change-events...");
    const t4 = now();

    const ceVals = acts.map((a, i) => {
      const chNum = parseInt(a.chapter, 10);
      const pid = chapterToProvId.get(chNum)!;
      const eid = chapterToEnactId.get(chNum)!;
      const opDate = parseOperativeDate(a.approved_date) ?? "1850-01-01";
      return {
        enactment_id: eid.toString(),
        provision_id: pid.toString(),
        action: "enact" as const,
        new_text: a.text || null,
        operative_date: opDate,
        in_act_order: i,
        chaptered_out: false,
        trust_level: "ocr_uncertain" as const,
        source_document_id: srcDocId.toString(),
        page_ref: `p. ${a.source_page}`,
      };
    });

    const ceRows = await sql`
      INSERT INTO change_event (
        enactment_id, provision_id, action, new_text,
        operative_date, in_act_order, chaptered_out,
        trust_level, source_document_id, page_ref
      )
      SELECT
        v.enactment_id::bigint,
        v.provision_id::bigint,
        v.action::change_action,
        v.new_text,
        v.operative_date::date,
        v.in_act_order::int,
        v.chaptered_out::boolean,
        v.trust_level::trust_level,
        v.source_document_id::bigint,
        v.page_ref
      FROM jsonb_to_recordset(${sql.json(ceVals)})
        AS v(
          enactment_id text, provision_id text, action text, new_text text,
          operative_date text, in_act_order text, chaptered_out text,
          trust_level text, source_document_id text, page_ref text
        )
      RETURNING id
    `;

    const s4ms = ms(t4);
    stages.push({ stage: "ingest-change-events", rows: ceRows.length, wallMs: s4ms, perUnitMs: s4ms / ceRows.length });
    console.log(`  ${ceRows.length} change_events  ${s4ms.toFixed(1)}ms`);
    logRun("1850-STAGE4", `${ceRows.length} change_events`, "OK");

    // ---- STAGE 5: lineage_edge ----
    // The 1850 sample contains civil governance acts (State Translator, AG office,
    // Sacramento City incorporation, pilot regulations, etc.) — none are a direct
    // subject-matter predecessor of a specific 1872 Penal Code section in the sample.
    // Therefore: ONE SYNTHETIC DEMO EDGE is created (mechanism validation only).
    //
    // Edge: Stats. 1850 ch. 23 (Court supersession / appellate jurisdiction)
    //       --> Penal Code § 1 (structural provision, "The Penal Code")
    // Edge type: repeal_reenact (predecessor's subject matter was eventually absorbed
    //            into the 1872 codification)
    // This edge is SYNTHETIC — see note column.
    console.log("\n[5/5] lineage-edge (synthetic demo)...");
    const t5 = now();

    // ch. 23 = "AN ACT to supersede certain Courts..."
    const predProvId = chapterToProvId.get(23)!;
    // Penal Code § 1 provision id = 1 (confirmed above)
    const succProvId = BigInt(1);
    // Use the 1872 Penal Code enactment id
    const [enact1872Row] = await sql`
      SELECT id FROM enactment WHERE citation LIKE 'Stats. 1872%' LIMIT 1
    `;
    if (!enact1872Row) throw new Error("Could not find 1872 Penal Code enactment");
    const enact1872Id = BigInt(enact1872Row.id);

    const [edgeRow] = await sql`
      INSERT INTO lineage_edge (
        enactment_id,
        predecessor_provision_id,
        successor_provision_id,
        edge_type,
        text_disposition,
        continues,
        note
      ) VALUES (
        ${enact1872Id},
        ${predProvId},
        ${succProvId},
        'repeal_reenact',
        'Subject matter of pre-code court organization acts absorbed into 1872 Penal Code',
        false,
        'SYNTHETIC DEMO — mechanism validation only, not a real legal disposition'
      )
      RETURNING id
    `;
    const s5ms = ms(t5);
    stages.push({ stage: "lineage-edge", rows: 1, wallMs: s5ms, perUnitMs: s5ms });
    console.log(`  lineage_edge id=${edgeRow.id}  pred_prov=${predProvId}  succ_prov=${succProvId}  ${s5ms.toFixed(1)}ms`);
    logRun("1850-STAGE5", `lineage_edge id=${edgeRow.id} SYNTHETIC DEMO`, "OK");

    // ---- Recursive CTE: full ancestor+descendant chain ----
    console.log("\n=== RECURSIVE CTE LINEAGE QUERY ===");
    console.log(`Starting from provision id=${predProvId} (Stats. 1850 ch. 23)`);

    // PostgreSQL recursive CTEs require exactly ONE non-recursive term and ONE recursive
    // term combined with UNION ALL. Multiple recursive branches must be done via separate
    // CTEs or by unioning within the recursive part. We use two separate CTEs:
    // one walking descendants, one walking ancestors, then union the results.
    const lineageRows = await sql`
      WITH RECURSIVE
      -- Walk forward: from starting provision, follow edges where it is predecessor
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
      -- Walk backward: from starting provision, follow edges where it is successor
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

    console.log("\nLineage chain result:");
    console.log("provision_id | current_designation         | unit_type    | edge_type      | linked_from                 | direction  | depth");
    console.log("-".repeat(130));
    for (const r of lineageRows) {
      console.log(
        String(r.provision_id).padEnd(13) + "| " +
        String(r.current_designation ?? "").slice(0, 28).padEnd(28) + " | " +
        String(r.unit_type ?? "").padEnd(13) + "| " +
        String(r.edge_type ?? "").padEnd(15) + " | " +
        String(r.linked_from ?? "").slice(0, 28).padEnd(28) + " | " +
        String(r.direction).padEnd(11) + "| " +
        String(r.depth)
      );
    }

    // ---- Final counts ----
    console.log("\n=== FINAL DB COUNTS ===");
    const unitCounts = await sql`
      SELECT unit_type::text, count(*)::int as cnt
      FROM provision
      GROUP BY unit_type
      ORDER BY unit_type
    `;
    console.log("unit_type    | count");
    console.log("-".repeat(30));
    for (const r of unitCounts) {
      console.log(`${String(r.unit_type).padEnd(13)}| ${r.cnt}`);
    }

    const [ceTotalRow] = await sql`SELECT count(*)::int as cnt FROM change_event`;
    console.log(`\nTotal change_events: ${ceTotalRow.cnt}`);

    const [edgeTotalRow] = await sql`SELECT count(*)::int as cnt FROM lineage_edge`;
    console.log(`Total lineage_edges: ${edgeTotalRow.cnt}`);

    // ---- Update benchmark JSON ----
    console.log("\nUpdating benchmark JSON...");
    const existing = JSON.parse(readFileSync(BENCHMARK_OUTPUT, "utf-8"));

    const totalMs = stages.reduce((acc, s) => acc + s.wallMs, 0);
    const bench1850 = {
      ingested_at: new Date().toISOString(),
      input_file: ACTS_1850_PATH,
      acts_count: acts.length,
      notes: [
        "Single run (not averaged) — act_section rows added to existing code_section data, no truncate",
        "No materialize stage — act_section provisions have no successor amendments in this dataset",
        "Lineage edge is SYNTHETIC DEMO — see lineage_edge note column",
        "OCR trust_level='ocr_uncertain' (CER est. 5–15%) for all 1850 rows",
        "approved_date for ch.11 was blank in source JSON; operative_date defaulted to 1850-01-01",
      ],
      stages: stages.map((s) => ({
        stage: s.stage,
        rows: s.rows,
        wall_ms: parseFloat(s.wallMs.toFixed(2)),
        per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
      })),
      total_ms: parseFloat(totalMs.toFixed(2)),
      rows_added: {
        source_documents: 1,
        enactments: acts.length,
        provisions_act_section: acts.length,
        designation_history: acts.length,
        change_events: acts.length,
        lineage_edges: 1,
      },
      lineage_edge: {
        type: "SYNTHETIC_DEMO",
        predecessor: `Stats. 1850 ch. 23 (provision id=${predProvId})`,
        successor: `Penal Code section 1 (provision id=${succProvId})`,
        edge_type: "repeal_reenact",
        note: "SYNTHETIC DEMO — mechanism validation only, not a real legal disposition",
        recursive_cte_rows_returned: lineageRows.length,
      },
      final_db_counts: {
        provision_by_unit_type: Object.fromEntries(unitCounts.map((r) => [r.unit_type, r.cnt])),
        change_events_total: ceTotalRow.cnt,
        lineage_edges_total: edgeTotalRow.cnt,
      },
    };

    existing["ingest_1850"] = bench1850;
    writeFileSync(BENCHMARK_OUTPUT, JSON.stringify(existing, null, 2), "utf-8");
    console.log(`Benchmark JSON updated: ${BENCHMARK_OUTPUT}`);

    // ---- Summary ----
    console.log("\n=== 1850 INGEST SUMMARY ===");
    console.log(`Acts processed:        ${acts.length}`);
    console.log(`Enactments added:      ${acts.length}`);
    console.log(`Provisions (act_sec):  ${acts.length}`);
    console.log(`Change events added:   ${acts.length}`);
    console.log(`Lineage edges added:   1 (SYNTHETIC DEMO)`);
    console.log(`Total wall time:       ${totalMs.toFixed(1)}ms`);
    console.log("\nPer-stage breakdown:");
    for (const s of stages) {
      console.log(`  ${s.stage.padEnd(26)} ${s.rows} rows  ${s.wallMs.toFixed(1)}ms  (${s.perUnitMs.toFixed(2)}ms/unit)`);
    }

    logRun("1850-COMPLETE", `acts=${acts.length} provisions=${acts.length} change_events=${acts.length} lineage_edges=1 total_ms=${totalMs.toFixed(0)}`, "OK");

  } finally {
    await sql.end();
  }
}

main().catch((err) => {
  console.error("FATAL:", err);
  logRun("1850-FAIL", String(err), "FAIL");
  process.exit(1);
});
