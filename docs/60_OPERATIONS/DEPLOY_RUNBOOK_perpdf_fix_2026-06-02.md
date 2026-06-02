# Deploy Runbook -- Per-PDF Worker Fix (post-1872 Code/amendment stream)

**Date prepared:** 2026-06-02
**Status:** PREPARED. Nothing deployed. Execute on Patrick's go.
**Scope of fix:** Make the OCR workers able to process ANY body PDF per session
(Statutes + Code/amendments + extra-session), not just `<label>_Statutes.pdf`.

---

## What changed (backward-compatible)

A work-item may now carry an OPTIONAL `pdf` field. The PDF resolves as:

```
ARCHIVE / (entry.get("pdf") or f"{label}_Statutes.pdf")
```

Entries WITHOUT `pdf` behave EXACTLY as today. Each work-item keeps its own
unique `label`, which still drives `production-<label>/`, `OCR_COMPLETE.marker`,
`sha256`, and (later) its own `source_document`. A Code volume is a distinct
source document by design.

The 5080 claims remotely via SSH to the 5090's `queue_claim.py`. That claim now
returns the resolved PDF filename as a second token (`CLAIMED <label> <pdf>`) so
the 5080 OCRs the correct local PDF. The 5080 parse is tolerant: it accepts the
new two-token form AND a legacy single-token `CLAIMED <label>` (un-upgraded 5090)
by falling back to `<label>_Statutes.pdf`.

---

## Repo file -> on-box file mapping (VERIFIED identical before edit)

Before editing, the four repo copies were byte-identical (SHA256) to the live
on-box scripts, so these repo copies are drop-in replacements:

| Repo file (corrected) | Deploy to box | On-box path |
|---|---|---|
| `pipeline/5090/queue_worker.py` | 5090 | `C:\Users\patolex\PatoLex-scratch\queue_worker.py` |
| `pipeline/5090/queue_claim.py`  | 5090 | `C:\Users\patolex\PatoLex-scratch\queue_claim.py` |
| `pipeline/5080/queue_worker_5080.py` | 5080 (local) | `C:\Users\PatrickKolasinski\PatoLex-scratch\queue_worker_5080.py` |
| `pipeline/5080/queue_claim.py`  | 5080 (local) | `C:\Users\PatrickKolasinski\PatoLex-scratch\queue_claim.py` |

Notes:
- `pipeline/5090/queue_claim.py` and `pipeline/5080/queue_claim.py` are
  byte-identical (same SHA256 pre- and post-edit). The 5080's local copy is a
  consistency mirror; the claim that actually runs is the one ON the 5090
  (invoked by the 5080 worker over SSH). Deploy the corrected `queue_claim.py`
  to the 5090; refresh the 5080's local mirror for consistency.

---

## PRECONDITION findings (verified 2026-06-02)

- **5090 archive has NO Code PDFs.** `dir` of
  `C:\Users\patolex\PatoLex-scratch\chief-clerk-archive\*.pdf` shows only
  `*_Statutes.pdf`. All five Code PDFs MUST be scp'd UP to the 5090 before any
  5090 worker can claim/OCR them.
- **5080 archive HAS all five Code PDFs** (local OCR there will find them):
  - `1883-84_Code.pdf` (25,916,297 B)
  - `1873-74_Code.pdf` (17,516,970 B)
  - `1875-76_Code.pdf`  (6,715,556 B)
  - `1877-78_Code.pdf`  (6,380,763 B)
  - `1880_Code.pdf`     (19,458,479 B)
- **LEGISLATURE_MAP does NOT yet have the new Code labels.** Ingest will skip
  them (`not in LEGISLATURE_MAP -- skipping`). Ingest is FROZEN now; do NOT add
  entries or run ingest as part of this deploy. See "Before ingest (LATER)".

---

## DEPLOY STEPS (execute on go)

### 0. Pre-flight
- Confirm a maintenance window: deploying mid-OCR is fine (workers pick up the
  new code only between volumes / on next start), but cleanest to deploy during
  the morning backoff when workers are stopped via STOP flags.

### 1. Stage the five Code PDFs on the 5090 archive (scp UP from 5080)
Run from the 5080 (local), one scp per file (no compound commands):

```
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\PatoLex-scratch\chief-clerk-archive\1883-84_Code.pdf" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/chief-clerk-archive/1883-84_Code.pdf
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\PatoLex-scratch\chief-clerk-archive\1873-74_Code.pdf" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/chief-clerk-archive/1873-74_Code.pdf
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\PatoLex-scratch\chief-clerk-archive\1875-76_Code.pdf" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/chief-clerk-archive/1875-76_Code.pdf
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\PatoLex-scratch\chief-clerk-archive\1877-78_Code.pdf" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/chief-clerk-archive/1877-78_Code.pdf
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\PatoLex-scratch\chief-clerk-archive\1880_Code.pdf" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/chief-clerk-archive/1880_Code.pdf
```

