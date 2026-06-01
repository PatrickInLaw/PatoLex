/**
 * designation_history — surface labels over time.
 *
 * Because the displayed citation (section number, code, label) changes
 * over time while the provision_id does not, all designation changes are
 * recorded here. This handles cases like the §634 game-law/plumbing
 * collision (same number, different code, same period) surfaced during the
 * Method-A spike.
 *
 * Each row represents: "provision P was known as §section_number of 'code'
 * (human label: label) during the date interval valid_range."
 *
 * valid_range is a PostgreSQL daterange [start, end) — inclusive start,
 * exclusive end. An open upper bound [start,) means "currently active."
 *
 * NO-OVERLAP CONSTRAINT (enforced by GiST exclusion — hand-edited into migration):
 *   EXCLUDE USING gist (provision_id WITH =, valid_range WITH &&)
 *   This guarantees that no two rows for the same provision_id have overlapping
 *   valid_range values, so any (provision_id, date) pair matches AT MOST one row.
 *   Requires btree_gist (already created). Hand-edited into migration because
 *   Drizzle pg-core cannot express EXCLUDE constraints.
 *
 * Query pattern: "What was the section number of provision P on date D?"
 *   SELECT section_number FROM designation_history
 *   WHERE provision_id = ? AND valid_range @> D::date
 *   -- No ORDER BY / LIMIT needed: the exclusion constraint guarantees at most one match.
 */

import { bigint, index, pgTable, text } from "drizzle-orm/pg-core";
import { daterange } from "./_types.js";
import { provision } from "./provision.js";

export const designationHistory = pgTable(
  "designation_history",
  {
    /** Surrogate PK. */
    id: bigint("id", { mode: "bigint" })
      .primaryKey()
      .generatedAlwaysAsIdentity(),

    /** FK → provision.id. */
    provisionId: bigint("provision_id", { mode: "bigint" })
      .notNull()
      .references(() => provision.id),

    /**
     * Code name, e.g. "Penal Code", "Civil Code", "Cal. Code Regs. tit. 2".
     * Nullable for act_section provisions (not codified).
     */
    code: text("code"),

    /**
     * The section number string as it appeared in the source, e.g. "187",
     * "1170.1", "634". Stored as text to preserve leading zeros and non-numeric
     * designations (e.g. "1" vs "001", alphabetic subdivision suffixes).
     */
    sectionNumber: text("section_number").notNull(),

    /**
     * Full human-readable label, e.g. "Penal Code § 187".
     * Convenient for display; derived from code + section_number but stored
     * to avoid repeated string construction.
     */
    label: text("label"),

    /**
     * Date interval during which this designation was in effect.
     * PostgreSQL daterange: [valid_from, valid_to), open upper = current.
     * GiST index supports overlap queries (does P have this number at date D?).
     */
    validRange: daterange("valid_range").notNull(),
  },
  (t) => [index("idx_designation_history_provision_id").on(t.provisionId)]
);
