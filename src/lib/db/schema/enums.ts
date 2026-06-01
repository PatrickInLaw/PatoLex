/**
 * PatoLex — shared PostgreSQL enums.
 * All enums are defined here and re-exported from the barrel index.
 */

import { pgEnum } from "drizzle-orm/pg-core";

/**
 * The kind of addressable legal unit a provision represents.
 *
 * - code_section      — a numbered section in a California code (most common)
 * - act_section       — a section of an uncodified act (pre-1872 primary)
 * - reg_section       — a section of the California Code of Regulations (CCR)
 */
export const unitTypeEnum = pgEnum("unit_type", [
  "code_section",
  "act_section",
  "reg_section",
]);

/**
 * Lifecycle status of a provision.
 */
export const provisionStatusEnum = pgEnum("provision_status", [
  "active",
  "repealed",
  "reserved",
  "superseded",
]);

/**
 * The action taken by a change_event — what the enactment did to the provision.
 */
export const changeActionEnum = pgEnum("change_action", [
  "enact",
  "amend",
  "repeal",
  "add",
  "renumber",
  "recodify",
  "reserve",
]);

/**
 * The legal instrument that created the enactment.
 */
export const enactmentKindEnum = pgEnum("enactment_kind", [
  "statute",
  "recodification",
  "regulatory_action",
]);

/**
 * The type of artifact represented by a source_document.
 */
export const sourceTypeEnum = pgEnum("source_type", [
  "session_law",
  "bill",
  "annotated_edition",
  "scan",
  "regulatory_action",
  "official_xml",
]);

/**
 * Confidence level of the text / event data.
 * Higher trust = more authoritative source.
 * official_xml > human_verified > derived > ocr_uncertain
 */
export const trustLevelEnum = pgEnum("trust_level", [
  "official_xml",
  "human_verified",
  "derived",
  "ocr_uncertain",
]);

/**
 * The type of lineage relationship between two provisions.
 * See SCHEMA_DESIGN.md §lineage_edge for identity-continuity rules per type.
 */
export const lineageEdgeTypeEnum = pgEnum("lineage_edge_type", [
  "renumber",
  "transfer",
  "split",
  "merge",
  "repeal_reenact",
  "repeal_without_successor",
]);
