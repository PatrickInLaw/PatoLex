# Born-Digital (2000–2024) DB Completeness + Modern DB Access — cc015, 2026-06-20

## DB access (wired 2026-06-20 by the 5080 session)
The modern corpus lives in **PostgreSQL on the 5080**, reachable from the 5090 over **Tailscale** (firewall-restricted to `100.64.0.0/10`, pg_hba `scram-sha-256`). DSN in `C:\github\PatoLex\.env.local` (GITIGNORED) as `DATABASE_URL` / `PATOLEX_PG_DSN` = `postgresql://postgres:postgres@100.108.42.91:5432/patolex` (`100.108.42.91` = the 5080's Tailscale IP; the password is a non-secret `postgres`). Verified: `select count(*) from enactment` → **35,332**, all `kind='statute'`.

Schema (7 tables, event-sourced): `enactment(id, source_document_id, citation, jurisdiction, session, legislature, chapter_number, chaptered_date, effective_date, operative_date, title, bill_number, kind)` + `provision, provision_version, source_document, change_event, designation_history, lineage_edge`.

## Born-digital 2000–2024 completeness — **20,271 / 21,455 = 94.5%**
DB distinct `chapter_number` per year (capped at oracle N) vs the oracle per-year denominator:

| years | completeness | note |
|---|---|---|
| **2000–2008** | **~100%** | db_distinct == oracle_N every year. BUT 2000 & 2005–2008 carry **~2× duplicate enactment ROWS** (Gate-F + born-digital double-ingest) — distinct chapters are correct, the duplicate rows want de-duping. |
| **2009–2024** | **~88–93%** | DB is ~10% short of oracle EVERY year (2022 880/997, 2024 919/1017, 2016 805/893 …). **~1,180 chapters total are not in the DB** across 2009–2024 — a **Gate-F ingest gap** (recent years partially ingested). |

**This is a missing-rows ingest gap, NOT a denominator problem** — the oracle per-year N's are consistent with the DB (2000–2008 match exactly). Closing it = re-running / completing the Gate-F ingest for 2009–2024 from the CA SOS bill-chapters source.

## Early-era DB attribution noise (separate finding)
The DB's 1850–1875 OCR-ingested rows have date/number attribution noise: by `chaptered_date` year, **1860 shows chapters up to 531** — vs the **true 371** (confirmed this session by the Table of Acts AND the official clerk PDF). These are OCR-ingest mis-attributions (phantom / mis-dated chapters), a data-quality cleanup for the early-era DB rows — **independent of the now-validated oracle denominators**.

*Artifacts: `pipeline/analysis/_dbcount.py` (access + schema), `_borncomplete.py` (this measurement). Read-only; oracle untouched by this pass.*
