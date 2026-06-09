# Ingestion Worklist — post-OCR pass (drafted cc006, 2026-06-08; to be Hans-verified)

> **STATUS UPDATE 2026-06-09 ~07:30 — OCR CAMPAIGN IS COMPLETE & VERIFIED.**
> The 5090 finished all OCR ~**05:13 AM 2026-06-09** (the "01:28 crash" was a `monitor_5090.ps1`
> false alarm — an SSH-poll drop, not a real crash; the box kept writing output until 05:13, proven
> by `page_ocr_results.json` mtimes). Queue: `done=198, pending=0, in_progress=1 (1998-vol6), held=6`.
> Output verified REAL by sampling 9 vols 1995–1999 (1341–2199 pages each, genuine text). **No OCR
> remains; do NOT re-OCR anything.** Two pre-ingest items:
> 1. **1998-vol6** OCR is complete on the **5080** (`production-1998-vol6/ocr_consensus/`, 27 MB,
>    pages 10→2156) — flip its queue flag to `done` and ensure the ingest can reach it (it lives on
>    the 5080, the other done outputs live on the 5090). Do NOT re-OCR.
> 2. **Missing-years gap audit:** queue years span 1862–2000 with gaps (mostly legit biennial
>    non-sessions). Suspicious — verify against the CA session calendar before declaring corpus
>    complete: **both 1901 & 1902, both 1908 & 1909, and the 1950s–60s cluster** (1952/54/56/58/60/62/64).
> Full detail in `SESSION_cc006_..._DualBox.md` → "CORRECTION (CONTINUATION #4)".

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

## ⚠ HANS AUDIT — BLOCKERS & CORRECTIONS (resolve BEFORE the ingest runs)
Hans adversarially verified this worklist against the live DB + 5090 queue. Real blockers found:

**BLOCKERS (break the ingest / the diff as written):**
1. **No `source_document` registrations exist for the 1877–1990 volumes.** `ingest_clean.py` resolves
   by `content_sha256` (from each volume's `sha256.txt`); with no registration it **FAILS LOUD** on
   the first volume ("no source_document with content_sha256 … refusing to ingest"). **Phase 1 needs
   a source_document REGISTRATION step first** — missing from the plan. (Source_document table = 69
   rows, all 1851–2008.)
2. **`ingest_clean.py` `LEGISLATURE_MAP` ends at 1875-76.** Every session 1877–1990 would be committed
   with `legislature = "1877-78"` (the label) instead of the correct ordinal — **silent data
   corruption** (wrong value, no error). **Extend the map to 1990 before ingest.**
3. **Dedup variants span 1927–1965, not 4 years.** 15+ years have competing `vol1` scans, several with
   TWO numbered-chapter variants (1955 `54chapters` vs `55chapters`; 1957 `56` vs `57`; 1959/1961/
   1963/1965 likewise; 1965 has 4 done variants). **No resolution protocol exists** → operator
   improvises 15+ choices → silent double-ingest / wrong scan. **Define a canonical-pick rule per
   (year,vol) before ingest.** NOTE: `1863` vs `1863-64` are DIFFERENT sessions (13th vs 15th Leg) —
   NOT dedup candidates, keep both. `1941-vol1-41chapters` has no `-chapters` sibling — verify.
4. **The "perfect-match" diff is broken by auto-increment ids.** `enactment.id` / `change_event.id` /
   `provision.id` are bigint sequences → every row gets a NEW id after purge+reinsert → a naive
   pg_dump byte-diff flags the ENTIRE corpus as changed. **Diff by LOGICAL key (citation +
   in_act_order), not file/id.** Also normalize `retrieved_at`, JSONB key order in `ocr_provenance` /
   `ocr_stats`, sequence state, and `public_id` (uuid_v7).

**FACTUAL CORRECTIONS to this doc:**
- "69 source_documents" → **67** have enactments; **2 are orphaned** registrations (identify them —
  could collide with the new registration step).
- "Gate F 1991–2024" → **2025 is ALREADY in the DB** (836 enactments, null source_document). So the
  staged 2025 Gate F JSONL may be a **dup/no-op** — verify before re-ingesting 2025 in Phase D.
- "185 done volumes" → **186**.
- "~1862→2000 done" → **1997 is 3/6, 1998 is 1/6, 1999 is 0/5, 2000 held** — OCR 1997–2000 is
  INCOMPLETE; Phase 1 is clean only through ~1996.
- `trust_level='official_xml'` lives on **`change_event`**, not `enactment`.
- **Pre-1850 rows (5):** 1831–1836 retroactive-dated acts in real sessions (e.g. `Stats. 1861 ch.277`
  dated 1831-05-02) — will appear in the backup/diff; acknowledge, don't "fix".
- "no citation collision" (2000–2008 dual layer) — **UNVERIFIED** by Hans; run the collision check.

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

## A.2 STRAY ROOT CAUSE — forensic verdict (cc006): a `chaptered_date` PARSER BUG, not junk
The "strays" are **51 REAL acts with correct text but a wrong `chaptered_date`** (two parser bugs +
1 mislabel). **DO NOT PURGE them — fix the date in place. And FIX THE PARSER *BEFORE* the re-ingest:**
a re-ingest with the current scripts **reproduces the same wrong dates**, so the backup-diff would
"match the bug" instead of catching it. This is the single most important pre-ingest fix.

- **Cluster A — 28 rows (DB years 1879–1895): OCR digit misread.** On the 1855–1870 OCR volumes the
  year in `[Approved … 18XX]` was OCR-corrupted (1855→1895, 1860→1880, 1869→1879…). `parse_act_date()`
  in `pipeline/5080/ingest_from_ocr.py` has **no session-year sanity check** → the corrupted but
  valid year was committed. Acts/session/citation/text are correct; only the date is wrong.
  **Fix:** clamp the parsed year to the source_document `coverage_start/end_year` (≈ session year).
  Recoverable with targeted `UPDATE`s — no re-OCR.
- **Cluster B — 22 rows (DB years 1895–1971): regex date-theft from body text.** In born-digital
  2000–2008, the permissive `APPROVED_RE` runs BEFORE `APPROVED_MODERN_RE` and `finditer` grabs the
  FIRST match — a **historical date reference in the act *body*** (e.g. "initiative measure approved
  June 2, 1913" → a 2000 act dated 1913-06-02; the B&P §473.15 boilerplate identically poisoned 6
  volumes). Bug in `parse_act_date()` in `pipeline/5080/parse_born_digital_prod.py`. **Fix:** use
  `APPROVED_MODERN_RE` (the `[Approved by Governor …]` bracket) only, or add the same ±year clamp.
  Correct date is already in the stored `new_text` — recoverable, no re-parse.
- **Special case — 1 row:** `2003_Vol1 ch.70` date `1993-07-15` is CORRECT (a 1993 act *filed late*
  in 2003); only the `citation`/`session` label (2003) is wrong (should be `Stats. 1993 ch.70`) — an
  artifact of the per-volume session-labeling approach.

**Implications for the backup→purge→re-ingest:** (1) **fix both `parse_act_date()` bugs first**;
(2) add a **permanent ±N-year sanity clamp** in the shared date parser so OCR/body noise can never
mis-date an act again; (3) the re-ingest will then yield CORRECTED dates that *differ* from the buggy
backup for these 51 (+ the 6-volume boilerplate) — expected/good, not a diff failure.

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
