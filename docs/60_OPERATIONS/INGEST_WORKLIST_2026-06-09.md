# Ingestion Worklist — post-OCR pass (drafted cc006, 2026-06-08; to be Hans-verified)

**Operator note:** ingestion runs **on the 5090** (64 GB beasty CPU; ingest is light work) and
connects to the **patolex PostgreSQL DB on the 5080** over Tailscale (`PGHOST=100.108.42.91`). It
is **supervised (Opus + Patrick), run tomorrow AM, never automatically.**

## STRATEGY (Patrick, 2026-06-08): backup → purge → full chronological re-ingest → diff
1. **Back up** the DB (pg_dump) — the safety net + the comparison baseline.
2. **Purge** the ingested data (truncate enactment/provision/change_event/designation_history/
   source_document; keep schema).
3. **Re-ingest ALL data in proper chronological order** (1850 → present), OCR then Gate F.
4. **Diff** the freshly-ingested DB against the backup. A mismatch ⇒ something went wrong — a
   cheap, strong sanity check that the ingest is deterministic and lossless.

**⚠ CAVEAT (flag for tomorrow):** the *current* DB (hence the backup) is **missing 1877–1990**
(only stray rows). A full re-ingest that also fills 1877–1990 will be a **SUPERSET** of the
backup, NOT a byte-for-byte match. So the diff must be framed as: **"every backup row reappears
unchanged (containment) AND the overlap years are identical"** — the 1877–1990 gap-fill is
expected net-new. A strict "perfect match" only holds if you re-ingest *exactly* the prior inputs
(determinism check) and add the gap separately. Decide which before running.

This doc = the chronological plan + exact what-to-ingest / skip / dedup, for Hans to verify
against DB + OCR-output reality.

## A. Already ingested — DO NOT re-ingest (verified via live DB, 2026-06-08)
- **OCR session laws 1850–1876** — dense `source_document`-linked enactments (90–395/yr); 69 source_documents.
- **2000–2008** — dense OCR-linked enactments (725–1,171/yr) = the born-digital Chief Clerk extracts already loaded.
- **Gate F (modern XML) 1991–2024 minus gaps** — 22,780 enactments, 14 two-year sessions
  (1991-92, 1995-96, 1997-98, 1999-2000, 2005-06 … 2023-24), `trust_level='official_xml'`.

## A.1 STRAY rows to review/clean (Patrick flag, 2026-06-08)
The per-year OCR-linked counts show **anomalous stray enactments scattered across 1877–1999** —
tiny counts (1–8/yr): e.g. 1879:5, 1880:8, 1881:1, 1882:2, 1883:1, 1885:1, 1886:3, 1888:7,
1895:2, 1905:2, 1911:1, 1913:7, 1914:1, 1933:1, 1934:2, 1944:1, 1954:4, 1965:1, 1971:1, **1993:1**.
These are `source_document`-linked, so they came from the OCR ingest path — almost certainly
**partial/aborted prior ingest fragments or mis-dated rows**, NOT real coverage (those years are
otherwise empty). **Review their origin** (which source_document / run produced them). They are a
hazard for the backup→re-ingest diff: they're in the backup but a clean re-ingest will produce the
*full, correct* set for those years, so the diff will (correctly) flag them. **Purge wipes them;**
the review is to understand how partial ingests happened (and confirm no good data is among them
before purge).

## B. Phase 1 — OCR ingest (the real gap): **1877–1990**
The 5090 campaign OCR'd ~1862→2000 (185 `done` volumes). The DB has only stray counts for
1877–1999, so **1877–1990 is the un-ingested OCR-only span** (no Gate F before 1991). Ingest
these chronologically via the canonical `ingest_clean.py` path.

**Scope = `done` volumes whose leading year is 1877–1990.** (Spot list, not exhaustive — Hans to
enumerate from the live queue: 1877-78, 1880, 1881, 1883-84, 1885-86, 1887, 1889, 1891, 1893,
1895, 1897, 1899, 1900-01, 1903, 1905, 1906-07, 1907-09, 1910-11, 1913-statutes, 1915→1990
vol/chapter volumes.)

**MANDATORY caveats Hans must check before any ingest:**
1. **EXCLUDE 1862–1876 done-volumes** — those years are ALREADY ingested (1850–1876 dense). The
   5090 re-OCR'd them; ingesting again would duplicate. Confirm the ingest path is keyed so it
   skips/does-not-duplicate already-present years.
2. **DEDUPE variant labels** — the done set has multiple labels for the same physical volume, e.g.
   `1927-vol1-26chapters` vs `1927-vol1-chapters`; `1929-vol1-28chapters` vs `-29chapters`;
   `1935-vol1-34chapters` vs `-chapters`; `1943-vol1-42chapters` vs `-chapters`; etc. Pick ONE
   canonical per (year, vol); do not ingest both.
3. **Confirm `ingest_clean.py` idempotency / dedup key** (citation? source_document SHA?) so a
   re-run or an overlapping year cannot double-insert.
4. **OCR output completeness** — each worklisted volume must have a non-trivial
   `production-<label>/ocr_consensus/page_ocr_results.json` (and consensus_output.json) on the 5090.

## C. Overlap zone 1991–2000 (OCR ⟂ Gate F) — DECISION NEEDED
- Gate F covers 1991-2000; the OCR campaign also OCR'd 1991-2000. Per Patrick: **Gate F is
  authoritative** for the overlap; OCR is the **seam-validation oracle**.
- The DB already tolerates dual layers (2000–2008 has both, no citation collision: OCR
  `Stats. YYYY_VolN ch.NNN` vs Gate F `CA YYYY Ch.N`).
- **Recommended:** ingest 1991–2000 OCR as a **parallel OCR layer** (consistent with 2000–2008),
  let the query/publish layer pick Gate F when both exist. Alternative: skip 1991–2000 OCR ingest
  entirely (Gate F suffices) and keep the OCR only as the seam-check. **Hans/operator to confirm
  which.** Either way it does NOT change Phase 1 (1877–1990).

## D. Phase 2 — Modern (Gate F) ingest: the 5 staged sessions
- Parsed + **staged on the 5090** (`gate_f_out/gate_f_{1989,1993,2001,2003,2025}_actions.jsonl`,
  51,834 actions). Idempotent (keyed by citation `CA YYYY Ch.N`).
- `python ingest_gate_f.py <gate_f_out> --years 1989 1993 2001 2003 2025 --commit`
  → fills Gate F gaps (1993-94, 2001-02, 2003-04) + extends to **current (2025-26)** = gap-free 1989→2026.

## E. DB-over-Tailscale (what makes ingest-on-5090 work) — see session log for the verified setup
- DB host: 5080 `100.108.42.91:5432`, db `patolex`, user `postgres`.
- 5090 ingest env: `PGHOST=100.108.42.91 PGPORT=5432 PGDATABASE=patolex PGUSER=postgres PGPASSWORD=…`
  (or `PATOLEX_PG_DSN`). Requires: 5080 Postgres `listen_addresses` incl. the Tailscale IP,
  `pg_hba.conf` allowing 100.70.54.56 → patolex, and Windows firewall inbound 5432 from
  100.64.0.0/10. **Connectivity to be tested + documented (this session).**

## F. NOT in this pass (deferred)
- `provision_version` / `lineage_edge` materialize sweeps (both 0 — read-model build).
- 1872 / 1943 recodification `lineage_edge` modeling.
- Human-gold OCR CER certification.
