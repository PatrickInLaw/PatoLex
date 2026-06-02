# Hans Adversarial Audit — Pass 4 (verify the pass-3 fixes; GO/NO-GO, 2026-06-02)

Pass 4 verified all 9 pass-3 fixes against the ACTUAL code (commit f08fb4b), not the fix report. **VERDICT: GO — with mandatory pre-run data-prep conditions.**

## All 9 fixes VERIFIED real
- **C1 (critical)** — purge is INSIDE the single all-or-nothing txn (`commit_volume` autocommit=False, ONE commit, rollback+raise on any error); no intermediate commit (the purge-then-fail-empty catastrophe is NOT present). EXISTS-skip + ON CONFLICT both gone. Purge order FK-safe child-before-parent; scoping is parameterized and cannot over-delete other volumes.
- **C2/H1** — unique index split into migration `0004`; `0003` is column-adds only; journal + both snapshots consistent (0004.prevId==0003.id). `ON CONFLICT` dropped — safe because post-purge `in_act_order` (enumerate index) is unique within one run; a stray dup would crash→rollback (clean fail-loud).
- **C3** — resolve by `content_sha256` (read from `sha256.txt`, same source the registry hashed), RAISE on 0 or >1; stale-1850 id=1 refusal triggers (lands-on-id=1 OR skeleton-coexists). Defended further by the partial unique index on content_sha256.
- **C4** — no surviving cross-version-stable-identity claim; all mentions are honest disclaimers.
- **C5** — `drizzle/dedup_precheck.sql` real (report + RAISE hard-gate + id=1 detector), idempotent, emergency id=1 purge left commented.
- **M3** — single-engine confidence 0.3333 (not 1.0); multi-engine paths unchanged + deterministic.
- **H3** — per-act confidence aggregated across the derived page span; end-page = next act's later start (can only WIDEN/over-include, never under-count uncertainty); last act handled; `page_span_derived` flagged honestly.
- **M2** — `capture_candidates` byte-identical test asserts equality on genuine multi-engine cases; 9/9 tests pass.
- **H2** — `consensus_output.json` banked AFTER commit (no orphan on rollback).
- **Flagged (a) 1850 sha256:** refusal is genuine fail-loud (RAISE propagates through `main` with no try/except, crashes the run) — NOT a silent skip; no code path marks a failed volume done.
- **Flagged (b) H3 heuristic:** blast radius bounded (over-include one neighbor page only).

## New pass-4 finding (MEDIUM) — FIXED
- **lineage_edge not purged** by C1 (FK → enactment.id, provision.id). Harmless for the 1850-1875 enact-from-nothing run (table empty), but the purge's "ALL prior rows" claim was dishonest and a future recodification (1872+) re-ingest would FK-block. **FIXED:** added `PURGE_LINEAGE_EDGE_SQL` (scoped to edges this doc's enactments caused) as step 0 of `_purge_source_document`, before the enactment/provision deletes. Compiles clean.
- **Minor footnote (NOT fixed — pre-existing, out of scope):** `enactment_params` stamps the same operative_date into chaptered_date + effective_date + operative_date (conflates 3 legally-distinct dates). Existed in version-A; note for a future pass.

## GO — mandatory pre-run data-prep
1. **1850 has NO `sha256.txt`** (every other volume 1851→1875-76 has one) → the resolver correctly REFUSES it. Either generate 1850's sha256 from the same bytes the registry hashed, OR exclude 1850 from this campaign and re-ingest it separately later.
2. **Purge the stale 1850 skeleton source_document id=1** (run `dedup_precheck.sql` section c; if id=1 present, run its commented emergency purge) BEFORE re-ingesting 1850.
3. **Apply order (now enforceable):** apply `0003` columns → run re-ingest for volumes WITH sha256.txt (1851-1875) → run `dedup_precheck.sql`, confirm ZERO dup pairs → apply `0004` (unique index).
4. **Before any future lineage_edge work (1872 recodification):** the lineage_edge purge is now in place (this pass) — re-verify scoping when edges actually land.
