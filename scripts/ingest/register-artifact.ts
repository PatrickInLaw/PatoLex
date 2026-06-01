/**
 * register-artifact.ts — Content-addressed artifact registry tool.
 *
 * Computes the SHA-256 of a file's raw bytes, then inserts or updates a
 * source_document row. Idempotent on content_sha256: re-registering the
 * same bytes updates metadata without creating duplicates.
 *
 * MISMATCH GUARD: if claimed_year is provided and differs from edition_year,
 * this script emits a loud WARNING. Filenames are NOT authoritative — only
 * the VERIFIED edition_year stored in the registry counts.
 *
 * Usage:
 *   npx tsx scripts/ingest/register-artifact.ts \
 *     --file <path>              required: path to artifact file \
 *     --type <source_type>       required: session_law|bill|annotated_edition|scan|regulatory_action|official_xml \
 *     --jurisdiction <code>      required: e.g. CA \
 *     --edition-year <year>      required: VERIFIED year from artifact content \
 *     --verification-note <txt>  required: evidence for edition_year \
 *     --citation <text>          optional: human-readable citation \
 *     --source-channel <name>    optional: repository/channel name, e.g. "Internet Archive" \
 *     --source-uri <url>         optional: exact source locator (IA details URL, Clerk URL, etc.) \
 *     --corpus <name>            optional: penal_code|civil_code|code_civil_procedure|political_code|uncodified_statutes|index|other \
 *     --coverage-start <year>    optional: first year of law span covered by this artifact \
 *     --coverage-end <year>      optional: last year of law span covered by this artifact \
 *     --section-range <range>    optional: e.g. "1-1685" or "Penal 1-1620" \
 *     --page-count <n>           optional: total pages in the artifact \
 *     --media-format <fmt>       optional: pdf|ocr_text|parsed_json \
 *     --file-name <name>         optional: override auto-derived basename for file_name column \
 *     --claimed-year <year>      optional: what filename/catalog claimed (triggers mismatch check) \
 *     --ocr-engine <name>        optional \
 *     --ocr-cer <0-1>            optional: OCR character error rate estimate \
 *     --trust-level <level>      optional: official_xml|human_verified|derived|ocr_uncertain (default: ocr_uncertain) \
 *     --clean-channel            optional flag: mark as clean channel (IA-non-Google / CA-gov) \
 *     --dry-run                  optional: compute hash, show what would be inserted, do not write
 */

import { createHash } from "crypto";
import { readFileSync, statSync } from "fs";
import { basename } from "path";
import { eq } from "drizzle-orm";
import dotenv from "dotenv";

// Load env before importing schema/client (client reads DATABASE_URL lazily but
// drizzle-kit imports can trigger it indirectly in some setups).
dotenv.config({ path: ".env.local" });

import { getDb } from "../../src/lib/db/client.js";
import { sourceDocument } from "../../src/lib/db/schema/index.js";

// ---------------------------------------------------------------------------
// Argument parsing (manual, no dep on yargs/commander)
// ---------------------------------------------------------------------------

interface Args {
  file: string;
  type: string;
  jurisdiction: string;
  editionYear: number;
  verificationNote: string;
  citation?: string;
  sourceChannel?: string;
  sourceUri?: string;
  corpus?: string;
  coverageStart?: number;
  coverageEnd?: number;
  sectionRange?: string;
  pageCount?: number;
  mediaFormat?: string;
  fileName?: string;
  claimedYear?: number;
  ocrEngine?: string;
  ocrCer?: number;
  trustLevel: string;
  cleanChannel: boolean;
  dryRun: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Partial<Args> & { dryRun: boolean; cleanChannel: boolean } = {
    dryRun: false,
    cleanChannel: false,
    trustLevel: "ocr_uncertain",
  };

  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const next = argv[i + 1];

