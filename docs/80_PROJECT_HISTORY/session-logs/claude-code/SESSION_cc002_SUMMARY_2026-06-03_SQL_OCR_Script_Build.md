# Session Summary: cc002 — SQL OCR Script Build + DB Topology Fix + Cutover Prep

| Field | Value |
|-------|-------|
| Session | cc002 (continuation) |
| Date | 2026-06-03 |
| Agent | Claude Code (Sonnet 4.6) |
| Context | Step 1 SQL pipeline build — replacement OCR script, DB topology correction, cutover preparation |
| Branch | main |

---

## What Was Done

### 1. Fixed schema.sql filtered-index QUOTED_IDENTIFIER error

The previous session created the `PatoLexQueue` database on `PK_Alien_5090\SQLEXPRESS` but table creation failed at line 77 with `Msg 1934: QUOTED_IDENTIFIER incorrect settings`. Root cause: SQL Server requires `SET QUOTED_IDENTIFIER ON` to create filtered indexes. Added `SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;` before the CREATE TABLE block.

### 2. Built `ocr_only_sql.py` — the SQL-pipeline OCR script (runs on any box)

Originally named `ocr_only_5090_sql.py` (wrong — it runs on 5080 and 5090). Renamed to `ocr_only_sql.py`. Built as a NEW replacement file; live `pipeline/5090/ocr_only_5090.py` untouched.

Key changes from the live script:
- **Named args** (`--inbox`, `--midbox`, `--outbox`, `--label`, `--pdf`, `--stage`) — no hardcoded paths
- **`PREP_COMPLETE` marker** written atomically at end of `--stage prep`; checked as a defense-in-depth barrier in `--stage ocr`
- **`--stage ocr` skips STAGES 1–3** — loads `page_classification.json` (includes `total_pages`) and reads `sha256.txt`. No fitz.open in OCR-only runs.
- **OUTBOX_COMPLETE marker** for two-file publish atomicity
- **Per-volume log file** (`SCRATCH/ocr-script.log`) as default
- All preprocessing functions at module level

### 3. Hans pass-1 and pass-2 on `ocr_only_sql.py` — both clean

Pass-1 BLOCKERs: rc=3 not handled in worker (changed to rc=1); preprocessing functions inside conditional block (moved to module level). Three SERIOUS fixed.

Pass-2 BLOCKER: outbox failure exits rc=0 silently (fixed: `_outbox_fail` flag + `sys.exit(1)`). Three SERIOUS fixed (OUTBOX_COMPLETE marker; sha256.txt existence check; json.loads guarded).

### 4. DB topology correction — PatoLexQueue moved to the 3060

PatoLexQueue was wrongly created on the 5090. Correct host is `PK_XPS\SQLEXPRESS` (100.113.254.6, the 3060 file server). Patrick:
- Ran `CREATE DATABASE PatoLexQueue` on the 3060 via Windows auth (local admin)
- Ran `CREATE USER PatitoSync FOR LOGIN PatitoSync; ALTER ROLE db_owner ADD MEMBER PatitoSync` on the 3060
- schema.sql applied remotely via PatitoSync: `ocr_queue` (55 cols), `state_history` (8 cols), 6 filtered indexes confirmed

`PatoLexQueue` on the 5090 still exists (empty, needs to be dropped — 5090 sa password not in secrets file).

### 5. PATOLEX_QUEUE_DSN added to secrets file

`PATOLEX_QUEUE_DSN` added to `PatoLex-secrets.env` pointing at the 3060. schema.sql topology comment corrected (5090 → 3060).

### 6. Live queue snapshot and seed dry run

Pulled live `production_queue_state.json` from the 5090 (29KB — 106 volumes, far beyond the stale repo copy). Saved as `pipeline/sql/live_queue_snapshot.json`.

Seed dry run: 106 volumes, 1862–1975, 78 done, 28 pending, 4 re-queued from in_progress.

### 7. OCR pipeline status discovered

The 5090 JSON workers have been running all night uninterrupted — advanced from 1862 to ~1963 as of this session. The repo `production_queue_state.json` was a stale snapshot. The 5080 JSON worker was working on `1959-vol2-chapters` (2812 pages); hit CUDA OOM on pages 695–696 when PatoAudio sidecars pegged the GPU, recovered, and continued. As of session end: 5080 at page ~900/2812, PatoAudio finished.

### 8. Cutover decision

Decision: cut over to the SQL pipeline now. The 5080 will participate as an OCR-only worker (not kept on the coupled JSON pipeline). Requires SMB shares on the 3060 before cross-box handoff.

---

## Files Changed

### New
- `pipeline/sql/ocr_only_sql.py` — renamed from `ocr_only_5090_sql.py`; SQL-pipeline OCR script (Hans×2 clean)
- `pipeline/sql/live_queue_snapshot.json` — snapshot of live 5090 queue at 2026-06-03 ~21:00 PT
- `C:\Users\PatrickKolasinski\PatoLex-scratch\manifest_1976_2000.json` — 104-entry manifest for 1976–2000 statute volumes (outside repo)
- `C:\Users\PatrickKolasinski\PatoLex-scratch\queue_extend_manifest.py` — appends manifest entries with explicit pdf fields to JSON queue (outside repo); also deployed to 5090

