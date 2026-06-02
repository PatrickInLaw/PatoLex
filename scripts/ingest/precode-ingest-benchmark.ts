/**
 * precode-ingest-benchmark.ts
 *
 * PROVISIONAL BENCHMARK — 1850–1871 pre-code session-law sample ingest.
 * Partial coverage (~1,069 acts across 19 session-law volumes, 1850–1871/72).
 * trust_level = 'ocr_uncertain'. Model: 1850-blank-forward, session-laws primary.
 *
 * NOT the certified corpus. Labels everything ocr_uncertain.
 * See PIPELINE_BENCHMARKS.md "1850-1871 pre-code session-law sample ingest (PROVISIONAL BENCHMARK)".
 *
 * Stages:
 *   0. purge                 — TRUNCATE all data tables RESTART IDENTITY CASCADE
 *   1. register-sources      — one source_document per session year
 *   2. ingest-enactments     — one enactment row per act
 *   3. ingest-provisions     — one provision (act_section) + one designation_history per act
 *   4. ingest-change-events  — one 'enact' change_event per act (empty text acts flagged)
 *   5. materialize           — fold change_events → provision_version rows
 *
 * Usage (from repo root):
 *   npx tsx scripts/ingest/precode-ingest-benchmark.ts
 *
 * Reads DATABASE_URL from .env.local.
 * Runs 3 times (truncate between each), leaves DB in final ingested state.
 * Writes structured JSON to PatoLex-scratch/gate-b-precode/precode_ingest_benchmark.json.
 * Appends to docs/80_PROJECT_HISTORY/run-logs/precode-ingest-run.log.
 */

import { appendFileSync, readFileSync, writeFileSync } from "fs";
import postgres from "postgres";
import dotenv from "dotenv";

dotenv.config({ path: ".env.local" });

// ---------------------------------------------------------------------------
// PATHS
// ---------------------------------------------------------------------------
const SCRATCH = "C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\gate-b-precode";
const RUNS = 3;
const BENCHMARK_OUTPUT = SCRATCH + "\\precode_ingest_benchmark.json";
const LOG_FILE = "docs\\80_PROJECT_HISTORY\\run-logs\\precode-ingest-run.log";

// Session year → file mapping (covers all 19 acts_*.json files)
const SESSION_FILES: Array<{ sessionYear: string; legislature: number; file: string; sourceLabel: string }> = [
  { sessionYear: "1850", legislature: 1, file: SCRATCH + "\\acts_1850.json", sourceLabel: "1st Legislature (1850)" },
  { sessionYear: "1851", legislature: 2, file: SCRATCH + "\\acts_1851.json", sourceLabel: "2nd Legislature (1851)" },
  { sessionYear: "1852", legislature: 3, file: SCRATCH + "\\acts_1852.json", sourceLabel: "3rd Legislature (1852)" },
  { sessionYear: "1853", legislature: 4, file: SCRATCH + "\\acts_1853.json", sourceLabel: "4th Legislature (1853)" },
  { sessionYear: "1854", legislature: 5, file: SCRATCH + "\\acts_1854.json", sourceLabel: "5th Legislature (1854)" },
  { sessionYear: "1855", legislature: 6, file: SCRATCH + "\\acts_1855.json", sourceLabel: "6th Legislature (1855)" },
  { sessionYear: "1856", legislature: 7, file: SCRATCH + "\\acts_1856.json", sourceLabel: "7th Legislature (1856)" },
  { sessionYear: "1857", legislature: 8, file: SCRATCH + "\\acts_1857.json", sourceLabel: "8th Legislature (1857)" },
  { sessionYear: "1858", legislature: 9, file: SCRATCH + "\\acts_1858.json", sourceLabel: "9th Legislature (1858)" },
  { sessionYear: "1859", legislature: 10, file: SCRATCH + "\\acts_1859.json", sourceLabel: "10th Legislature (1859)" },
  { sessionYear: "1860", legislature: 11, file: SCRATCH + "\\acts_1860.json", sourceLabel: "11th Legislature (1860)" },
  { sessionYear: "1861", legislature: 12, file: SCRATCH + "\\acts_1861.json", sourceLabel: "12th Legislature (1861)" },
  { sessionYear: "1862", legislature: 13, file: SCRATCH + "\\acts_1862.json", sourceLabel: "13th Legislature (1862)" },
  // 1863 had both a regular and adjourned session; use acts_1863.json as the primary
  { sessionYear: "1863", legislature: 14, file: SCRATCH + "\\acts_1863.json", sourceLabel: "14th Legislature (1863)" },
  { sessionYear: "1863-64", legislature: 15, file: SCRATCH + "\\acts_1863_64.json", sourceLabel: "15th Legislature (1863-64 adjourned)" },
  { sessionYear: "1865-66", legislature: 16, file: SCRATCH + "\\acts_1865_66.json", sourceLabel: "16th Legislature (1865-66)" },
  { sessionYear: "1867-68", legislature: 17, file: SCRATCH + "\\acts_1867_68.json", sourceLabel: "17th Legislature (1867-68)" },
  { sessionYear: "1869-70", legislature: 18, file: SCRATCH + "\\acts_1869_70.json", sourceLabel: "18th Legislature (1869-70)" },
  { sessionYear: "1871-72", legislature: 19, file: SCRATCH + "\\acts_1871_72.json", sourceLabel: "19th Legislature (1871-72)" },
];

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------
interface RawAct {
  session_year: string;
  legislature: number;
  chapter: number;
  title: string;
  approved_date: string;
  text: string;
  source_page: number;
  trust_level?: string;
  source_label?: string;
}

