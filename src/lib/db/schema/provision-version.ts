/**
 * provision_version — materialized read model (the web UI's query side).
 *
 * For each provision, the fully-resolved text valid over a [valid_from, valid_to)
 * daterange, built by folding change_events in sequence order and applying §9605
 * conflict resolution. This is the CQRS read side — never the system of record.
 * The event log (change_event) is always the authoritative source; provision_version
 * is regenerable from it at any time.
 *
 * POPULATION:
 *   provision_version rows are inserted by the Gate-G build/fold step — NOT by
 *   Postgres triggers or MATERIALIZED VIEWs. The table is write-once during each
 *   build run; existing rows are truncated and rebuilt from change_event.
 *
 * POINT-IN-TIME QUERY (zero replay, any date):
 *   SELECT text FROM provision_version
 *   WHERE provision_id = $1 AND valid_range @> $2::date
 *
 * CONSTRAINT (enforced by GiST exclusion — hand-edited into migration):
 *   No two rows for the same provision_id may have overlapping valid_range values.
 *   This guarantees exactly one result for any (provision_id, date) pair.
 *   Constraint: EXCLUDE USING gist (provision_id WITH =, valid_range WITH &&)
 *   Requires: CREATE EXTENSION IF NOT EXISTS btree_gist;
 *   Hand-edited into the migration because Drizzle pg-core cannot express
 *   EXCLUDE constraints. See "HAND-EDITED" sections in migration SQL.
 *
 * FULL-TEXT SEARCH:
 *   fts_vector is a tsvector GENERATED ALWAYS column:
 *     to_tsvector('english', coalesce(text, ''))
 *   Expressed natively in Drizzle via generatedAlwaysAs(..., { mode: 'stored' }).
 *   The GIN index is expressed via .using('gin', ...) so db:generate emits
 *   correct DDL. Both are Drizzle-native and do NOT require hand-editing.
 *
 * ETL/GATE-G INVARIANT (not enforced in DDL — validated in the build layer):
 *   A provision_version row representing a repeal SHOULD have text IS NULL.
 *   This cannot be cleanly checked with a table-level CHECK constraint because
 *   the "repeal" state spans the change_event and provision_version tables.
 *   The build/fold step (Gate G) is responsible for enforcing this invariant.
 *   Do not add a DDL CHECK here; it would require a cross-table join.
 *
 * PROVENANCE:
 *   source_change_event_id — the change_event that produced this version
 *   source_document_id     — the source artifact for additional traceability
 */

import { sql } from "drizzle-orm";
import {
  bigint,
  index,
  pgTable,
  text,
} from "drizzle-orm/pg-core";
import { daterange, tsvector } from "./_types.js";
import { changeEvent } from "./change-event.js";
import { provision } from "./provision.js";
import { sourceDocument } from "./source-document.js";
import { trustLevelEnum } from "./enums.js";

export const provisionVersion = pgTable(
  "provision_version",
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
     * Fully resolved text of the provision valid over valid_range.
     * Null for repealed provisions (no text; the range records when the repeal
     * was in effect so "what existed on date X" queries return null correctly).
     *
     * ETL invariant: repeal rows should have text IS NULL (validated by Gate G,
     * not by a DDL CHECK — see module docstring).
     */
    text: text("text"),

    /**
     * Date interval [valid_from, valid_to) during which this text was the law.
     * Inclusive start, exclusive end. Open upper bound [start,) = currently in force.
     * Queried as: valid_range @> $date::date
     *
     * EXCLUSION CONSTRAINT (not expressible in Drizzle — see migration SQL):
     * No two rows for the same provision_id may overlap:
     *   EXCLUDE USING gist (provision_id WITH =, valid_range WITH &&)
     */
    validRange: daterange("valid_range").notNull(),

    /**
     * tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED
     *
     * The column type is tsvector (custom type from _types.ts). The GENERATED
     * ALWAYS expression is expressed via Drizzle's generatedAlwaysAs() so
     * db:generate emits correct DDL: `tsvector GENERATED ALWAYS AS (...) STORED`.
     * The app MUST NOT write this column.
     */
    ftsVector: tsvector("fts_vector").generatedAlwaysAs(
      sql`to_tsvector('english', coalesce("text", ''))`
    ),

    /** Trust level of this materialized version. */
    trustLevel: trustLevelEnum("trust_level").notNull(),

    /**
     * FK → change_event.id — the specific change event that produced this version.
     * Enables tracing any version back to its source event and thence to its
     * source document and enactment.
     */
    sourceChangeEventId: bigint("source_change_event_id", {
      mode: "bigint",
    }).references(() => changeEvent.id),

    /**
     * FK → source_document.id — additional provenance shortcut.
     * Denormalized from source_change_event_id.source_document_id for
     * efficient provenance lookups without joining through change_event.
     */
    sourceDocumentId: bigint("source_document_id", { mode: "bigint" }).references(
      () => sourceDocument.id
    ),
  },
  (t) => [
    /**
     * B-tree index on provision_id for range-scan before the GiST predicate.
     * The GiST exclusion constraint also creates an index on (provision_id, valid_range)
     * that handles the primary point-in-time lookup pattern efficiently.
     */
    index("idx_provision_version_provision_id").on(t.provisionId),

    /**
     * GIN index on fts_vector for full-text search.
     * Expressed natively via .using('gin', ...) — db:generate emits the correct
     * GIN index DDL. No hand-edit required.
     */
    index("idx_provision_version_fts").using("gin", t.ftsVector),
  ]
);