Verify (5090): `dir /b C:\Users\patolex\PatoLex-scratch\chief-clerk-archive\*Code*.pdf` lists all five.
(5080 archive already has all five -- no action needed there.)

### 2. Graceful-stop the workers (between-volume drain; never kills in-flight)
- 5090: create `C:\Users\patolex\PatoLex-scratch\STOP_WORKER.flag` (Write/`type nul >`).
  Each of the 3 workers exits between volumes after finishing + marking its current volume.
- 5080: create `C:\Users\PatrickKolasinski\PatoLex-scratch\STOP_5080_WORKER.flag`.
  (Note: the 5080 worker DELETES its STOP flag at startup, so it's safe to leave;
  but stop it first so it isn't mid-volume when you swap the script.)
- Wait until `queue-worker.log` / `worker-5080-run.log` show graceful exit lines.

### 3. Deploy the corrected scripts (scp from the repo)
From the repo machine (the 5080 is the repo host):

```
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\5090\queue_worker.py" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/queue_worker.py
scp -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 "C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex\pipeline\5090\queue_claim.py" patolex@100.70.54.56:C:/Users/patolex/PatoLex-scratch/queue_claim.py
```

For the 5080 (local copy -- use Write tool or `copy`):
- Copy `pipeline\5080\queue_worker_5080.py` -> `C:\Users\PatrickKolasinski\PatoLex-scratch\queue_worker_5080.py`
- Copy `pipeline\5080\queue_claim.py`        -> `C:\Users\PatrickKolasinski\PatoLex-scratch\queue_claim.py`

Verify SHA256 of each on-box file equals the repo file.

### 4. Append the prepared queue entries to the LIVE 5090 queue
- Source: `docs/60_OPERATIONS/prepared-code-queue-entries-2026-06-02.json` (the
  `entries` array).
- Target: `C:\Users\patolex\PatoLex-scratch\production_queue_state.json` on the 5090,
  append into its `volumes` array. Take the queue lock or do it while workers are
  stopped (step 2) to avoid racing the lock.
- Keep the array's overall forward order; the five Code items sort by `year`
  among the existing pending volumes (1873, 1875, 1877, 1880, 1883). The
  1883-84-regular item is the highest-priority NEW item but will be claimed after
  lower-year pending Statutes volumes -- that is correct forward order. If you
  want 1883-84-regular OCR'd ahead of remaining lower-year work, temporarily set
  the competing entries to `held` (never delete) or place 1883-84-regular first
  and accept that the forward-claim still honors `year`. (Forward policy is
  by `year` then array order; adjust `year`/`held` only if you truly want to
  reorder -- do NOT change labels.)

### 5. Restart the workers
- 5090: delete `STOP_WORKER.flag`, then start the 3 workers as usual
  (`python queue_worker.py <id>` x3 via the existing launcher).
- 5080: delete `STOP_5080_WORKER.flag` (it self-clears on start anyway), then
  start `python queue_worker_5080.py 5080-1`.
- Watch the logs: a claim of a Code item should log
  `... START OCR (1883-84_Code.pdf)` (5090) or
  `... START local OCR (1883-84_Code.pdf) on 5080` (5080), proving the `pdf`
  field threaded through claim->run.

### 6. Smoke check
- Confirm `production-1883-84-regular/` (etc.) directories are created per-label,
  distinct from any `production-1883-84/` Statutes dir. Markers/sha256 are
  per-label -- no collision with the Statutes volume of the same year.

---

## Before ingest (LATER -- DO NOT DO NOW; ingest is frozen)

Add the new labels to BOTH ingest maps before ingesting these volumes:
- `pipeline/5080/ingest_from_ocr.py` -> `LEGISLATURE_MAP`
- `pipeline/ingest_clean.py` -> `LEGISLATURE_MAP` (it falls back to
  `(session_label, session_label)` if missing, but add proper entries)

Suggested entries (confirm legislature ordinals / session strings against the
volume title pages before ingest):
```
"1873-74-code":   ("1873-74 Codes",        "20th"),
"1875-76-code":   ("1875-76 Code amend.",  "21st"),
"1877-78-code":   ("1877-78 Code amend.",  "22nd"),
"1880-code":      ("1880 Code amend.",     "23rd extra"),
"1883-84-regular":("1883 Code amend.",     "25th"),
```
Each will become its OWN `source_document` (distinct from the Statutes volume of
the same biennium). This is correct: the Code/amendment volume is a separate
official publication.

---

## Rollback

The change is additive and backward-compatible. To roll back: redeploy the
previous scripts (git has the pre-edit versions) and remove the appended Code
entries from the live queue. Banked OCR for any in-flight/completed Code volume
is preserved by its own `production-<label>/` marker and is never lost.
