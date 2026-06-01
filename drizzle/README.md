# drizzle/ — Migration Files

This directory contains Drizzle-kit generated SQL migrations plus hand-edited
sections for DDL features that Drizzle cannot express.

---

## Hand-Edited Sections in the Migration

Search for `HAND-EDITED` in `0000_wandering_shinobi_shaw.sql` to locate these.

### 1. `CREATE EXTENSION btree_gist` (before all DDL)

Drizzle cannot emit `CREATE EXTENSION` statements. The `btree_gist` extension
is required to build a combined GiST index over a `bigint` column (provision_id)
and a range column (valid_range) — which is what both EXCLUDE constraints need.
This line must appear BEFORE all table DDL.

### 2. `uuid_generate_v7()` function (before the `provision` table)

PostgreSQL has no built-in UUIDv7 generator. The migration defines a
`uuid_generate_v7()` plpgsql function that encodes the current millisecond
unix timestamp in the high 48 bits, sets the version (7) and variant nibbles,
and fills the remainder with random bits. This function must be created BEFORE
the `provision` table so the column default reference resolves.

The `provision.public_id` column default is `uuid_generate_v7()`. The Drizzle
schema expresses this as `.default(sql\`uuid_generate_v7()\`)`.

### 3. GiST exclusion constraint on `provision_version`

```sql
ALTER TABLE "provision_version"
  ADD CONSTRAINT "provision_version_provision_id_valid_range_excl"
  EXCLUDE USING gist (provision_id WITH =, valid_range WITH &&);
```

Drizzle pg-core cannot express `EXCLUDE USING gist` constraints. This
constraint guarantees that no two `provision_version` rows for the same
`provision_id` may have overlapping `valid_range` values — enforcing exactly
one result for any `(provision_id, date)` point-in-time query.

### 4. GiST exclusion constraint on `designation_history`

```sql
ALTER TABLE "designation_history"
  ADD CONSTRAINT "designation_history_provision_id_valid_range_excl"
  EXCLUDE USING gist (provision_id WITH =, valid_range WITH &&);
```

Same no-overlap guarantee as `provision_version`, applied to designation labels.
Guarantees that a `(provision_id, date)` lookup returns at most one designation.

### 5. CHECK constraint on `source_document.ocr_cer_estimate`

```sql
ALTER TABLE "source_document"
  ADD CONSTRAINT "source_document_ocr_cer_estimate_check"
  CHECK (ocr_cer_estimate IS NULL OR (ocr_cer_estimate >= 0 AND ocr_cer_estimate <= 1));
```

Drizzle's table-level `check()` API works but does not emit the constraint
inline in the `CREATE TABLE` DDL for all versions — hand-editing is safer and
more explicit here.

### 6. `DEFERRABLE INITIALLY DEFERRED` on self-referential FKs in `change_event`

The three self-referential FKs on `change_event` (`supersedes_id`,
`superseded_by_id`, `double_jointed_with_id`) are made deferrable:

```sql
ALTER TABLE "change_event"
  ALTER CONSTRAINT "change_event_supersedes_id_change_event_id_fk"
  DEFERRABLE INITIALLY DEFERRED;
-- (repeated for superseded_by_id, double_jointed_with_id)
```

This removes the bidirectional-delete trap: rows that reference each other can
be inserted/deleted within a single transaction without ordering problems.
Drizzle does not support `DEFERRABLE` on FK definitions.

---

## What Drizzle Emits Natively (No Hand-Edit Needed)

After the adversarial-review revision, the following are fully Drizzle-native:

- `provision_version.fts_vector` — expressed via `generatedAlwaysAs(sql\`to_tsvector('english', coalesce("text", ''))\`, { mode: 'stored' })`.
  Drizzle 0.45+ emits correct `GENERATED ALWAYS AS ... STORED` DDL.
- `idx_provision_version_fts` — expressed via `.using('gin', t.ftsVector)`.
  Drizzle 0.45+ emits `CREATE INDEX ... USING gin`.
- `provision.public_id` default — expressed via `.default(sql\`uuid_generate_v7()\`)`.

---

## Regeneration Caveat

When you run `npm run db:generate` after a schema change, Drizzle regenerates
the migration SQL from scratch. The hand-edited sections listed above will NOT
be present in the new migration — you must re-apply them.

**Checklist after each regeneration:**

1. Add `CREATE EXTENSION IF NOT EXISTS btree_gist;` at the top (before all DDL).
2. Add the `uuid_generate_v7()` function before the `provision` table.
3. Add the GiST EXCLUDE constraint on `provision_version`.
4. Add the GiST EXCLUDE constraint on `designation_history`.
5. Add the CHECK constraint on `source_document.ocr_cer_estimate`.
6. Add `DEFERRABLE INITIALLY DEFERRED` to the three self-referential FKs on
   `change_event` (`supersedes_id`, `superseded_by_id`, `double_jointed_with_id`).
7. Verify that `fts_vector` was emitted as `GENERATED ALWAYS AS ... STORED`
   (should be, because it is Drizzle-native now).
8. Verify that `idx_provision_version_fts` was emitted as `USING gin`
   (should be, because it is Drizzle-native now).

Mark each section with a `-- HAND-EDITED (N): ...` comment so future reviewers
can find them instantly.

---

## Population of provision_version and designation_history

Neither `provision_version` nor `designation_history` is a PostgreSQL
`MATERIALIZED VIEW`. They are ordinary tables populated by the Gate-G
build/fold step:

- `provision_version` rows are built by folding `change_event` rows in
  `(operative_date, enactment.chapter_number, in_act_order)` order, applying
  §9605 conflict resolution, and writing the resolved intervals.
- `designation_history` rows are built from the enactment/parsing pipeline.

Both tables are truncated and rebuilt during each Gate-G run. Do not write to
them from application code.
