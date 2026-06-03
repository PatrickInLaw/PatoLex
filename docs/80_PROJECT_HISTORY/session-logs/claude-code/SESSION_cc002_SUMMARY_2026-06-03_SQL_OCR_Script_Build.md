# Session Summary: cc002 — SQL OCR Script Build

| Field | Value |
|-------|-------|
| Session | cc002 (continuation) |
| Date | 2026-06-03 |
| Agent | Claude Code (Sonnet 4.6) |
| Context | Step 1 SQL pipeline build — replacement OCR script for queue worker |
| Branch | main |

---

## What Was Done

### 1. Fixed schema.sql filtered-index QUOTED_IDENTIFIER error

The previous session created the `PatoLexQueue` database on `PK_Alien_5090\SQLEXPRESS` but table creation failed at line 77 with `Msg 1934: QUOTED_IDENTIFIER incorrect settings`. Root cause: SQL Server requires `SET QUOTED_IDENTIFIER ON` to create filtered indexes. Added `SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;` before the CREATE TABLE block. Also corrected the topology comment (DB host is the 5090, not the 3060).

Schema re-apply requires running sqlcmd manually (Patrick task — credentials blocked auto-apply).

### 2. Built `ocr_only_5090_sql.py` — the SQL-pipeline replacement OCR script

Per Patrick's direction: build as a NEW replacement file (`pipeline/sql/ocr_only_5090_sql.py`), leave the live production script (`pipeline/5090/ocr_only_5090.py`) completely untouched. Test the replacement, then slide it in.

Key changes from the live script:
- **Named args** (`--inbox`, `--midbox`, `--outbox`, `--label`, `--pdf`, `--stage`) so the SQL queue worker can invoke it without hardcoded paths
- **`PREP_COMPLETE` marker** written atomically at end of `--stage prep`; checked as a defense-in-depth barrier in `--stage ocr`
- **`--stage ocr` skips STAGES 1–3 entirely** — loads `page_classification.json` (which includes `total_pages`) and reads `sha256.txt` instead of re-opening the PDF. Eliminates the fitz.open cost in OCR-only runs.
- **OUTBOX_COMPLETE marker** for two-file publish atomicity — `page_ocr_results.json` and `page_classification.json` are both written to outbox before the marker appears; ingest must wait for the marker
- **Per-volume log file** (`SCRATCH/ocr-script.log`) as default — no cross-worker interleaving on shared midbox
- All preprocessing functions moved to **module level** (identical to production; just repositioned)

### 3. Hans pass-1 on `ocr_only_5090_sql.py`

Two BLOCKERs found:
- Exit code 3 ("reclaimable") not handled in `queue_worker_sql.py` — could burn attempts and dead-letter a volume. Fix: changed to rc=1; the SQL gate (`prep_state='done'`) is the real prevention.
- Preprocessing functions inside a conditional block — `NameError` trap if anyone adds a call in ocr mode. Fix: moved to module level.

Three SERIOUS: fitz.open waste in ocr mode (fixed: total_pages in JSON), unhandled OSError on outbox copy (fixed: retry), shared log file (fixed: per-volume).

### 4. Hans pass-2 on revised `ocr_only_5090_sql.py`

One BLOCKER: outbox failure exits rc=0 silently → OCR work accepted as done by queue but ingest never sees the volume. Fix: set `_outbox_fail` flag; `sys.exit(1)` if any file failed all retries.

Three SERIOUS: non-atomic two-file publish (fixed: OUTBOX_COMPLETE marker), sha256.txt missing unchecked in ocr mode (fixed: explicit existence check + exit rc=1), `json.loads` unguarded on classification JSON (fixed: try/except). Two MINOR fixed (log message fraction corrected).

---

## Files Changed

### New
- `pipeline/sql/ocr_only_5090_sql.py` — SQL-pipeline replacement OCR script (Hans×2 clean)

### Modified
- `pipeline/sql/schema.sql` — QUOTED_IDENTIFIER fix; topology comment corrected (DB = 5090 not 3060)
- `docs/80_PROJECT_HISTORY/run-logs/cc002-planning-run.log` — 2026-06-03 progress appended

---

## Decisions Made

| Decision | Detail |
|----------|--------|
| Replacement file, not overwrite | `ocr_only_5090_sql.py` is a new file; live `ocr_only_5090.py` untouched until tested |
| rc=1 on barrier fail, not rc=3 | SQL gate is the real prevention; special rc codes the worker doesn't handle are misleading traps |
| OUTBOX_COMPLETE marker | Two-file outbox publish needs an explicit completion signal; ingest must wait for this marker |
| Per-volume log file default | `SCRATCH/ocr-script.log` avoids cross-worker interleaving on shared midbox without requiring supervisor to set PATOLEX_RUN_LOG |

---

## Open Items at Close

| Item | Priority |
|------|----------|
| Apply schema.sql to `PK_Alien_5090\SQLEXPRESS` (Patrick task — credentials) | HIGH |
| Local test of `ocr_only_5090_sql.py` with `--stage all` and a real PDF, local dirs | HIGH |
| Test `--stage prep` + `--stage ocr` separately once all mode passes | HIGH |
| Run `setup_3060.ps1` elevated on the 3060 to create SMB shares + firewall | HIGH |
| Update ingest process to wait for `OUTBOX_COMPLETE` marker before reading outbox files | MEDIUM |
| Supervised cutover: drain JSON workers → seed PatoLexQueue → start SQL workers | MEDIUM |

---

## Next Session Should Start With

1. Set `$env:SQLCMDPASSWORD` from secrets file; run `sqlcmd -S "100.70.54.56\SQLEXPRESS" -U sa -i "pipeline\sql\schema.sql" -b` to apply tables/indexes
2. Local test `ocr_only_5090_sql.py --stage all` on a real volume with local paths (not UNC)
3. Once local tests pass, run `setup_3060.ps1` elevated on the 3060
4. Seed `PatoLexQueue` via `seed_ocr_queue.py --dry-run` first, then confirm

---

## Lessons Learned

- SQL Server `CREATE INDEX` with a `WHERE` clause (filtered index) requires `SET QUOTED_IDENTIFIER ON` in the session; without it, `Msg 1934` fires. Add `SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON;` before any filtered index creation in schema scripts.
- Exit codes from subprocess scripts must be documented in both the script AND the worker that calls it. An "rc=3 means reclaimable" convention that only the script knows about (and the worker ignores) is a silent ops trap.
- On Windows UNC/SMB paths, `Path.replace()` is not guaranteed to be seen atomically by readers on other machines due to SMB client-side caching (~10s window). For multi-file publish sequences, a completion marker file (written last) is the correct guard.
- `shutil.copy2` + `tmp.replace(dest)` on UNC can fail with `OSError` if the destination is locked by a reader; always wrap with a retry loop when publishing to a shared outbox.