    switch (flag) {
      case "--file":
        args.file = next;
        i++;
        break;
      case "--type":
        args.type = next;
        i++;
        break;
      case "--jurisdiction":
        args.jurisdiction = next;
        i++;
        break;
      case "--edition-year":
        args.editionYear = parseInt(next, 10);
        i++;
        break;
      case "--verification-note":
        args.verificationNote = next;
        i++;
        break;
      case "--citation":
        args.citation = next;
        i++;
        break;
      case "--source-channel":
        args.sourceChannel = next;
        i++;
        break;
      case "--source-uri":
        args.sourceUri = next;
        i++;
        break;
      case "--corpus":
        args.corpus = next;
        i++;
        break;
      case "--coverage-start":
        args.coverageStart = parseInt(next, 10);
        i++;
        break;
      case "--coverage-end":
        args.coverageEnd = parseInt(next, 10);
        i++;
        break;
      case "--section-range":
        args.sectionRange = next;
        i++;
        break;
      case "--page-count":
        args.pageCount = parseInt(next, 10);
        i++;
        break;
      case "--media-format":
        args.mediaFormat = next;
        i++;
        break;
      case "--file-name":
        args.fileName = next;
        i++;
        break;
      case "--claimed-year":
        args.claimedYear = parseInt(next, 10);
        i++;
        break;
      case "--ocr-engine":
        args.ocrEngine = next;
        i++;
        break;
      case "--ocr-cer":
        args.ocrCer = parseFloat(next);
        i++;
        break;
      case "--trust-level":
        args.trustLevel = next;
        i++;
        break;
      case "--clean-channel":
        args.cleanChannel = true;
        break;
      case "--dry-run":
        args.dryRun = true;
        break;
    }
  }

  // Validate required args
  const missing: string[] = [];
  if (!args.file) missing.push("--file");
  if (!args.type) missing.push("--type");
  if (!args.jurisdiction) missing.push("--jurisdiction");
  if (args.editionYear === undefined) missing.push("--edition-year");
  if (!args.verificationNote) missing.push("--verification-note");

  if (missing.length > 0) {
    console.error(
      `[register-artifact] FAIL: Missing required arguments: ${missing.join(", ")}`
    );
    console.error(
      "Usage: npx tsx scripts/ingest/register-artifact.ts --file <path> --type <type> " +
        "--jurisdiction <code> --edition-year <year> --verification-note <text> [options]"
    );
    process.exit(1);
  }

  return args as Args;
}

// ---------------------------------------------------------------------------
// SHA-256 computation
// ---------------------------------------------------------------------------

function sha256File(filePath: string): string {
  const bytes = readFileSync(filePath);
  return createHash("sha256").update(bytes).digest("hex");
}

// ---------------------------------------------------------------------------
// Valid enum values
// ---------------------------------------------------------------------------

const VALID_TYPES = [
  "session_law",
  "bill",
  "annotated_edition",
  "scan",
  "regulatory_action",
  "official_xml",
] as const;

const VALID_TRUST_LEVELS = [
  "official_xml",
  "human_verified",
  "derived",
  "ocr_uncertain",
] as const;