interface ActRecord extends RawAct {
  sessionYear: string;
  legislatureNum: number;
  operativeDate: string | null;   // parsed from approved_date
  citation: string;               // e.g. "Stats. 1852 ch. 14"
  emptyText: boolean;
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
  sourceDocuments: number;
  enactments: number;
  provisions: number;
  changeEvents: number;
  provisionVersions: number;
  emptyTextFlagged: number;
}

// ---------------------------------------------------------------------------
// LOG HELPER
// ---------------------------------------------------------------------------
function logRun(phase: string, desc: string, status: "OK" | "WARN" | "FAIL") {
  const d = new Date(Date.now() - 7 * 3600 * 1000); // approx PT
  const ts = d.toISOString().replace("T", " ").slice(0, 16) + " PT";
  const line = `[${ts}] ${phase} | ${desc} | ${status}\n`;
  process.stderr.write(line);
  try { appendFileSync(LOG_FILE, line, "utf-8"); } catch { /* non-fatal */ }
}

// ---------------------------------------------------------------------------
// TIMER
// ---------------------------------------------------------------------------
function now(): bigint { return process.hrtime.bigint(); }
function ms(start: bigint): number { return Number(process.hrtime.bigint() - start) / 1e6; }

// ---------------------------------------------------------------------------
// DATE PARSING
// ---------------------------------------------------------------------------
/**
 * 19th-century CA acts generally took effect on approval/passage.
 * approved_date field is free-form text (e.g. "Passed January 5, 1850", "April 28, 1852").
 * Returns ISO date string or null if unparseable.
 */
