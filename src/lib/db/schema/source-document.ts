/**
 * source_document — provenance record for every artifact ingested.
 *
 * Tracks the original source (Internet Archive scan, leginfo XML, Chief
 * Clerk PDF, etc.) and its quality metadata. Multiple source_documents
 * can back a single enactment; the trust_level drives disagreement-flagging
 * during QA.
 */

import { sql } from "drizzle-orm";
import {
  bigint,
  boolean,
  doublePrecision,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import { sourceTypeEnum, trustLevelEnum } from "./enums.js";

export const sourceDocument = pgTable("source_document", {
  /**
   * Surrogate PK — bigint identity, compact for FK joins across millions of
   * change_event / provision_version rows.
   */
  id: bigint("id", { mode: "bigint" })
    .primaryKey()
    .generatedAlwaysAsIdentity(),

  /**
   * Class of source artifact (session_law | bill | annotated_edition |
   * scan | regulatory_action | official_xml).
   */
  type: sourceTypeEnum("type").notNull(),

  /**
   * Human-readable citation, e.g. "Stats. 1883 ch. 38" or "SB 123 (2023)".
   */
  citation: text("citation"),

  /**
   * Jurisdiction code, e.g. "CA" or "US".
   */
  jurisdiction: text("jurisdiction").notNull(),

  /**
   * Ingest channel identifier: Internet Archive item ID, Chief Clerk URL,
   * leginfo URL, OLRC URL, etc.
   */
  sourceChannel: text("source_channel"),

  /**
   * Qualitative scan quality indicator (e.g. "good", "poor", "missing").
   * Nullable — only relevant for scanned/OCR'd documents.
   */
  scanQuality: text("scan_quality"),

  /**
   * OCR engine used (e.g. "tesseract-5", "abbyy-12"). Nullable.
   */
  ocrEngine: text("ocr_engine"),

  /**
   * Estimated character error rate from OCR confidence scores. 0–1. Nullable.
   * When non-null, enforced by CHECK: ocr_cer_estimate >= 0 AND ocr_cer_estimate <= 1
   * (hand-edited into migration because Drizzle table-level CHECK support is limited).
   */
  ocrCerEstimate: doublePrecision("ocr_cer_estimate"),

  /**
   * Overall trust level of the source artifact.
   */
  trustLevel: trustLevelEnum("trust_level").notNull(),

  /**
   * When this document was retrieved/ingested. Stored as UTC.
   */
  retrievedAt: timestamp("retrieved_at", { withTimezone: true }),

  /**
   * Clean-channel flag: true = source is IA-non-Google or CA-gov only
   * (suitable for serving text publicly per the licensing analysis).
   * false = do not serve raw text.
   */
  cleanChannel: boolean("clean_channel").notNull().default(false),

  /**
   * SHA-256 hex digest of the artifact's raw bytes (the content-derived
   * identity). UNIQUE — same bytes = same artifact regardless of filename.
   * Content is the authority; this hash anchors provenance independently of
   * filenames or catalog metadata.
   */
  contentSha256: text("content_sha256"),

  /**
   * VERIFIED publication/edition year, read from the artifact's OWN CONTENT
   * (title page, colophon, copyright notice) — NOT the filename or catalog.
   * This is the authoritative edition year stored in the registry.
   */
  editionYear: integer("edition_year"),

  /**
   * What a filename, catalog entry, or acquisition agent asserted about the
   * edition year before verification. Kept to enable claimed-vs-verified
   * mismatch detection. Nullable — omit when provenance was clean from the start.
   */
  claimedYear: integer("claimed_year"),

  /**
   * How edition_year was determined: human-readable evidence trail, e.g.
   * "title page p.3: 'Sacramento, 1872'" or "section text contains
   * '[In effect April 5, 1880.]' — post-1872 amendment language".
   * Nullable — fill in whenever edition_year is set.
   */
  verificationNote: text("verification_note"),

  /**
   * Current filename or relative path to the artifact on disk.
   * CONVENIENCE POINTER ONLY — non-authoritative. The registry (content_sha256)
   * is the identity; this field is a human-readable hint. Auto-derived from
   * --file argument (basename) if not supplied explicitly.
   */
  fileName: text("file_name"),

  /**
   * Exact source locator for the artifact: Internet Archive details URL,
   * Chief Clerk direct file URL, leginfo URL, etc.
   * Distinct from source_channel (which is the repository/channel name,
   * e.g. "Internet Archive" or "CA Assembly Chief Clerk").
   */
  sourceUri: text("source_uri"),

  /**
   * Which body of law this artifact covers.
   * Values: 'penal_code' | 'civil_code' | 'code_civil_procedure' |
   *         'political_code' | 'uncodified_statutes' | 'index' | 'other'
   * Stored as text for domain-neutral flexibility (not a DB enum).
   * Artifact-level — one row = one corpus.
   */
  corpus: text("corpus"),

  /**
   * First year of the span of law the artifact covers.
   * E.g. an 1850 session-law volume = 1850; an 1880 code reprint that
   * incorporates amendments from 1872 forward = 1872 (code origin).
   */
  coverageStartYear: integer("coverage_start_year"),

  /**
   * Last year of the span of law the artifact covers.
   * E.g. an 1880 reprint as-amended-through-1880 = 1880;
   * a single-session volume = same as coverage_start_year.
   */
  coverageEndYear: integer("coverage_end_year"),

  /**
   * Human-readable section number range this artifact covers.
   * E.g. "1-1685", "1-3525", "Penal 1-1620". Nullable.
   */
  sectionRange: text("section_range"),

  /**
   * Total number of pages in the artifact. Nullable.
   * Derived from the actual file (PDF page count, djvu page markers, etc.).
   */
  pageCount: integer("page_count"),

  /**
   * Physical format of the artifact file.
   * Values: 'pdf' | 'ocr_text' | 'parsed_json'
   * Nullable — fill in when known.
   */
  mediaFormat: text("media_format"),

  /**
   * Per-volume OCR consensus statistics (capture-ALL-signals). JSONB so the
   * volume-level quality picture and the pointer to the banked per-token
   * consensus output are persisted, not recomputed. `scan_quality` and
   * `ocr_cer_estimate` columns above hold the headline derived values; this
   * field holds the supporting distribution + provenance. Shape (written by
   * ingest_clean.py):
   *   {
   *     mean_agreement: number|null,    // mean per-page consensus confidence
   *     median_agreement: number|null,  // median per-page consensus confidence
   *     high_count: number,             // pages with confidence > 0.98
   *     med_count: number,              // pages with 0.93 < confidence <= 0.98
   *     low_count: number,              // pages with confidence <= 0.93
   *     engines: string[],              // union of engines seen across pages
   *     n_pages: number,                // pages with usable consensus
   *     consensus_output_path: string   // banked consensus_output.json (Phase C
   *                                     // per-token disagreement substrate)
   *   }
   *
   * H2 (banking order): consensus_output.json is banked by ingest_clean.py ONLY
   * AFTER the volume's DB commit succeeds, so a rolled-back volume never leaves
   * an orphan file pointing at a source_document with no committed rows. The
   * bank step is idempotent (it overwrites), so a later successful re-run
   * re-banks deterministically. ocr_stats.consensus_output_path is set in the
   * same committed txn that produced the events it indexes.
   */
  ocrStats: jsonb("ocr_stats"),
}, (table) => [
  uniqueIndex("uq_source_document_content_sha256")
    .on(table.contentSha256)
    .where(sql`${table.contentSha256} IS NOT NULL`),
]);
