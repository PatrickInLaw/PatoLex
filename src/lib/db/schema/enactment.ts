/**
 * enactment — one act with legal force (the "commit" in the event-sourced model).
 *
 * Maps 1:1 to a Git commit in the law-as-git-repo projection. The
 * chapter_number is the §9605 ordering key used to resolve double-chaptering
 * conflicts when two acts amend the same section in the same session.
 *
 * Three dates are stored for each enactment (all nullable, era-aware):
 *   chaptered_date  — date the Governor signed / Secretary of State filed
 *   effective_date  — date the act took effect as law
 *   operative_date  — date the substantive provisions became operative
 *                     (Gov. Code §9600 modern default: 90 days after chaptering;
 *                      pre-1900 rules differ — store null when unknown)
 * Point-in-time queries key on operative_date. effective ≠ operative is a
 * correctness trap modeled explicitly.
 */

import {
  bigint,
  date,
  integer,
  pgTable,
  text,
} from "drizzle-orm/pg-core";
import { enactmentKindEnum } from "./enums.js";
import { sourceDocument } from "./source-document.js";

export const enactment = pgTable("enactment", {
  /** Surrogate PK — bigint identity. */
  id: bigint("id", { mode: "bigint" })
    .primaryKey()
    .generatedAlwaysAsIdentity(),

  /** FK → source_document.id (the primary source artifact for this act). */
  sourceDocumentId: bigint("source_document_id", { mode: "bigint" }).references(
    () => sourceDocument.id
  ),

  /**
   * Human-readable legal citation, e.g. "Stats. 1883 ch. 38" or
   * "Cal. Code Regs. tit. 2, § 599.859 (2026)".
   */
  citation: text("citation"),

  /** Jurisdiction code, e.g. "CA". */
  jurisdiction: text("jurisdiction").notNull(),

  /**
   * Legislative session identifier, e.g. "2023-2024" or "1883".
   * Maps to the California legislature session number for state statutes.
   */
  session: text("session"),

  /**
   * Legislature number (e.g. 2024 = "85th"). Stored separately from session
   * for precision when session-year ranges overlap.
   */
  legislature: text("legislature"),

  /**
   * Chapter number assigned by the Secretary of State. This is the §9605
   * ordering key: when two acts amend the same section in the same operative
   * period, the higher chapter number prevails (last-chaptered wins).
   * Stored as integer for reliable numeric comparison; nullable for
   * regulatory actions (which have no chapter number).
   */
  chapterNumber: integer("chapter_number"),

  /** Date the Governor signed / Secretary of State chaptered. */
  chapteredDate: date("chaptered_date"),

  /** Date the act took effect as law. */
  effectiveDate: date("effective_date"),

  /**
   * Date the substantive provisions became operative.
   * Point-in-time queries use this date.
   */
  operativeDate: date("operative_date"),

  /** Short descriptive title of the act (from the heading or bill title). */
  title: text("title"),

  /**
   * Bill number for the modern era (1991–present), e.g. "SB 123" or "AB 456".
   * Nullable — not applicable for pre-1991 statutes or regulatory actions.
   * Used in the Git commit trailer and UI citations.
   */
  billNumber: text("bill_number"),

  /** Legal instrument type: statute | recodification | regulatory_action. */
  kind: enactmentKindEnum("kind").notNull(),
});