type SourceType = (typeof VALID_TYPES)[number];
type TrustLevel = (typeof VALID_TRUST_LEVELS)[number];

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = parseArgs(process.argv.slice(2));

  // Validate enum values
  if (!VALID_TYPES.includes(args.type as SourceType)) {
    console.error(
      `[register-artifact] FAIL: Invalid --type "${args.type}". ` +
        `Valid values: ${VALID_TYPES.join(", ")}`
    );
    process.exit(1);
  }

  if (!VALID_TRUST_LEVELS.includes(args.trustLevel as TrustLevel)) {
    console.error(
      `[register-artifact] FAIL: Invalid --trust-level "${args.trustLevel}". ` +
        `Valid values: ${VALID_TRUST_LEVELS.join(", ")}`
    );
    process.exit(1);
  }

  // Verify file exists
  try {
    statSync(args.file);
  } catch {
    console.error(`[register-artifact] FAIL: File not found: ${args.file}`);
    process.exit(1);
  }

  // =========================================================================
  // MISMATCH GUARD — fires before touching the DB, so it's visible even in dry-run
  // =========================================================================
  if (
    args.claimedYear !== undefined &&
    args.claimedYear !== args.editionYear
  ) {
    console.error("");
    console.error(
      "╔══════════════════════════════════════════════════════════════════════╗"
    );
    console.error(
      "║  *** EDITION YEAR MISMATCH — FILENAME/CATALOG CLAIM IS WRONG ***    ║"
    );
    console.error(
      "╠══════════════════════════════════════════════════════════════════════╣"
    );
    console.error(
      `║  File          : ${args.file.padEnd(52)} ║`
    );
    console.error(
      `║  Claimed year  : ${String(args.claimedYear).padEnd(52)} ║`
    );
    console.error(
      `║  Verified year : ${String(args.editionYear).padEnd(52)} ║`
    );
    console.error(
      `║  Evidence      : ${args.verificationNote.substring(0, 52).padEnd(52)} ║`
    );
    console.error(
      "╠══════════════════════════════════════════════════════════════════════╣"
    );
    console.error(
      "║  The artifact has been QUARANTINED by filename but is being          ║"
    );
    console.error(
      "║  registered with its VERIFIED edition year. The claimed_year is      ║"
    );
    console.error(
      "║  stored for audit purposes. Do NOT ingest this artifact as the       ║"
    );
    console.error(
      "║  claimed year's baseline text.                                       ║"
    );
    console.error(
      "╚══════════════════════════════════════════════════════════════════════╝"
    );
    console.error("");
  }

  // Compute SHA-256
  console.log(`[register-artifact] Computing SHA-256 for: ${args.file}`);
  const sha256 = sha256File(args.file);
  const sha256Short = sha256.substring(0, 16) + "...";
  console.log(`[register-artifact] SHA-256: ${sha256}`);

  // Derive file_name from path basename if not explicitly supplied
  const fileName = args.fileName ?? basename(args.file);

  const row = {
    type: args.type as SourceType,
    jurisdiction: args.jurisdiction,
    citation: args.citation ?? null,
    sourceChannel: args.sourceChannel ?? null,
    sourceUri: args.sourceUri ?? null,
    corpus: args.corpus ?? null,
    coverageStartYear: args.coverageStart ?? null,
    coverageEndYear: args.coverageEnd ?? null,
    sectionRange: args.sectionRange ?? null,
    pageCount: args.pageCount ?? null,
    mediaFormat: args.mediaFormat ?? null,
    fileName,
    contentSha256: sha256,
    editionYear: args.editionYear,
    claimedYear: args.claimedYear ?? null,
    verificationNote: args.verificationNote,
    ocrEngine: args.ocrEngine ?? null,
    ocrCerEstimate: args.ocrCer ?? null,
    trustLevel: args.trustLevel as TrustLevel,
    cleanChannel: args.cleanChannel,
    retrievedAt: new Date(),
  };

  if (args.dryRun) {
    console.log("[register-artifact] DRY RUN — would upsert row:");
    console.log(JSON.stringify({ ...row, sha256Short }, null, 2));
    console.log("[register-artifact] DRY RUN complete. No DB write.");
    return;
  }

  // =========================================================================
  // Upsert: idempotent on content_sha256
  // =========================================================================
  const db = getDb();

  // Check for existing row with this sha256
  const existing = await db
    .select({ id: sourceDocument.id })
    .from(sourceDocument)
    .where(eq(sourceDocument.contentSha256, sha256))
    .limit(1);

  if (existing.length > 0) {
    const existingId = existing[0].id;
    console.log(
      `[register-artifact] Existing row found (id=${existingId}) — updating metadata.`
    );

    await db
      .update(sourceDocument)
      .set({
        type: row.type,
        jurisdiction: row.jurisdiction,
        citation: row.citation,
        sourceChannel: row.sourceChannel,
        sourceUri: row.sourceUri,
        corpus: row.corpus,
        coverageStartYear: row.coverageStartYear,
        coverageEndYear: row.coverageEndYear,
        sectionRange: row.sectionRange,
        pageCount: row.pageCount,
        mediaFormat: row.mediaFormat,
        fileName: row.fileName,
        editionYear: row.editionYear,
        claimedYear: row.claimedYear,
        verificationNote: row.verificationNote,
        ocrEngine: row.ocrEngine,
        ocrCerEstimate: row.ocrCerEstimate,
        trustLevel: row.trustLevel,
        cleanChannel: row.cleanChannel,
        retrievedAt: row.retrievedAt,
      })
      .where(eq(sourceDocument.contentSha256, sha256));

    console.log(
      `[register-artifact] OK: Updated source_document id=${existingId}`
    );
    console.log(`[register-artifact]   content_sha256 : ${sha256}`);
    console.log(`[register-artifact]   edition_year   : ${args.editionYear}`);
    if (args.claimedYear !== undefined) {
      console.log(`[register-artifact]   claimed_year   : ${args.claimedYear}`);
      if (args.claimedYear !== args.editionYear) {
        console.log(
          `[register-artifact]   MISMATCH       : claimed=${args.claimedYear} vs verified=${args.editionYear}`
        );
      }
    }
  } else {
    console.log(`[register-artifact] New artifact — inserting row.`);

    const inserted = await db
      .insert(sourceDocument)
      .values(row)
      .returning({ id: sourceDocument.id });

    const newId = inserted[0].id;
    console.log(
      `[register-artifact] OK: Inserted source_document id=${newId}`
    );
    console.log(`[register-artifact]   content_sha256 : ${sha256}`);
    console.log(`[register-artifact]   edition_year   : ${args.editionYear}`);
    if (args.claimedYear !== undefined) {
      console.log(`[register-artifact]   claimed_year   : ${args.claimedYear}`);
      if (args.claimedYear !== args.editionYear) {
        console.log(
          `[register-artifact]   MISMATCH       : claimed=${args.claimedYear} vs verified=${args.editionYear}`
        );
      }
    }
  }

  process.exit(0);
}

main().catch((err) => {
  console.error("[register-artifact] FAIL:", err);
  process.exit(1);
});