function parseApprovedDate(raw: string, sessionYear: string): string | null {
  if (!raw || raw.trim() === "") return null;

  // Try to extract a date from the string
  // Common patterns:
  //   "Passed January 5, 1850"
  //   "Approved April 28, 1852"
  //   "January 5, 1850"
  //   "April 28th, 1852"
  const monthNames: Record<string, number> = {
    january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
    july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
  };

  // Strip leading keywords
  let s = raw.replace(/^(passed|approved|enacted)\s*/i, "").trim();

  // Pattern: "Month Day, Year" or "Month Dayth, Year"
  const m = s.match(/^(\w+)\s+(\d+)(?:st|nd|rd|th)?,?\s*(\d{4})/i);
  if (m) {
    const monthNum = monthNames[m[1].toLowerCase()];
    if (monthNum) {
      const day = parseInt(m[2], 10);
      const year = parseInt(m[3], 10);
      // Sanity check: year should be within session range; day must be 1-31 (reject OCR artifacts like "80")
      const syYear = parseInt(sessionYear.split("-")[0], 10);
      if (year >= syYear - 1 && year <= syYear + 2 && day >= 1 && day <= 31) {
        return `${year}-${String(monthNum).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      }
    }
  }

  // Fallback: try just extracting a 4-digit year and using Jan 1 of that year
  // This is flagged as approximate
  const yearOnly = s.match(/(\d{4})/);
  if (yearOnly) {
    const year = parseInt(yearOnly[1], 10);
    const syYear = parseInt(sessionYear.split("-")[0], 10);
    if (year >= syYear - 1 && year <= syYear + 2) {
      // Return null — we don't want to fabricate a date for partial info
      return null;
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// LOAD ALL ACTS
// ---------------------------------------------------------------------------
function loadAllActs(): { acts: ActRecord[]; byYear: Map<string, ActRecord[]>; emptyCount: number } {
  const acts: ActRecord[] = [];
  const byYear = new Map<string, ActRecord[]>();

  for (const session of SESSION_FILES) {
    let raw: RawAct[];
    try {
      raw = JSON.parse(readFileSync(session.file, "utf-8"));
    } catch (e) {
      logRun("LOAD", `Could not read ${session.file}: ${e}`, "WARN");
      continue;
    }

    const sessionActs: ActRecord[] = [];
    for (const act of raw) {
      const operativeDate = parseApprovedDate(act.approved_date ?? "", session.sessionYear);
      const citation = `Stats. ${session.sessionYear} ch. ${act.chapter}`;
      const emptyText = !act.text || act.text.trim() === "";

      sessionActs.push({
        ...act,
        sessionYear: session.sessionYear,
        legislatureNum: session.legislature,
        operativeDate,
        citation,
        emptyText,
      });
    }
    acts.push(...sessionActs);
    byYear.set(session.sessionYear, sessionActs);
  }

  const emptyCount = acts.filter((a) => a.emptyText).length;
  return { acts, byYear, emptyCount };
}

// ---------------------------------------------------------------------------
// STAGE 0: PURGE
// ---------------------------------------------------------------------------
async function stage0Purge(sql: postgres.Sql): Promise<{ wallMs: number }> {
  const t = now();
  await sql`TRUNCATE provision_version, change_event, designation_history, lineage_edge, enactment, provision, source_document RESTART IDENTITY CASCADE`;
  const wallMs = ms(t);
  return { wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 1: REGISTER SOURCES
// ---------------------------------------------------------------------------
/**
 * One source_document row per session year.
 * corpus='uncodified_statutes', source_channel='CA Assembly Chief Clerk',
 * clean_channel=true, media_format='ocr_text', trust_level='ocr_uncertain'.
 */
async function stage1RegisterSources(
  sql: postgres.Sql,
  acts: ActRecord[],
): Promise<{ docIdByYear: Map<string, bigint>; rows: number; wallMs: number }> {
  const t = now();

  // Build unique session years from acts
  const sessionYears = [...new Set(SESSION_FILES.map((s) => s.sessionYear))];
  const docIdByYear = new Map<string, bigint>();

  // Batch all inserts in one round-trip using jsonb_to_recordset
  const vals = SESSION_FILES.map((s) => {
    const syActs = acts.filter((a) => a.sessionYear === s.sessionYear);
    const editionYear = parseInt(s.sessionYear.split("-")[0], 10);
    return {
      type: "session_law",
      citation: `CA Statutes ${s.sessionYear} — ${s.sourceLabel}`,
      jurisdiction: "CA",
      source_channel: "CA Assembly Chief Clerk",
      corpus: "uncodified_statutes",
      coverage_start_year: editionYear,
      coverage_end_year: parseInt(s.sessionYear.split("-").pop()!, 10),
      edition_year: editionYear,
      media_format: "ocr_text",
      ocr_engine: "tesseract-5",
      ocr_cer_estimate: 0.12,
      trust_level: "ocr_uncertain",
      clean_channel: true,
      file_name: `acts_${s.sessionYear.replace("-", "_")}.json`,
      verification_note: `Parsed JSON from Chief Clerk OCR scan; ${syActs.length} acts in this session. PROVISIONAL BENCHMARK data.`,
    };
  });

  const result = await sql`
    INSERT INTO source_document (type, citation, jurisdiction, source_channel, corpus, coverage_start_year, coverage_end_year, edition_year, media_format, ocr_engine, ocr_cer_estimate, trust_level, clean_channel, file_name, verification_note, retrieved_at)
    SELECT
      v.type::source_type,
      v.citation,
      v.jurisdiction,
      v.source_channel,
      v.corpus,
      v.coverage_start_year::int,
      v.coverage_end_year::int,
      v.edition_year::int,
      v.media_format,
      v.ocr_engine,
      v.ocr_cer_estimate::double precision,
      v.trust_level::trust_level,
      v.clean_channel::boolean,
      v.file_name,
      v.verification_note,
      NOW()
    FROM jsonb_to_recordset(${sql.json(vals)})
      AS v(type text, citation text, jurisdiction text, source_channel text, corpus text,
           coverage_start_year text, coverage_end_year text, edition_year text,
           media_format text, ocr_engine text, ocr_cer_estimate text, trust_level text,
           clean_channel text, file_name text, verification_note text)
    RETURNING id, citation
  `;

  // Map back from citation to session year
  for (let i = 0; i < SESSION_FILES.length; i++) {
    const row = result[i];
    if (row) docIdByYear.set(SESSION_FILES[i].sessionYear, BigInt(row.id));
  }

  const wallMs = ms(t);
  return { docIdByYear, rows: result.length, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 2: INGEST ENACTMENTS
// ---------------------------------------------------------------------------
/**
 * One enactment per act. kind='statute', jurisdiction='CA',
 * citation='Stats. YYYY ch. N', chapter_number, chaptered_date/operative_date.
 */
async function stage2IngestEnactments(
  sql: postgres.Sql,
  acts: ActRecord[],
  docIdByYear: Map<string, bigint>,
): Promise<{ enactIdByActKey: Map<string, bigint>; rows: number; wallMs: number }> {
  const t = now();
  const BATCH = 200;
  const enactIdByActKey = new Map<string, bigint>();

  for (let i = 0; i < acts.length; i += BATCH) {
    const chunk = acts.slice(i, i + BATCH);
    const vals = chunk.map((act) => {
      const docId = docIdByYear.get(act.sessionYear);
      if (!docId) throw new Error(`No source_document for session year ${act.sessionYear}`);
      return {
        source_document_id: docId.toString(),
        citation: act.citation,
        jurisdiction: "CA",
        session: act.sessionYear,
        legislature: `${act.legislatureNum}th`,
        chapter_number: act.chapter,
        chaptered_date: act.operativeDate,    // best available date
        operative_date: act.operativeDate,
        title: act.title ? act.title.slice(0, 500) : null,
        kind: "statute",
      };
    });

    const result = await sql`
      INSERT INTO enactment (source_document_id, citation, jurisdiction, session, legislature, chapter_number, chaptered_date, operative_date, title, kind)
      SELECT
        (v.source_document_id::bigint),
        v.citation,
        v.jurisdiction,
        v.session,
        v.legislature,
        v.chapter_number::int,
        v.chaptered_date::date,
        v.operative_date::date,
        v.title,
        v.kind::enactment_kind
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(source_document_id text, citation text, jurisdiction text, session text,
             legislature text, chapter_number text, chaptered_date text, operative_date text,
             title text, kind text)
      RETURNING id
    `;

    for (let j = 0; j < chunk.length; j++) {
      const act = chunk[j];
      const actKey = `${act.sessionYear}:${act.chapter}`;
      enactIdByActKey.set(actKey, BigInt(result[j].id));
    }
  }

  const wallMs = ms(t);
  return { enactIdByActKey, rows: acts.length, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 3: INGEST PROVISIONS + DESIGNATION HISTORY
// ---------------------------------------------------------------------------
/**
 * One provision (unit_type='act_section') per act.
 * current_designation = 'Stats. YYYY ch. N'.
 * designation_history: code=null (uncodified), section_number=chapter string,
 * valid_range from operative_date (or session start year if null).
 */
async function stage3IngestProvisions(
  sql: postgres.Sql,
  acts: ActRecord[],
): Promise<{ provIdByActKey: Map<string, bigint>; rows: number; wallMs: number }> {
  const t = now();
  const BATCH = 200;
  const provIdByActKey = new Map<string, bigint>();

  // Insert provisions in batches, collect IDs
  for (let i = 0; i < acts.length; i += BATCH) {
    const chunk = acts.slice(i, i + BATCH);
    const vals = chunk.map((act) => ({
      jurisdiction: "CA",
      unit_type: "act_section",
      current_designation: act.citation,
      status: "active",
    }));

    const result = await sql`
      INSERT INTO provision (jurisdiction, unit_type, current_designation, status)
      SELECT
        v.jurisdiction,
        v.unit_type::unit_type,
        v.current_designation,
        v.status::provision_status
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(jurisdiction text, unit_type text, current_designation text, status text)
      RETURNING id
    `;

    for (let j = 0; j < chunk.length; j++) {
      const act = chunk[j];
      const actKey = `${act.sessionYear}:${act.chapter}`;
      provIdByActKey.set(actKey, BigInt(result[j].id));
    }
  }

  // Insert designation_history in batches
  const allActs = acts; // alias for clarity
  for (let i = 0; i < allActs.length; i += BATCH) {
    const chunk = allActs.slice(i, i + BATCH);
    const vals = chunk.map((act) => {
      const actKey = `${act.sessionYear}:${act.chapter}`;
      const provId = provIdByActKey.get(actKey)!;
      // Use operative date if available; otherwise use session start year Jan 1
      const validFrom = act.operativeDate ?? `${act.sessionYear.split("-")[0]}-01-01`;
      return {
        provision_id: provId.toString(),
        code: null as string | null,   // uncodified — no code name
        section_number: String(act.chapter),
        label: act.citation,
        valid_range: `[${validFrom},)`,
      };
    });

    await sql`
      INSERT INTO designation_history (provision_id, code, section_number, label, valid_range)
      SELECT
        (v.provision_id::bigint),
        v.code,
        v.section_number,
        v.label,
        v.valid_range::daterange
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(provision_id text, code text, section_number text, label text, valid_range text)
    `;
  }

  const wallMs = ms(t);
  return { provIdByActKey, rows: acts.length, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 4: INGEST CHANGE EVENTS
// ---------------------------------------------------------------------------
/**
 * One 'enact' change_event per act. Empty-text acts are ingested with null new_text
 * and counted/flagged but NOT silently skipped (flagged in output).
 */
async function stage4IngestChangeEvents(
  sql: postgres.Sql,
  acts: ActRecord[],
  enactIdByActKey: Map<string, bigint>,
  provIdByActKey: Map<string, bigint>,
  docIdByYear: Map<string, bigint>,
): Promise<{ rows: number; emptyFlagged: number; wallMs: number }> {
  const t = now();
  const BATCH = 200;
  let totalRows = 0;

  // Build source_page reference: acts_YYYY.json acts are 0-indexed within their session
  // Track position within session for in_act_order
  const sessionCounter = new Map<string, number>();

  for (let i = 0; i < acts.length; i += BATCH) {
    const chunk = acts.slice(i, i + BATCH);
    const vals = chunk.map((act) => {
      const actKey = `${act.sessionYear}:${act.chapter}`;
      const enactId = enactIdByActKey.get(actKey);
      const provId = provIdByActKey.get(actKey);
      const docId = docIdByYear.get(act.sessionYear);
      if (!enactId || !provId || !docId) {
        throw new Error(`Missing FK for act ${actKey}: enactId=${enactId} provId=${provId} docId=${docId}`);
      }

      const counter = sessionCounter.get(act.sessionYear) ?? 0;
      sessionCounter.set(act.sessionYear, counter + 1);

      return {
        enactment_id: enactId.toString(),
        provision_id: provId.toString(),
        action: "enact",
        new_text: act.emptyText ? null : act.text,
        operative_date: act.operativeDate,
        in_act_order: counter,
        trust_level: "ocr_uncertain",
        source_document_id: docId.toString(),
        page_ref: act.source_page != null ? `p. ${act.source_page}` : null,
      };
    });

    const result = await sql`
      INSERT INTO change_event (enactment_id, provision_id, action, new_text, operative_date, in_act_order, chaptered_out, trust_level, source_document_id, page_ref)
      SELECT
        (v.enactment_id::bigint),
        (v.provision_id::bigint),
        v.action::change_action,
        v.new_text,
        v.operative_date::date,
        v.in_act_order::int,
        false,
        v.trust_level::trust_level,
        (v.source_document_id::bigint),
        v.page_ref
      FROM jsonb_to_recordset(${sql.json(vals)})
        AS v(enactment_id text, provision_id text, action text, new_text text,
             operative_date text, in_act_order text, trust_level text,
             source_document_id text, page_ref text)
      RETURNING id
    `;
    totalRows += result.length;
  }

  const emptyFlagged = acts.filter((a) => a.emptyText).length;
  const wallMs = ms(t);
  return { rows: totalRows, emptyFlagged, wallMs };
}

// ---------------------------------------------------------------------------
// STAGE 5: MATERIALIZE
// ---------------------------------------------------------------------------
/**
 * Fold change_events → provision_version rows via single SQL CTE.
 * For these pre-code enactments, each act-provision has exactly one 'enact' event
 * (no subsequent amendments in this sample), so each provision gets one version
 * [operative_date, infinity).
 * Acts with null operative_date get [null, infinity) which will be stored as a
 * daterange starting at NULL — the DB allows this.
 */
async function stage5Materialize(sql: postgres.Sql): Promise<{ rows: number; wallMs: number }> {
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
          ORDER BY operative_date NULLS FIRST, ch_num, in_act_order
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
        WHEN valid_from IS NULL AND valid_to IS NULL THEN daterange(NULL, NULL, '[)')
        WHEN valid_from IS NULL THEN daterange(NULL, valid_to, '[)')
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
// PIPELINE RUN
// ---------------------------------------------------------------------------
async function runPipeline(
  sql: postgres.Sql,
  acts: ActRecord[],
  docIdByYear: Map<string, bigint>,
  runNum: number,
): Promise<RunResult> {
  process.stderr.write(`\n=== RUN ${runNum} of ${RUNS} ===\n`);
  const runT = now();

  process.stderr.write("  [0/5] purge...\n");
  const s0 = await stage0Purge(sql);
  process.stderr.write(`        TRUNCATE done  ${s0.wallMs.toFixed(1)}ms\n`);

  process.stderr.write("  [1/5] register-sources...\n");
  const s1 = await stage1RegisterSources(sql, acts);
  process.stderr.write(`        ${s1.rows} source_document rows  ${s1.wallMs.toFixed(1)}ms\n`);
  // Update docIdByYear from s1 for subsequent runs
  for (const [k, v] of s1.docIdByYear) docIdByYear.set(k, v);

  process.stderr.write("  [2/5] ingest-enactments...\n");
  const s2 = await stage2IngestEnactments(sql, acts, s1.docIdByYear);
  process.stderr.write(`        ${s2.rows} enactment rows  ${s2.wallMs.toFixed(1)}ms\n`);

  process.stderr.write("  [3/5] ingest-provisions...\n");
  const s3 = await stage3IngestProvisions(sql, acts);
  process.stderr.write(`        ${s3.rows} provision rows + ${s3.rows} designation_history rows  ${s3.wallMs.toFixed(1)}ms\n`);

  process.stderr.write("  [4/5] ingest-change-events...\n");
  const s4 = await stage4IngestChangeEvents(sql, acts, s2.enactIdByActKey, s3.provIdByActKey, s1.docIdByYear);
  process.stderr.write(`        ${s4.rows} change_event rows (${s4.emptyFlagged} empty-text flagged)  ${s4.wallMs.toFixed(1)}ms\n`);

  process.stderr.write("  [5/5] materialize...\n");
  const s5 = await stage5Materialize(sql);
  process.stderr.write(`        ${s5.rows} provision_version rows  ${s5.wallMs.toFixed(1)}ms\n`);

  const totalMs = ms(runT);
  process.stderr.write(`  Run ${runNum} total: ${totalMs.toFixed(1)}ms\n`);

  return {
    run: runNum,
    stages: [
      { stage: "purge",                 rows: 0,            wallMs: s0.wallMs, perUnitMs: 0 },
      { stage: "register-sources",      rows: s1.rows,       wallMs: s1.wallMs, perUnitMs: s1.wallMs / Math.max(1, s1.rows) },
      { stage: "ingest-enactments",     rows: s2.rows,       wallMs: s2.wallMs, perUnitMs: s2.wallMs / Math.max(1, s2.rows) },
      { stage: "ingest-provisions",     rows: s3.rows * 2,   wallMs: s3.wallMs, perUnitMs: s3.wallMs / Math.max(1, s3.rows * 2) },
      { stage: "ingest-change-events",  rows: s4.rows,       wallMs: s4.wallMs, perUnitMs: s4.wallMs / Math.max(1, s4.rows) },
      { stage: "materialize",           rows: s5.rows,       wallMs: s5.wallMs, perUnitMs: s5.wallMs / Math.max(1, s5.rows) },
    ],
    totalMs,
    sourceDocuments: s1.rows,
    enactments: s2.rows,
    provisions: s3.rows,
    changeEvents: s4.rows,
    provisionVersions: s5.rows,
    emptyTextFlagged: s4.emptyFlagged,
  };
}

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------
async function main() {
  process.stderr.write("PatoLex Pre-Code Ingest Benchmark (PROVISIONAL)\n");
  process.stderr.write("================================================\n");
  process.stderr.write("Model: 1850-blank-forward, session-laws primary\n");
  process.stderr.write("trust_level: ocr_uncertain\n\n");

  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL not set — check .env.local");

  logRun("INIT", "precode-ingest-benchmark started", "OK");

  const sql = postgres(url, { max: 5 });

  try {
    process.stderr.write("Loading acts from JSON files...\n");
    const { acts, byYear, emptyCount } = loadAllActs();

    process.stderr.write(`\nInventory:\n`);
    let total = 0;
    for (const [yr, yrActs] of byYear) {
      process.stderr.write(`  ${yr}: ${yrActs.length} acts (${yrActs.filter(a => a.emptyText).length} empty-text)\n`);
      total += yrActs.length;
    }
    process.stderr.write(`  TOTAL: ${total} acts (${emptyCount} empty-text)\n\n`);

    logRun("LOAD", `${total} acts loaded; ${emptyCount} empty-text acts`, "OK");

    const allRuns: RunResult[] = [];
    const docIdByYear = new Map<string, bigint>();

    for (let run = 1; run <= RUNS; run++) {
      logRun(`PRE-RUN-${run}`, "Starting run", "OK");
      const result = await runPipeline(sql, acts, docIdByYear, run);
      allRuns.push(result);
      logRun(`RUN-${run}`, `enactments=${result.enactments} provisions=${result.provisions} changeEvents=${result.changeEvents} provVersions=${result.provisionVersions} totalMs=${result.totalMs.toFixed(0)}`, "OK");
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
    const variance = allRuns.reduce((a, b) => a + (b.totalMs - avgTotal) ** 2, 0) / RUNS;
    const stdDev = Math.sqrt(variance);

    // ---- Print benchmark table ----
    process.stderr.write("\n=== BENCHMARK TABLE (avg of 3 runs) ===\n");
    process.stderr.write("Stage".padEnd(26) + "Rows".padStart(7) + "Avg ms".padStart(10) + "ms/unit".padStart(10) + "\n");
    process.stderr.write("-".repeat(55) + "\n");
    for (const s of avgStages) {
      process.stderr.write(
        s.stage.padEnd(26) +
        s.rows.toString().padStart(7) +
        s.wallMs.toFixed(1).padStart(10) +
        (s.rows > 0 ? s.perUnitMs.toFixed(4) : "n/a").padStart(10) +
        "\n"
      );
    }
    process.stderr.write("-".repeat(55) + "\n");
    process.stderr.write("TOTAL".padEnd(26) + "".padStart(7) + avgTotal.toFixed(1).padStart(10) + "\n");

    process.stderr.write("\n=== PER-RUN TOTALS ===\n");
    for (const r of allRuns) {
      process.stderr.write(`  Run ${r.run}: ${r.totalMs.toFixed(1)}ms\n`);
    }
    process.stderr.write(`  Std dev: ${stdDev.toFixed(1)}ms\n`);

    // ---- Per-year breakdown ----
    const byYearCounts: Array<{ year: string; count: number; emptyText: number }> = [];
    for (const [yr, yrActs] of byYear) {
      byYearCounts.push({ year: yr, count: yrActs.length, emptyText: yrActs.filter(a => a.emptyText).length });
    }

    // ---- ETA extrapolation ----
    // Use ingest-enactments ms/act as the primary per-act rate
    const enactStage = avgStages.find((s) => s.stage === "ingest-enactments")!;
    const ceStage = avgStages.find((s) => s.stage === "ingest-change-events")!;
    const msPerAct = enactStage.perUnitMs;
    const msPerEvent = ceStage.perUnitMs;

    const etaLow3k = (3000 * msPerAct) / 1000; // seconds for 3000 acts
    const etaHigh5k = (5000 * msPerAct) / 1000;

    // ---- Write benchmark JSON ----
    const benchOut = {
      generated_at: new Date().toISOString(),
      label: "PROVISIONAL BENCHMARK — 1850-1871 pre-code session-law sample",
      caution: "Partial coverage (~1,069 acts, 19 volumes). Un-gold-verified Tesseract OCR. trust_level=ocr_uncertain. NOT certified corpus. For pipeline timing / ETA estimation only.",
      model: "1850-blank-forward, session-laws as primary source. No 1872-enact-from-nothing. No Penal Code sections in this run.",
      input: {
        scratch_dir: SCRATCH,
        session_files: SESSION_FILES.length,
        total_acts: total,
        empty_text_acts: emptyCount,
        by_year: byYearCounts,
      },
      runs: allRuns.map((r) => ({
        run: r.run,
        total_ms: parseFloat(r.totalMs.toFixed(2)),
        source_documents: r.sourceDocuments,
        enactments: r.enactments,
        provisions: r.provisions,
        change_events: r.changeEvents,
        provision_versions: r.provisionVersions,
        empty_text_flagged: r.emptyTextFlagged,
        stages: r.stages.map((s) => ({
          stage: s.stage,
          rows: s.rows,
          wall_ms: parseFloat(s.wallMs.toFixed(2)),
          per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
        })),
      })),
      averages: {
        total_ms: parseFloat(avgTotal.toFixed(2)),
        std_dev_ms: parseFloat(stdDev.toFixed(2)),
        stages: avgStages.map((s) => ({
          stage: s.stage,
          rows: s.rows,
          avg_wall_ms: parseFloat(s.wallMs.toFixed(2)),
          per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
        })),
      },
      eta_extrapolation: {
        note: "INGEST is not the bottleneck — OCR is. These figures show ingest time only.",
        ms_per_act_ingest: parseFloat(msPerAct.toFixed(4)),
        ms_per_event_ingest: parseFloat(msPerEvent.toFixed(4)),
        full_precode_corpus_estimate: "~3,000–5,000 acts (ESTIMATE — not yet fully inventoried)",
        eta_3000_acts_seconds: parseFloat(etaLow3k.toFixed(2)),
        eta_5000_acts_seconds: parseFloat(etaHigh5k.toFixed(2)),
        caveat: "Rates measured on localhost single-machine. Larger batches improve throughput. Materialize CTE will need chunking at millions of rows.",
      },
    };

    // Use replacer to handle any stray BigInts
    const replacer = (_key: string, val: unknown) =>
      typeof val === "bigint" ? String(val) : val;

    writeFileSync(BENCHMARK_OUTPUT, JSON.stringify(benchOut, replacer, 2), "utf-8");
    process.stderr.write(`\nBenchmark JSON written to: ${BENCHMARK_OUTPUT}\n`);

    logRun("COMPLETE", `Done. ${total} acts. Avg total ${avgTotal.toFixed(0)}ms over ${RUNS} runs. DB left in run-${RUNS} state.`, "OK");

    // Emit a machine-readable summary to stdout for the final report
    const summary = {
      total_acts: total,
      empty_text_flagged: emptyCount,
      avg_total_ms: parseFloat(avgTotal.toFixed(2)),
      std_dev_ms: parseFloat(stdDev.toFixed(2)),
      per_run_ms: allRuns.map((r) => parseFloat(r.totalMs.toFixed(2))),
      avg_stages: avgStages.map((s) => ({
        stage: s.stage,
        rows: s.rows,
        avg_wall_ms: parseFloat(s.wallMs.toFixed(2)),
        per_unit_ms: parseFloat(s.perUnitMs.toFixed(4)),
      })),
      final_db_counts: {
        source_documents: allRuns[RUNS - 1].sourceDocuments,
        enactments: allRuns[RUNS - 1].enactments,
        provisions: allRuns[RUNS - 1].provisions,
        change_events: allRuns[RUNS - 1].changeEvents,
        provision_versions: allRuns[RUNS - 1].provisionVersions,
      },
      eta: {
        ms_per_act: parseFloat(msPerAct.toFixed(4)),
        eta_3000_acts_s: parseFloat(etaLow3k.toFixed(2)),
        eta_5000_acts_s: parseFloat(etaHigh5k.toFixed(2)),
      },
      by_year: byYearCounts,
    };

    // Print JSON summary to stdout (only line going to stdout, rest is stderr)
    process.stdout.write(JSON.stringify(summary, replacer) + "\n");

  } finally {
    await sql.end();
  }
}

main().catch((err) => {
  process.stderr.write("FATAL: " + String(err) + "\n");
  logRun("FAIL", String(err), "FAIL");
  process.exit(1);
});
