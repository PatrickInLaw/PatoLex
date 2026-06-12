# Queue Port Plan — JSON-over-SSH → (built, unused) SQL → Postgres

**Status: MARKER / DEFERRED. Do NOT build this yet.** This is the durable record of the queue decision so
we can pick it up cleanly *if and when* new OCR work appears. Written 2026-06-12 (cc007). Decision owner: Patrick.

Cross-refs: `SQL_PIPELINE_DESIGN_2026-06-03.md` (the SQL design, REVISION 2, MSSQL-targeted),
`CC007_RECOVERY_MEMO_2026-06-12.md` §6.1, memory `sql-pipeline-rework-plan`.

---

## 1. Why this exists

The OCR campaign distributed page-OCR work across the 5080 + 5090 boxes via a **work queue**. Three things
exist today, in three different states:

1. **JSON-over-SSH queue — LIVE, but fragile and ad-hoc.** A single `production_queue_state.json` file +
   file-lock + one SSH network round-trip per claim/heartbeat (`queue_claim.py`). It works for a one-time
   campaign but is the wrong thing to keep: a shared mutable JSON file is not a real concurrency primitive,
   every operation pays SSH latency, and it was **built unilaterally without design discussion** when a SQL
   queue was the stated plan. **It must not survive into the open-source repo.**
2. **SQL queue — BUILT, never deployed.** `pipeline/sql/queue_worker_sql.py` (REVISION 2): one generic worker
   parameterized by `--role`, atomic claim, lease + heartbeat + fence token, DSN via `PATOLEX_QUEUE_DSN`.
   Solid design — but it **targets MSSQL** (pyodbc / ODBC Driver 18, `WITH (UPDLOCK, READPAST)`), which was
   tied to a now-unnecessary "stand up MSSQL on the 3060" plan. Never cut over.
3. **Postgres — ALREADY RUNNING.** `localhost:5432/patolex` on the 5080 is live (the corpus DB). Postgres has
   the exact equivalent claim primitive: **`SELECT ... FOR UPDATE SKIP LOCKED`**. So the SQL design ports
   cleanly to Postgres with no new infrastructure — **no MSSQL, no 3060 needed.**

---

## 2. THE DECISION (do not decide solo — this is Patrick's call)

The deciding question is **whether there is future multi-box OCR work** (re-OCR the garbage floor / illegible
pages, new volumes, a re-run with better engines):

- **If YES → port the SQL queue to Postgres.** Retire BOTH the JSON-over-SSH path AND the MSSQL target. One
  DB-backed queue, both boxes connect over the network to `patolex`, no file locks, no SSH-per-op.
- **If NO** (campaign effectively done; remaining work — text cleanup, re-parse, ingest — is all single-box) →
  **archive the WHOLE queue layer** (JSON *and* SQL) to `project-archives/`. It served its purpose. Nothing to
  port; just preserve the history.

Either way: **the JSON-over-SSH protocol does not ship to open-source.**

---

## 3. IF we port to Postgres — the concrete plan (NOT YET)

The SQL design already exists; porting is mechanical, MSSQL→Postgres dialect:

1. **Driver:** `psycopg` (v3) instead of pyodbc. DSN from `PATOLEX_QUEUE_DSN` (default to the same
   `localhost:5432/patolex`, or a dedicated queue DB/schema).
2. **Claim primitive:** replace `WITH (UPDLOCK, READPAST)` with
   ```sql
   UPDATE ocr_queue SET status='claimed', worker=%s, lease_until=now()+interval '%s seconds', fence=fence+1
   WHERE id = (SELECT id FROM ocr_queue
               WHERE status='pending' AND role=%s
               ORDER BY priority, id
               FOR UPDATE SKIP LOCKED
               LIMIT 1)
   RETURNING id, fence;
   ```
3. **Lease / heartbeat / fence:** keep REVISION 2's model verbatim — `lease_until` timestamp, periodic
   heartbeat extends the lease, a reaper requeues expired leases, the **fence token** (monotonic per item)
   lets a slow worker detect it was reaped and abort a stale write. All expressible in Postgres unchanged.
4. **Schema:** one `ocr_queue` table (id, role, status, worker, priority, lease_until, fence, payload jsonb,
   timestamps). Statuses mirror the JSON ones incl. the 5090's `prepped` (the prep→ocr two-role split).
5. **Worker:** the existing generic `--role` worker (prep / ocr) — see §4 forensics for which file is canonical.
6. **Retire:** move `queue_claim.py` + `production_queue_state.json` + the MSSQL `queue_worker_sql.py` to
   `project-archives/superseded-pipeline/queue/`. The Postgres worker becomes the only queue code.
7. **Config:** DSN via env (`PATOLEX_QUEUE_DSN`), consistent with `config.py`'s single-source approach. The
   queue is a *service endpoint*, not a filesystem location, so it stays an env var, not a `path_for` entry
   (see config.py's note on non-filesystem protocols).

---

## 4. Forensics (settled, for the record)

- `pipeline/5090/queue_worker.py` = **canonical production worker** — evolved to the prep/ocr two-role model at
  commit `445bea1` (6/3), used in the 6/8 dual-box restore.
- `pipeline/5090-scale/queue_worker.py` = **frozen 6/2 single-role experiment** (ReadOnly), superseded.
- The two `queue_claim.py` copies (5080 / 5090) differ by ONLY the config edit + the 5090's
  `claimable = status in ("pending","prepped")` line.

**HELD: the `queue_claim` unification.** Patrick had asked to unify on the 5090 "prepped" version, but unifying
a layer we may retire is wasted polish — so it is intentionally NOT done, pending this decision.

---

## 5. Open-source note

Of the four target repos, the queue belongs (if it survives at all) in the **OCR toolset** repo as the
DB-backed coordinator. The JSON-over-SSH protocol is explicitly excluded — it was campaign scaffolding, not a
design we'd stand behind publicly.
