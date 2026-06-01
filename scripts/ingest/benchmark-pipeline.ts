/**
 * PatoLex Ingest Benchmark Pipeline
 *
 * Spike/benchmark tooling — NOT the eventual C# production pipeline.
 * Lives in scripts/ingest/ to be clearly separate from pipeline/ and src/server/.
 *
 * Stages:
 *   1. ingest-sources       — insert source_document rows
 *   2. ingest-enactments    — insert enactment rows
 *   3. ingest-provisions    — insert provision + designation_history rows
 *   4. ingest-change-events — insert change_event rows (1872 enact + 1883 amend/repeal/add)
 *   5. materialize          — build provision_version daterange rows via SQL fold
 *   6. validate             — compare 1883 versions against pc_extract_1883.json
 *
 * Usage (from repo root):
 *   npx tsx scripts/ingest/benchmark-pipeline.ts
 *
 * Reads DATABASE_URL from .env.local.
 * Truncates all tables between runs, leaves DB in final state after run 3.
 */

import { appendFileSync, readFileSync, writeFileSync } from "fs";
import postgres from "postgres";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });

// ---------------------------------------------------------------------------
// PATHS
// ---------------------------------------------------------------------------
const SCRATCH =
  "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-historical";
const RUNS = 3;
const BENCHMARK_OUTPUT = SCRATCH + "\\ingest_benchmark.json";
const LOG_FILE =
  "docs\\80_PROJECT_HISTORY\\run-logs\\ingest-benchmark-run.log";

const PC_1872_PATH = SCRATCH + "\\pc_extract_1872.json";
const PC_1883_PATH = SCRATCH + "\\pc_extract_1883.json";
const PC_1881_PATH = SCRATCH + "\\pc_extract_1881.json";
const DIRECTIVES_PATH = SCRATCH + "\\method_a_final_validation.json";

