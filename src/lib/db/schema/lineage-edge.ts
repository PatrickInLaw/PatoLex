/**
 * lineage_edge — recodification and renumber lineage as a typed directed graph.
 *
 * What Git rename detection cannot infer, and the genuinely hard modeling
 * problem in the schema. One mechanism handles all scales:
 *   - Rare/huge: 1872 codification (act_sections → code_sections)
 *   - Rare/huge: 1943 Government Code / Political Code dissolution
 *   - Medium:    1992 Family Code (lifted from Civil Code)
 *   - Small:     Single-section renumber, decimal spinoffs (§1170 → §1170.1)
 *
 * Provisions are nodes; recodification creates typed directed edges between
 * predecessor and successor provisions, each edge stamped with the enactment
 * that caused it. A 1943 mega-event is thousands of edges from one enactment;
 * a §1170 spinoff is two edges from another — same table, same query path.
 *
 * IDENTITY-CONTINUITY RULES (per edge_type):
 *   renumber              — keep same provision_id; add designation_history row
 *   transfer              — keep same provision_id (cross-code)
 *   split                 — hybrid: primary successor keeps id; spinoffs get new ids
 *   merge                 — new id (or dominant predecessor's); merge edges from each
 *   repeal_reenact        — new id + "continues" edge (chain technically broke)
 *   repeal_without_successor — predecessor terminated; successor_provision_id = null
 *
 * Identity continuity is an explicit, recorded decision per edge — never inferred.
 *
 * RECURSIVE QUERY — "full history of provision P":
 *   A recursive CTE walks the edge graph to collect all ancestor/descendant
 *   provision_ids, then unions their change_event / provision_version rows.
 *   This traversal is the reason the synthetic stable id exists.
 *
 * Git emit: lineage_edge → git mv + rewrite commits; text_disposition annotates
 * the commit message with the disposition of text across the edge.
 */

import { bigint, boolean, index, pgTable, text } from "drizzle-orm/pg-core";
import { lineageEdgeTypeEnum } from "./enums.js";
import { enactment } from "./enactment.js";
import { provision } from "./provision.js";

export const lineageEdge = pgTable(
  "lineage_edge",
  {
    /** Surrogate PK. */
    id: bigint("id", { mode: "bigint" })
      .primaryKey()
      .generatedAlwaysAsIdentity(),

    /** FK → enactment.id — the act that caused this lineage transition. */
    enactmentId: bigint("enactment_id", { mode: "bigint" })
      .notNull()
      .references(() => enactment.id),

    /** FK → provision.id — the predecessor (source) provision. */
    predecessorProvisionId: bigint("predecessor_provision_id", {
      mode: "bigint",
    })
      .notNull()
      .references(() => provision.id),

    /**
     * FK → provision.id — the successor (target) provision.
     * Null for repeal_without_successor (predecessor terminated, no successor).
     */
    successorProvisionId: bigint("successor_provision_id", {
      mode: "bigint",
    }).references(() => provision.id),

    /** Type of lineage relationship. Determines identity-continuity rules. */
    edgeType: lineageEdgeTypeEnum("edge_type").notNull(),

    /**
     * Description of how the text was disposed across this edge, e.g.:
     * "text transferred unchanged", "text divided at subsection (d)",
     * "originated by split from §1170 (primary successor)".
     * Used in Git commit messages and UI history annotations.
     */
    textDisposition: text("text_disposition"),

    /**
     * Legal-continuity flag for repeal_reenact edges.
     * Set true when the successor provision is the legal continuation of the
     * predecessor (the chain technically broke at repeal, but the substance
     * is continuous — used by the UI to present an unbroken history and by
     * the Git emitter to treat the re-enactment as a modify rather than a
     * delete+create). Null on all other edge types. Per SCHEMA_DESIGN.md.
     */
    continues: boolean("continues"),

    /**
     * Free-form note for human reviewers. Records identity-inheritance
     * judgments, ambiguities, and references to supporting evidence
     * (e.g. history notes in the code, disposition tables).
     */
    note: text("note"),
  },
  (t) => [
    /** Support the recursive CTE traversal (walk from predecessor). */
    index("idx_lineage_edge_predecessor").on(t.predecessorProvisionId),
    /** Support the recursive CTE traversal (walk from successor). */
    index("idx_lineage_edge_successor").on(t.successorProvisionId),
    /** FK support. */
    index("idx_lineage_edge_enactment_id").on(t.enactmentId),
  ]
);
