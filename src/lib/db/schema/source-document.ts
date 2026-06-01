/**
 * source_document — provenance record for every artifact ingested.
 *
 * Tracks the original source (Internet Archive scan, leginfo XML, Chief
 * Clerk PDF, etc.) and its quality metadata. Multiple source_documents
 * can back a single enactment; the trust_level drives disagreement-flagging
 * during QA.
 */

import {
  bigint,
  boolean,
  doublePrecision,
  pgTable,
  text,
  timestamp,
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
});