### Modified
- `pipeline/sql/schema.sql` — QUOTED_IDENTIFIER fix; topology comment corrected (DB = 3060)
- `pipeline/sql/queue_worker_sql.py` — references updated from `ocr_only_5090_sql.py` → `ocr_only_sql.py`
- `docs/80_PROJECT_HISTORY/run-logs/cc002-planning-run.log` — progress appended
- `C:\Users\PatrickKolasinski\Documents\PatoLex-secrets.env` — PATOLEX_QUEUE_DSN added (outside repo)

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| DB on 3060, not 5090 | Queue DB co-located with SMB file shares on the 3060 file server |
| 5080 as SQL OCR-only worker | Better than keeping 5080 on coupled JSON pipeline; participates in decoupled architecture from day 1 |
| Cut over now | JSON workers dead/stale; SQL stack ready; no reason to wait |
| `ocr_only_sql.py` (generic name) | Script runs on any box; machine-specific name was wrong |

---

### 9. Queue extended to 2000

Built `manifest_1976_2000.json` (104 statute-content volumes, 1976–2000, 8.2 GB) and `queue_extend_manifest.py` (reads manifest, appends entries with explicit `pdf` field so queue_worker.py resolves correct filenames). Both deployed to 5090 scratch.

Started background SCP transfer of 104 PDFs (8.2 GB) from 5080 archive → 5090 archive; logged to `C:\Users\PatrickKolasinski\PatoLex-scratch\scp_transfer_1976_2000.log`. Once transfer completes, run on 5090:
```
python C:\Users\patolex\PatoLex-scratch\queue_extend_manifest.py C:\Users\patolex\PatoLex-scratch\manifest_1976_2000.json
```

**Note:** 1996 Vol2–5 (5–19 MB) and all 1997–2000 volumes (4–33 MB) are suspiciously small — likely born-digital PDFs, not scanned images. The project data tier boundary is ~1993–94 for OCR. 1996 Vol1 (511 MB) and Vol6 (192 MB) are clearly scanned. 1996 Vol2–5 and 1997–2000 may produce garbage OCR; evaluate when reached.

---

## Open Items at Close

| Item | Priority |
|------|----------|
| SCP transfer 104 PDFs 5080→5090 finishing in background — run queue_extend_manifest.py once done | HIGH |
| Patrick runs SMB share setup on the 3060 (elevated) | HIGH |
| Stop JSON workers on 5090 (set max_workers=0) and 5080 (write STOP_5080_WORKER.flag) | HIGH |
| Seed `PatoLexQueue` for real (seed_ocr_queue.py, not dry-run) | HIGH |
| Start prep supervisor on 5090 | HIGH |
| Start OCR workers on 5090 and 5080 | HIGH |
| Drop `PatoLexQueue` from 5090 (needs 5090 sa password — not in secrets file) | MEDIUM |
| Update ingest process to wait for `OUTBOX_COMPLETE` marker | MEDIUM |
| Evaluate 1996 Vol2-5 and 1997-2000 as born-digital (not OCR-able) when reached | LOW |

---

## Next Session Should Start With

1. Verify SCP transfer completed (`scp_transfer_1976_2000.log` ends with TRANSFER COMPLETE)
2. Run on 5090: `python queue_extend_manifest.py manifest_1976_2000.json` — adds 104 volumes
3. Patrick runs SMB share setup elevated on the 3060
4. Store 3060 SMB credentials on the 5090 (`cmdkey /add:100.113.254.6 /user:... /pass:...`) and 5080
5. Stop JSON workers (5090: write `0` to `max_workers.txt` via SSH; 5080: write `STOP_5080_WORKER.flag`)
6. Seed SQL queue for real: `$env:PATOLEX_QUEUE_DSN = ...; python seed_ocr_queue.py --queue-json pipeline/sql/live_queue_snapshot.json`
7. Start prep workers on 5090; start OCR workers on 5090 and 5080

---

## Lessons Learned

- SQL Server `CREATE INDEX` with a `WHERE` clause (filtered index) requires `SET QUOTED_IDENTIFIER ON`; without it `Msg 1934` fires.
- Exit codes from subprocess scripts must be documented in both the script AND the worker. An rc=3 convention only the script knows about is a silent ops trap.
- On Windows UNC/SMB paths, `Path.replace()` is not atomic across machines due to SMB caching (~10s). Use a completion marker file written last.
- `shutil.copy2` + `tmp.replace(dest)` on UNC can fail with `OSError` if the destination is locked; always retry.
- Always check BOTH the stale repo JSON and the live queue on the worker box — they diverge immediately after any commit.
- Script names should be generic when the script is box-agnostic. Machine-specific names imply machine-specific behavior that isn't there.