// ---------------------------------------------------------------------------
// LOG HELPER
// ---------------------------------------------------------------------------
function logRun(phase: string, desc: string, status: "OK" | "WARN" | "FAIL") {
  // Approximate PT (UTC-7 summer 2026)
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
interface BaselineSection { section_num: number; text: string; }
interface ValidationResult {
  section: number;
  action: string;
  status: string;
  cer?: number | null;
  rec_snippet?: string | null;
  gt_snippet?: string | null;
}
interface MethodAFinal {
  baseline_sections: number;
  gt_sections: number;
  directives_found: number;
  directives_applied: number;
  results: ValidationResult[];
}
interface AmendEvent {
  secNum: number;
  action: "repeal" | "amend" | "add";
  newText: string | null;
  operativeDate: string;
  chapterNum: number;
  inActOrder: number;
  actKey: "feb8" | "mar9" | "mar15";
}
interface StageTiming {
  stage: string;
  rows: number;
  wallMs: number;
  perUnitMs: number;
}
interface RunResult {
  run: number;
  stages: StageTiming[];
  totalMs: number;
  provisions: number;
  changeEvents: number;
  provisionVersions: number;
  validationSummary: Record<string, number>;
}

// ---------------------------------------------------------------------------
// LOAD INPUT DATA
// ---------------------------------------------------------------------------
function loadData() {
  console.log("Loading input data...");
  const baseline: BaselineSection[] = JSON.parse(readFileSync(PC_1872_PATH, "utf-8"));
  const gt1883List: BaselineSection[] = JSON.parse(readFileSync(PC_1883_PATH, "utf-8"));
  const methodA: MethodAFinal = JSON.parse(readFileSync(DIRECTIVES_PATH, "utf-8"));

  const gt1883 = new Map<number, string>();
  for (const s of gt1883List) {
    if (s.section_num !== undefined && s.text) gt1883.set(s.section_num, s.text);
  }

  console.log(`  baseline sections: ${baseline.length}`);
  console.log(`  gt1883 sections:   ${gt1883.size}`);
  console.log(`  directives:        ${methodA.results.length} results in file (${methodA.directives_found} total found)`);
  return { baseline, gt1883, methodA };
}

// ---------------------------------------------------------------------------
// BUILD 1883 AMENDMENT EVENTS
// ---------------------------------------------------------------------------
/**
 * Reconstruct all 12 1883 directives:
 *   Feb 8:  §§299,300,301 repeal (ch.2 from directives_1883.json "chapter:II")
 *   Mar 9:  §626 amend, §§627,628,629 repeal, §631 amend, §632 amend, §634 amend, §636 amend
 *             (ch.38 — ESTIMATED; see assumption note in benchmark output)
 *   Mar 15: §1388 add (ch.92 — ESTIMATED)
 *
 * Sections 627/628/629 are from directives_1883.json (not in method_a_final_validation results).
 * new_text for amend/add events = rec_snippet from method_a_final_validation.json where available.
 * rec_snippets are PARTIAL (truncated OCR fragments), not full section texts — flagged in output.
 */
function build1883Events(results: ValidationResult[]): AmendEvent[] {
  const snip = (sec: number) =>
    results.find((r) => r.section === sec)?.rec_snippet ?? null;

  const events: AmendEvent[] = [];
  // Feb 8 act
  const feb8secs = [299, 300, 301];
  for (let i = 0; i < feb8secs.length; i++) {
    events.push({ secNum: feb8secs[i], action: "repeal", newText: null, operativeDate: "1883-02-08", chapterNum: 2, inActOrder: i, actKey: "feb8" });
  }
  // Mar 9 act
  const mar9 = [
    { n: 626, a: "amend" as const },
    { n: 627, a: "repeal" as const },
    { n: 628, a: "repeal" as const },
    { n: 629, a: "repeal" as const },
    { n: 631, a: "amend" as const },
    { n: 632, a: "amend" as const },
    { n: 634, a: "amend" as const },
    { n: 636, a: "amend" as const },
  ];
  for (let i = 0; i < mar9.length; i++) {
    const e = mar9[i];
    events.push({ secNum: e.n, action: e.a, newText: e.a === "repeal" ? null : snip(e.n), operativeDate: "1883-03-09", chapterNum: 38, inActOrder: i, actKey: "mar9" });
  }
  // Mar 15 act
  events.push({ secNum: 1388, action: "add", newText: snip(1388), operativeDate: "1883-03-15", chapterNum: 92, inActOrder: 0, actKey: "mar15" });

  return events;
}

// ---------------------------------------------------------------------------
// TRUNCATE
// ---------------------------------------------------------------------------
async function truncateAll(sql: postgres.Sql) {
  await sql`TRUNCATE provision_version, change_event, designation_history, lineage_edge, enactment, provision, source_document RESTART IDENTITY CASCADE`;
}

// ---------------------------------------------------------------------------
// STAGE 1: INGEST SOURCES
// ---------------------------------------------------------------------------
async function stage1IngestSources(sql: postgres.Sql) {
  const t = now();
  const rows = await sql`
    INSERT INTO source_document (type, citation, jurisdiction, source_channel, scan_quality, ocr_engine, ocr_cer_estimate, trust_level, retrieved_at, clean_channel)
    VALUES
      ('scan',        'penalcodecalifo00burcgoog (1872 Penal Code baseline)',     'CA', 'https://archive.org/details/penalcodecalifo00burcgoog', 'good', 'abbyy-djvu', 0.08, 'derived', NOW(), false),
      ('session_law', 'Stats. 1883 ch. 2 (Feb 8 repeals §§299-301)',             'CA', 'statutescalifor00caligoog', 'good', 'abbyy-djvu', 0.05, 'derived', NOW(), false),
      ('session_law', 'Stats. 1883 ch. 38 (Mar 9 game/fish amendments)',          'CA', 'statutescalifor00caligoog', 'good', 'abbyy-djvu', 0.05, 'derived', NOW(), false),
      ('session_law', 'Stats. 1883 ch. 92 (Mar 15 §1388 add)',                   'CA', 'statutescalifor00caligoog', 'good', 'abbyy-djvu', 0.05, 'derived', NOW(), false)
    RETURNING id
  `;
  const wallMs = ms(t);
  const ids = rows.map((r) => BigInt(r.id));
  return { baselineDocId: ids[0], feb8DocId: ids[1], mar9DocId: ids[2], mar15DocId: ids[3], rows: 4, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 2: INGEST ENACTMENTS
// ---------------------------------------------------------------------------
async function stage2IngestEnactments(sql: postgres.Sql, docIds: {
  baselineDocId: bigint; feb8DocId: bigint; mar9DocId: bigint; mar15DocId: bigint;
}) {
  const t = now();
  const rows = await sql`
    INSERT INTO enactment (source_document_id, citation, jurisdiction, session, legislature, chapter_number, chaptered_date, effective_date, operative_date, title, kind)
    VALUES
      (${docIds.baselineDocId}, 'Stats. 1872 (Penal Code codification)',             'CA', '1871-1872', '19th', NULL, '1872-03-04', '1872-07-01', '1872-07-01', 'The Penal Code of California',                                              'recodification'),
      (${docIds.feb8DocId},     'Stats. 1883, ch. 2',                                'CA', '1883',      '25th',    2, '1883-02-08', '1883-02-08', '1883-02-08', 'An Act to repeal Penal Code §§299-301',                                      'statute'),
      (${docIds.mar9DocId},     'Stats. 1883, ch. 38',                               'CA', '1883',      '25th',   38, '1883-03-09', '1883-03-09', '1883-03-09', 'An Act amending Penal Code §§626,631-632,634,636 and repealing §§627-629',    'statute'),
      (${docIds.mar15DocId},    'Stats. 1883, ch. 92',                               'CA', '1883',      '25th',   92, '1883-03-15', '1883-03-15', '1883-03-15', 'An Act adding §1388 to the Penal Code',                                      'statute')
    RETURNING id
  `;
  const wallMs = ms(t);
  const ids = rows.map((r) => BigInt(r.id));
  return { e1872: ids[0], e1883feb8: ids[1], e1883mar9: ids[2], e1883mar15: ids[3], rows: 4, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 3: INGEST PROVISIONS + DESIGNATION HISTORY
// ---------------------------------------------------------------------------
/**
 * Batch strategy:
 *   Provisions: jsonb_to_recordset batch of 100 rows per INSERT, 720 total.
 *   Designation history: same batch size, same total.
 *   Both use jsonb_to_recordset so each round-trip moves 100 rows.
 *   Total round trips: ceil(720/100)*2 = 16 round trips for 1440 rows.
 */
async function stage3IngestProvisions(sql: postgres.Sql, baseline: BaselineSection[]) {
  const t = now();
  const BATCH = 100;
  const secToProvId = new Map<number, bigint>();

  for (let i = 0; i < baseline.length; i += BATCH) {
    const chunk = baseline.slice(i, i + BATCH);
    const vals = chunk.map((s) => ({
      jurisdiction: "CA",
      unit_type: "code_section",
      current_designation: `Penal Code § ${s.section_num}`,
      status: "active",
    }));
    // Use sql.json() to pass as a proper JSONB parameter (postgres-js typed param)
    const result = await sql`
      INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
      SELECT v.jurisdiction, v.unit_type::unit_type, v.current_designation, v.status::provision_status
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(jurisdiction text, unit_type text, current_designation text, status text)
      RETURNING id, current_designation
    `;
    for (let j = 0; j < result.length; j++) {
      secToProvId.set(chunk[j].section_num, BigInt(result[j].id));
    }
  }

  // designation_history: one row per section, valid_range = [1872-07-01,)
  for (let i = 0; i < baseline.length; i += BATCH) {
    const chunk = baseline.slice(i, i + BATCH);
    const vals = chunk.map((s) => ({
      provision_id: secToProvId.get(s.section_num)!.toString(),
      code: "Penal Code",
      section_number: s.section_num.toString(),
      label: `Penal Code § ${s.section_num}`,
      valid_range: "[1872-07-01,)",
    }));
    await sql`
      INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
      SELECT (v.provision_id::bigint), v.code, v.section_number, v.label, v.valid_range::daterange
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(provision_id text, code text, section_number text, label text, valid_range text)
    `;
  }

  const wallMs = ms(t);
  return { secToProvId, provRows: secToProvId.size, desigRows: secToProvId.size, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 4: INGEST CHANGE EVENTS
// ---------------------------------------------------------------------------
/**
 * Batch strategy:
 *   1872 enact events: 720 rows in batches of 100 (8 round trips).
 *   1883 events: 12 rows in a single INSERT.
 *   Total round trips: 9.
 */
async function stage4IngestChangeEvents(
  sql: postgres.Sql,
  baseline: BaselineSection[],
  events1883: AmendEvent[],
  secToProvId: Map<number, bigint>,
  enacts: { e1872: bigint; e1883feb8: bigint; e1883mar9: bigint; e1883mar15: bigint },
  docs: { baselineDocId: bigint; feb8DocId: bigint; mar9DocId: bigint; mar15DocId: bigint }
) {
  const t = now();
  const BATCH = 100;
  let enactCount = 0;

  // 1872 enact events
  const enactBatch = baseline.map((s, i) => ({
    enactment_id: enacts.e1872.toString(),
    provision_id: secToProvId.get(s.section_num)!.toString(),
    action: "enact",
    new_text: s.text || null,
    operative_date: "1872-07-01",
    in_act_order: i,
    trust_level: "derived",
    source_document_id: docs.baselineDocId.toString(),
  }));

  for (let i = 0; i < enactBatch.length; i += BATCH) {
    const chunk = enactBatch.slice(i, i + BATCH);
    const r = await sql`
      INSERT INTO change_event (enactment_id, provision_id, action, new_text, operative_date, in_act_order, chaptered_out, trust_level, source_document_id)
      SELECT (v.enactment_id::bigint), (v.provision_id::bigint), v.action::change_action, v.new_text,
             v.operative_date::date, v.in_act_order::int, false, v.trust_level::trust_level, (v.source_document_id::bigint)
      FROM jsonb_to_recordset(${sql.json(chunk)})
        AS v(enactment_id text, provision_id text, action text, new_text text, operative_date text, in_act_order text, trust_level text, source_document_id text)
      RETURNING id
    `;
    enactCount += r.length;
  }

  // Handle any 1883 event targeting a section not in the 1872 baseline.
  // Sections 626-629, 632, 636 were added between 1872-1883 (not in our baseline extract).
  // §1388 is a genuine "add" (brand new section). For all missing sections we create
  // a provision so the FK can be satisfied. Designation start date uses the 1883 operative
  // date (earliest known existence). This is flagged as an assumption in the output.
  for (const e of events1883) {
    if (!secToProvId.has(e.secNum)) {
      const desigStart = e.action === "add" ? e.operativeDate : "1872-07-01";
      const [p] = await sql`
        INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
        VALUES ('CA', 'code_section', ${"Penal Code § " + e.secNum}, 'active')
        RETURNING id
      `;
      const pid = BigInt(p.id);
      secToProvId.set(e.secNum, pid);
      await sql`
        INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
        VALUES (${pid}, 'Penal Code', ${e.secNum.toString()}, ${"Penal Code § " + e.secNum}, ${("[" + desigStart + ",)")}::daterange)
      `;
    }
  }

  // 1883 events
  const amendBatch = events1883.map((e) => {
    const eid = e.actKey === "feb8" ? enacts.e1883feb8 : e.actKey === "mar9" ? enacts.e1883mar9 : enacts.e1883mar15;
    const did = e.actKey === "feb8" ? docs.feb8DocId : e.actKey === "mar9" ? docs.mar9DocId : docs.mar15DocId;
    const pid = secToProvId.get(e.secNum);
    if (!pid) throw new Error(`Missing provision for §${e.secNum}`);
    return {
      enactment_id: eid.toString(),
      provision_id: pid.toString(),
      action: e.action,
      new_text: e.newText,
      operative_date: e.operativeDate,
      in_act_order: e.inActOrder,
      trust_level: "derived",
      source_document_id: did.toString(),
    };
  });

  const ar = await sql`
    INSERT INTO change_event (enactment_id, provision_id, action, new_text, operative_date, in_act_order, chaptered_out, trust_level, source_document_id)
    SELECT (v.enactment_id::bigint), (v.provision_id::bigint), v.action::change_action, v.new_text,
           v.operative_date::date, v.in_act_order::int, false, v.trust_level::trust_level, (v.source_document_id::bigint)
    FROM jsonb_to_recordset(${sql.json(amendBatch)})
      AS v(enactment_id text, provision_id text, action text, new_text text, operative_date text, in_act_order text, trust_level text, source_document_id text)
    RETURNING id
  `;

  const wallMs = ms(t);
  return { enactCount, amendCount: ar.length, totalRows: enactCount + ar.length, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 5: MATERIALIZE
// ---------------------------------------------------------------------------
/**
 * Single SQL CTE fold — no per-provision round trips.
 * Orders events by (operative_date, chapter_number NULLS FIRST, in_act_order) per §9605.
 * Uses LEAD() to compute valid_to for each version.
 * Excludes chaptered_out events.
 * GiST exclusion constraint enforces non-overlap — if it raises, ranges are wrong.
 */
async function stage5Materialize(sql: postgres.Sql) {
  const t = now();
  const result = await sql`
    WITH ordered AS (
      SELECT
        ce.id            AS ce_id,
        ce.provision_id,
        ce.action,
        ce.new_text,
        ce.operative_date,
        ce.in_act_order,
        ce.trust_level,
        ce.source_document_id,
        COALESCE(e.chapter_number, 0) AS ch_num
      FROM change_event ce
      JOIN enactment e ON e.id = ce.enactment_id
      WHERE ce.chaptered_out = false
    ),
    versioned AS (
      SELECT
        ce_id,
        provision_id,
        action,
        new_text,
        operative_date AS valid_from,
        LEAD(operative_date) OVER (
          PARTITION BY provision_id
          ORDER BY operative_date, ch_num, in_act_order
        ) AS valid_to,
        trust_level,
        source_document_id
      FROM ordered
    )
    INSERT INTO provision_version (provision_id, text, valid_range, trust_level, source_change_event_id, source_document_id)
    SELECT
      provision_id,
      CASE WHEN action = 'repeal' THEN NULL ELSE new_text END,
      CASE
        WHEN valid_to IS NULL THEN daterange(valid_from, NULL, '[)')
        ELSE daterange(valid_from, valid_to, '[)')
      END,
      trust_level::trust_level,
      ce_id,
      source_document_id
    FROM versioned
    RETURNING id
  `;
  const wallMs = ms(t);
  return { rows: result.length, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 6: VALIDATE
// ---------------------------------------------------------------------------
/**
 * Query date: 1883-12-01 (after all 1883 amendments operative).
 * Compare provision_version.text against pc_extract_1883.json GT.
 * Match categories:
 *   EXACT     — character-identical
 *   NEAR      — match after whitespace normalization
 *   PARTIAL   — CER < 0.3
 *   MISMATCH  — CER >= 0.3
 *   NULL_TEXT — repeal (PV text is null, GT has repeal notice)
 *   NO_PV     — no version at query date
 */
function norm(t: string | null | undefined): string {
  return t ? t.replace(/\s+/g, " ").trim().toLowerCase() : "";
}

function cer(ref: string, hyp: string): number {
  const r = norm(ref).slice(0, 2000);
  const h = norm(hyp).slice(0, 2000);
  if (r === h) return 0;
  if (!r) return 1;
  const m = r.length, n = h.length;
  const dp = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) {
    let prev = dp[0]; dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      dp[j] = r[i-1] === h[j-1] ? prev : 1 + Math.min(prev, dp[j], dp[j-1]);
      prev = tmp;
    }
  }
  return dp[n] / m;
}

async function stage6Validate(
  sql: postgres.Sql,
  gt1883: Map<number, string>,
  secToProvId: Map<number, bigint>,
  queryDate = "1883-12-01"
) {
  const t = now();

  const pvRows = await sql<{ provision_id: string; text: string | null }[]>`
    SELECT provision_id::text, text
    FROM provision_version
    WHERE valid_range @> ${queryDate}::date
  `;
  const pvMap = new Map<bigint, string | null>();
  for (const r of pvRows) pvMap.set(BigInt(r.provision_id), r.text ?? null);

  const cats = ["EXACT", "NEAR", "PARTIAL", "MISMATCH", "NULL_TEXT", "NO_PV"] as const;
  const summary: Record<string, number> = Object.fromEntries(cats.map((c) => [c, 0]));
  const details: Array<{ section: number; cat: string; cer: number | null }> = [];

  for (const [sec, gtText] of gt1883.entries()) {
    const pid = secToProvId.get(sec);
    if (pid === undefined) { summary["NO_PV"]++; details.push({ section: sec, cat: "NO_PV", cer: null }); continue; }
    if (!pvMap.has(pid)) { summary["NO_PV"]++; details.push({ section: sec, cat: "NO_PV", cer: null }); continue; }
    const pvText = pvMap.get(pid)!;
    if (pvText === null) { summary["NULL_TEXT"]++; details.push({ section: sec, cat: "NULL_TEXT", cer: null }); continue; }
    if (pvText === gtText) { summary["EXACT"]++; details.push({ section: sec, cat: "EXACT", cer: 0 }); continue; }
    if (norm(pvText) === norm(gtText)) { summary["NEAR"]++; details.push({ section: sec, cat: "NEAR", cer: 0 }); continue; }
    const c = cer(gtText, pvText);
    const cat = c < 0.3 ? "PARTIAL" : "MISMATCH";
    summary[cat]++;
    details.push({ section: sec, cat, cer: c });
  }

  const wallMs = ms(t);
  return { summary, details, gtSections: gt1883.size, wallMs };
}

// ---------------------------------------------------------------------------
// PIPELINE RUN
// ---------------------------------------------------------------------------
async function runPipeline(
  sql: postgres.Sql,
  baseline: BaselineSection[],
  gt1883: Map<number, string>,
  events1883: AmendEvent[],
  runNum: number
): Promise<RunResult> {
  console.log(`\n=== RUN ${runNum} of ${RUNS} ===`);
  const runT = now();

  console.log("  [1/6] ingest-sources...");
  const s1 = await stage1IngestSources(sql);
  console.log(`        ${s1.rows} rows  ${s1.wallMs.toFixed(1)}ms`);

  console.log("  [2/6] ingest-enactments...");
  const s2 = await stage2IngestEnactments(sql, { baselineDocId: s1.baselineDocId, feb8DocId: s1.feb8DocId, mar9DocId: s1.mar9DocId, mar15DocId: s1.mar15DocId });
  console.log(`        ${s2.rows} rows  ${s2.wallMs.toFixed(1)}ms`);

  console.log("  [3/6] ingest-provisions...");
  const s3 = await stage3IngestProvisions(sql, baseline);
  console.log(`        ${s3.provRows} provision + ${s3.desigRows} desig rows  ${s3.wallMs.toFixed(1)}ms`);

  console.log("  [4/6] ingest-change-events...");
  const s4 = await stage4IngestChangeEvents(sql, baseline, events1883, s3.secToProvId,
    { e1872: s2.e1872, e1883feb8: s2.e1883feb8, e1883mar9: s2.e1883mar9, e1883mar15: s2.e1883mar15 },
    { baselineDocId: s1.baselineDocId, feb8DocId: s1.feb8DocId, mar9DocId: s1.mar9DocId, mar15DocId: s1.mar15DocId }
  );
  console.log(`        ${s4.totalRows} rows (${s4.enactCount} enact + ${s4.amendCount} amend)  ${s4.wallMs.toFixed(1)}ms`);

  console.log("  [5/6] materialize...");
  const s5 = await stage5Materialize(sql);
  console.log(`        ${s5.rows} provision_version rows  ${s5.wallMs.toFixed(1)}ms`);

  console.log("  [6/6] validate...");
  const s6 = await stage6Validate(sql, gt1883, s3.secToProvId);
  console.log(`        ${s6.gtSections} GT sections compared  ${s6.wallMs.toFixed(1)}ms`);
  console.log("        Summary:", JSON.stringify(s6.summary));

  const totalMs = ms(runT);
  console.log(`  Run ${runNum} total: ${totalMs.toFixed(1)}ms`);

  return {
    run: runNum,
    stages: [
      { stage: "ingest-sources",       rows: s1.rows,                           wallMs: s1.wallMs, perUnitMs: s1.wallMs / s1.rows },
      { stage: "ingest-enactments",    rows: s2.rows,                           wallMs: s2.wallMs, perUnitMs: s2.wallMs / s2.rows },
      { stage: "ingest-provisions",    rows: s3.provRows + s3.desigRows,        wallMs: s3.wallMs, perUnitMs: s3.wallMs / (s3.provRows + s3.desigRows) },
      { stage: "ingest-change-events", rows: s4.totalRows,                      wallMs: s4.wallMs, perUnitMs: s4.wallMs / s4.totalRows },
      { stage: "materialize",          rows: s5.rows,                           wallMs: s5.wallMs, perUnitMs: s5.wallMs / s5.rows },
      { stage: "validate",             rows: s6.gtSections,                     wallMs: s6.wallMs, perUnitMs: s6.wallMs / Math.max(1, s6.gtSections) },
    ],
    totalMs,
    provisions: s3.provRows,
    changeEvents: s4.totalRows,
    provisionVersions: s5.rows,
    validationSummary: s6.summary,
  };
}

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------
async function main() {
  console.log("PatoLex Ingest Benchmark Pipeline");
  console.log("==================================");

  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set — check .env.local");

  logRun("INIT", "Pipeline started", "OK");

  const sql = postgres(url, { max: 5 });

  try {
    const { baseline, gt1883, methodA } = loadData();
    const events1883 = build1883Events(methodA.results);

    console.log(`\nBuilt ${events1883.length} 1883 amendment events:`);
    for (const e of events1883) {
      const snip = e.newText ? e.newText.slice(0, 50) + "..." : "(null)";
      console.log(`  §${e.secNum} ${e.action} @ ${e.operativeDate} ch.${e.chapterNum}  text: ${snip}`);
    }

    const allRuns: RunResult[] = [];

    for (let run = 1; run <= RUNS; run++) {
      logRun(`PRE-RUN-${run}`, "Truncating tables", "OK");
      await truncateAll(sql);
      console.log(`\nTables truncated (run ${run})`);

      const result = await runPipeline(sql, baseline, gt1883, events1883, run);
      allRuns.push(result);

      logRun(`RUN-${run}`, `provisions=${result.provisions} change_events=${result.changeEvents} prov_vers=${result.provisionVersions} total_ms=${result.totalMs.toFixed(0)}`, "OK");
    }

    // ---- Compute averages ----
    const stageNames = allRuns[0].stages.map((s) => s.stage);
    const avgStages = stageNames.map((name) => {
      const times = allRuns.map((r) => r.stages.find((s) => s.stage === name)!);
      const avgWall = times.reduce((a, b) => a + b.wallMs, 0) / RUNS;
      const rows = times[0].rows;
      return { stage: name, rows, wallMs: avgWall, perUnitMs: avgWall / Math.max(1, rows) };
    });
    const avgTotal = allRuns.reduce((a, b) => a + b.totalMs, 0) / RUNS;

    // ---- Print benchmark table ----
    console.log("\n=== BENCHMARK TABLE (avg of 3 runs) ===");
    console.log("Stage".padEnd(26) + "Rows".padStart(7) + "Avg ms".padStart(10) + "ms/unit".padStart(10));
    console.log("-".repeat(55));
    for (const s of avgStages) {
      console.log(s.stage.padEnd(26) + s.rows.toString().padStart(7) + s.wallMs.toFixed(1).padStart(10) + s.perUnitMs.toFixed(4).padStart(10));
    }
    console.log("-".repeat(55));
    console.log("TOTAL".padEnd(26) + "".padStart(7) + avgTotal.toFixed(1).padStart(10));

    // ---- Per-run variance ----
    console.log("\n=== PER-RUN TOTALS ===");
    for (const r of allRuns) {
      console.log(`  Run ${r.run}: ${r.totalMs.toFixed(1)}ms  (prov=${r.provisions} ce=${r.changeEvents} pv=${r.provisionVersions})`);
    }
    const variance = allRuns.reduce((a, b) => a + (b.totalMs - avgTotal) ** 2, 0) / RUNS;
    console.log(`  Std dev: ${Math.sqrt(variance).toFixed(1)}ms`);

    console.log("\n=== FINAL VALIDATION (run 3 DB state, query date 1883-12-01) ===");
    console.log(JSON.stringify(allRuns[RUNS - 1].validationSummary, null, 2));

    // ---- Write benchmark JSON ----
    const benchOut = {
      generated_at: new Date().toISOString(),
      note: "Benchmark spike tooling — see scripts/ingest/benchmark-pipeline.ts",
      input_files: {
        baseline: PC_1872_PATH,
        gt_1883: PC_1883_PATH,
        gt_1881: PC_1881_PATH,
        directives: DIRECTIVES_PATH,
      },
      assumptions: [
        "1872 operative_date = 1872-07-01 (standard CA Penal Code effective date; took effect July 1 1872)",
        "1883 'effective immediately' acts: operative_date = chaptered/approved date",
        "ch.2 for Feb 8 repeals (from directives_1883.json 'chapter:II'); ch.38 for Mar 9 amendments (ESTIMATED); ch.92 for Mar 15 add (ESTIMATED) — chapter numbers affect §9605 ordering within same operative date only",
        "§§627,628,629 repeals reconstructed from directives_1883.json (not present in method_a_final_validation results)",
        "new_text for amend/add events = rec_snippet from method_a_final_validation.json — PARTIAL OCR fragments, not full section text",
      ],
      runs: allRuns.map((r) => ({
        run: r.run,
        total_ms: parseFloat(r.totalMs.toFixed(2)),
        provisions: r.provisions,
        change_events: r.changeEvents,
        provision_versions: r.provisionVersions,
        stages: r.stages.map((s) => ({
          stage: s.stage,
          rows: s.rows,
          wall_ms: parseFloat(s.wallMs.toFixed(2)),
          per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
        })),
        validation_summary: r.validationSummary,
      })),
      averages: {
        total_ms: parseFloat(avgTotal.toFixed(2)),
        std_dev_ms: parseFloat(Math.sqrt(allRuns.reduce((a, b) => a + (b.totalMs - avgTotal) ** 2, 0) / RUNS).toFixed(2)),
        stages: avgStages.map((s) => ({
          stage: s.stage,
          rows: s.rows,
          avg_wall_ms: parseFloat(s.wallMs.toFixed(2)),
          per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
        })),
      },
    };

    writeFileSync(BENCHMARK_OUTPUT, JSON.stringify(benchOut, null, 2), "utf-8");
    console.log(`\nBenchmark JSON written to: ${BENCHMARK_OUTPUT}`);

    logRun("COMPLETE", `Done. Avg total ${avgTotal.toFixed(0)}ms over ${RUNS} runs. DB left in run-${RUNS} state.`, "OK");

  } finally {
    await sql.end();
  }
}

main().catch((err) => {
  console.error("FATAL:", err);
  logRun("FAIL", String(err), "FAIL");
  process.exit(1);
});
