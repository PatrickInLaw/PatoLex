# Canonical re-ingest COMPLETE — version-B (consensus) is the system of record (2026-06-02)

After 4 Hans passes + the pass-3 fix round, the canonical 1850-1875 re-ingest ran clean. The DB now holds the multi-engine **consensus** corpus with every captured signal, replacing the single-engine version-A.

## What ran (in order)
1. **DB backup** — `PatoLex-backups\patolex_pre_reingest_2026-06-02.dump` (pg_dump -Fc, 4.7 MB, 9:00 PT).
2. **1850 root-cause + prep** — 1850 lacked `sha256.txt` because it was the PILOT volume, OCR'd by an earlier pipeline (it alone has a `pages_prep_sauvola/` experiment dir) before sha256 banking was standard. The DB always had the real hash (id=20). Computed the PDF's SHA256 → matched id=20's `content_sha256` (`9ccbe75c…322017b`) exactly → wrote `production-1850/sha256.txt`. Purged the stale skeleton `source_document` id=1 (`acts_1850.json`, 26 rows, NULL sha — a pre-OCR structured-JSON artifact) via the dedup_precheck emergency block (4288→4262 enactments; id=20's 97 acts untouched).
3. **Migrations 0003 + 0004** applied via `npm run db:migrate` (DATABASE_URL = local localhost:5432/patolex). version-A had 0 `(source_document_id, in_act_order)` dups, so the unique index (0004) applied safely up front and additionally guards the re-ingest. drizzle journal now 5 (0000-0004).
4. **Dry-run pre-flight** over all 21 volumes — parsed clean, **planned exactly 4262 acts = the live DB count** (1:1 replacement cross-check), UTF-8 preserved, all signals computed.
5. **Canonical commit** — `ingest_clean.py <21 labels> --commit` (PATOLEX_ALLOW_COMMIT=1). Every volume REPLACED atomically (single txn, purge+reinsert); purged-count == inserted-count for all 21; exit 0.

## Final verified state
- **4262 enactments = 4262 change_events** (version-B). provision_version = 0 (by design — the materialized read model is a separate deferred date-ordered sweep; neither ingest path ever wrote it; matches version-A, no loss).
- **Committed text is 100% multi-engine consensus:** `consensus_method` = token_majority_3 (4057) + token_majority_2 (205), **zero single-engine**.
- **All signals populated:** confident (3424 true / 838 flagged), confidence, `ocr_provenance` jsonb on all 4262 (engines, agreement, page_span w/ derived multi-page aggregation, full per-token `disagreement.low_confidence_tokens` with each engine's candidate — the Phase C substrate); `ocr_stats` on all 21 source_documents.
- **UTF-8 faithful** — § confirmed via codepoint (chr 167) in 334 acts; sample: "§ 1. That the office of State Printer be, and is hereby created…".
- **dedup_precheck: zero duplicate (source_document_id, in_act_order) pairs**; stale id=1 gone; unique index `uq_change_event_src_doc_in_act_order` live.

## 21 volumes (label: acts)
1850:97, 1851:108, 1852:114, 1853:128, 1854:81, 1855:169, 1856:107, 1857:224, 1858:224, 1859:189, 1860:128, 1861:253, 1862:116, 1863:158, 1863-64:238, 1865-66:301, 1867-68:391, 1869-70:254, 1871-72:372, 1873-74:325, 1875-76:285 = **4262**.

## Notes / next
- version-A (single-engine) is preserved in the banked per-page outputs + `AB_CONSENSUS_VS_SINGLE.md`; the re-ingest is idempotent (re-runnable) and reversible from the backup.
- **Deferred (not loss):** materialize `provision_version` read model (date-ordered replay) when the timeline/serving layer is built.
- **Future:** A/B-2 + Phase C (qwen VLM-flagging targeting the persisted low-confidence tokens + crowd correction); the lineage_edge purge (added in pass-4) must be re-verified when 1872 recodification edges land.
