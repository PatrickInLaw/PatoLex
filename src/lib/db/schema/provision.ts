/**
 * provision — the addressable unit of law (domain-neutral, the lineage anchor).
 *
 * The thing with persistent identity across time. Its identity is SYNTHETIC
 * and SURFACE-INDEPENDENT — it survives renumbering, recodification, and
 * transfer across codes. This is the single most important concept in the
 * schema: it is what makes "this is the same section even though it was
 * renumbered in 1943" expressible.
 *
 * Identity design (decided cc002):
 *   id         — bigint identity PK, compact for FK joins across millions of
 *                change_event / provision_version rows. NEVER encodes the
 *                section number (the number changes; identity doesn't).
 *   public_id  — stable external UUIDv7, used in permalinks, cross-corpus
 *                references, and Git metadata headers. The DB default is
 *                uuid_generate_v7() (defined in the migration). The app MAY
 *                supply a v7 value at insert time for bulk-ingest locality;
 *                if omitted, the DB generates one. gen_random_uuid() (v4) is
 *                NOT used. UUIDs do NOT appear in Git file paths (paths use
 *                current designation); the UUID rides in per-file metadata
 *                headers and lineage.json.
 *
 * Designation (section number, code, label) is NOT stored here — it lives in
 * designation_history so the surface label can change without touching the
 * provision row. current_designation is a denormalized convenience field
 * pointing to the latest effective designation string.
 */

import { sql } from "drizzle-orm";
import {
  bigint,
  pgTable,
  text,
  uuid,
} from "drizzle-orm/pg-core";
import { provisionStatusEnum, unitTypeEnum } from "./enums.js";

export const provision = pgTable("provision", {
  /**
   * Surrogate PK — bigint identity. Used for all FK references within the DB.
   * Opaque — never encode the section number here.
   */
  id: bigint("id", { mode: "bigint" })
    .primaryKey()
    .generatedAlwaysAsIdentity(),

  /**
   * Stable external handle — pure UUIDv7 (time-ordered). The SQL default
   * calls uuid_generate_v7() (defined in the migration before this table),
   * which encodes the current millisecond unix timestamp in the high 48 bits,
   * sets the version (7) and variant nibbles, and fills the remainder with
   * random bits. This gives sequential UUIDs during bulk ingest (GiST/btree
   * locality) while remaining globally unique.
   *
   * The app MAY supply a UUIDv7 value at insert time; if omitted, the DB
   * default fires. gen_random_uuid() (v4) is NOT used — it was removed in
   * the adversarial-review revision.
   *
   * Used in: permalinks (/provision/{public_id}), Git metadata trailers,
   * lineage.json manifests, cross-corpus references.
   * NOT used in Git file paths (those use current designation).
   */
  publicId: uuid("public_id").notNull().unique().default(sql`uuid_generate_v7()`),

  /** Jurisdiction code, e.g. "CA". */
  jurisdiction: text("jurisdiction").notNull(),

  /**
   * What kind of legal unit this is.
   * code_section = numbered section in a California code (most common)
   * act_section  = section of an uncodified act (pre-1872 primary)
   * reg_section  = CCR section
   */
  unitType: unitTypeEnum("unit_type").notNull(),

  /**
   * Denormalized convenience: the current (latest) designation string, e.g.
   * "Penal Code § 187". Derived from designation_history; updated during
   * ingest and materialization. May be null for newly-minted provisions before
   * their first designation record is inserted.
   */
  currentDesignation: text("current_designation"),

  /** Lifecycle status of this provision. */
  status: provisionStatusEnum("status").notNull().default("active"),
});
