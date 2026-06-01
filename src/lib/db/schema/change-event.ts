/**
 * change_event — the heart of the event-sourced model (append-only log).
 *
 * One enactment's effect on one provision. This is the write side of CQRS:
 * the system of record. Rows are NEVER updated or deleted — only appended.
 *
 * Because California statutes restate the ENTIRE section on amendment,
 * new_text carries the complete new text for every non-repeal event. This
 * means deriving a version is SELECTION (latest event ≤ date), not REPLAY
 * of accumulated diffs.
 *
 * SEQUENCE (§9605 ordering):
 *   The canonical §9605 ordering tuple is:
 *     (operative_date, enactment.chapter_number, in_act_order)
 *   — documented here and used by the fold/materialize step, which sorts
 *   change_events by this tuple via a JOIN to enactment. No packed key is
 *   stored; the three source values are sufficient and unambiguous.
 *     1. operative_date — chronological order of effect
 *     2. enactment.chapter_number — higher chapter wins within the same
 *        operative period (§9605 last-chaptered-wins rule)
 *     3. in_act_order — 0-indexed position of this change within the
 *        enactment's section list (disambiguates two changes from the same act)
 *   Late-arriving events require a full re-fold of provision_version (not
 *   incremental). See SCHEMA_DESIGN.md §change_event for rationale.
 *
 * RESOLUTION METADATA (double-chaptering):
 *   supersedes_id      — if this event superseded an earlier event on the same
 *                        provision in the same session (higher chapter number)
 *   superseded_by_id   — set on the older event when it is superseded
 *   double_jointed_with_id — both events amended the same section in the same
 *                        session; resolution produced a "double-jointed" merged text
 *   chaptered_out      — true if this event was rendered ineffective because a
 *                        later chapter replaced the same section (§9605)
 *
 * DIFF:
 *   diff_from_prior stores a precomputed token-level structured diff as JSONB:
 *   [{ op: "equal"|"insert"|"delete", tokens: string[] }, ...]
 *   Punctuation-aware; enables legislative redline rendering without running
 *   a diff engine per page view. The first enact event has no prior → all tokens
 *   are "insert". A pure renumber has an empty diff with op="equal" only.
 *   Cross-split diffs may be labeled "originated by split from §X" rather than
 *   forcing a misleading whole-section redline.
 */

import {
  AnyPgColumn,
  bigint,
  boolean,
  date,
  index,
  integer,
  jsonb,
  pgTable,
  text,
} from "drizzle-orm/pg-core";
import { changeActionEnum, trustLevelEnum } from "./enums.js";
import { enactment } from "./enactment.js";
import { provision } from "./provision.js";
import { sourceDocument } from "./source-document.js";

export const changeEvent = pgTable(
  "change_event",
  {
    /** Surrogate PK — bigint identity. */
    id: bigint("id", { mode: "bigint" })
      .primaryKey()
      .generatedAlwaysAsIdentity(),

    /** FK → enactment.id — which act caused this change. */
    enactmentId: bigint("enactment_id", { mode: "bigint" })
      .notNull()
      .references(() => enactment.id),

    /** FK → provision.id — which provision was changed. */
    provisionId: bigint("provision_id", { mode: "bigint" })
      .notNull()
      .references(() => provision.id),

    /** What the enactment did to the provision. */
    action: changeActionEnum("action").notNull(),

    /**
     * Full replacement text of the provision after this change.
     * Null for repeal events (the section no longer exists).
     * CA statutes always restate the entire section, so this is always the
     * complete new text — never a patch or fragment.
     */
    newText: text("new_text"),

    /**
     * Date this change became operative (Gov. Code §9600 rules).
     * Point-in-time queries use this date (not chaptered_date or effective_date).
     * Nullable for era-ambiguous events where the date is not determinable.
     */
    operativeDate: date("operative_date"),

    /**
     * 0-indexed position of this change within its enactment's section list.
     * Used as the third element of the §9605 ordering tuple:
     *   (operative_date, enactment.chapter_number, in_act_order)
     * The fold/materialize step sorts by this tuple via a JOIN to enactment.
     * Disambiguates two change_events from the same enactment affecting the
     * same provision (e.g. an amend followed by a corrigendum in one act).
     */
    inActOrder: integer("in_act_order").notNull(),

    /**
     * Self-FK: if this event superseded an earlier event on the same provision
     * in the same session (higher chapter number wins — §9605).
     * Null if this event did not supersede any earlier event.
     */
    supersedesId: bigint("supersedes_id", { mode: "bigint" }).references(
      (): AnyPgColumn => changeEvent.id
    ),

    /**
     * Self-FK: set on the older event when it is superseded by a later chapter.
     * Null if this event was not superseded.
     */
    supersededById: bigint("superseded_by_id", { mode: "bigint" }).references(
      (): AnyPgColumn => changeEvent.id
    ),

    /**
     * Self-FK: both events amended the same section in the same session;
     * a "double-jointed" merged text was produced by applying both amendments.
     * Set on both events in the pair. Null if no double-jointing.
     */
    doubleJointedWithId: bigint("double_jointed_with_id", {
      mode: "bigint",
    }).references((): AnyPgColumn => changeEvent.id),

    /**
     * True if this event was rendered ineffective because a later chapter
     * replaced the same section (§9605 chaptered-out rule). The row is kept
     * for audit and lineage; it is excluded from provision_version reads.
     */
    chapteredOut: boolean("chaptered_out").notNull().default(false),

    /**
     * Precomputed token-level structured diff from the prior event's text.
     * Schema: [{ op: "equal"|"insert"|"delete", tokens: string[] }, ...]
     * Enables legislative redline rendering without running diff at query time.
     * Null until the ETL diff pass populates it.
     */
    diffFromPrior: jsonb("diff_from_prior"),

    /** FK → source_document.id — provenance of this specific change. */
    sourceDocumentId: bigint("source_document_id", { mode: "bigint" }).references(
      () => sourceDocument.id
    ),

    /**
     * Page or location reference within the source document (e.g. "p. 42",
     * "col. 2", XML element ID). Free-form text for human traceability.
     */
    pageRef: text("page_ref"),

    /** Trust level of this event's text. */
    trustLevel: trustLevelEnum("trust_level").notNull(),
  },
  (t) => [
    /**
     * Primary query pattern: "all change events for provision P, ordered by
     * operative date" — used to build provision_version rows during ETL and
     * to render history views.
     */
    index("idx_change_event_provision_date").on(t.provisionId, t.operativeDate),

    /** FK support index. */
    index("idx_change_event_enactment_id").on(t.enactmentId),
  ]
);
