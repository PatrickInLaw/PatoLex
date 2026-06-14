# HANDOFF — Page-Shape Classification Pipeline (cc007)
**Written 2026-06-14 ~01:30 UTC, right before a 5080 reboot. Read this top-to-bottom before doing anything.**

You may be a fresh session or this session post-compaction. Either way, assume you know nothing and start here.
The authoritative running session log is `docs/80_PROJECT_HISTORY/session-logs/claude-code/SESSION_cc007_SUMMARY_2026-06-09_Parallel_Ingest_Prep.md` — read its **Continuations 60–71** for the full narrative. This doc is the operational summary.

---

## 0. TL;DR — what is happening right now
We built and are running a **3-stage page-classification pipeline** over the 205-volume historical OCR corpus:
**Surya page-shape (GPU, 5090) → procedural text-reconcile (CPU, 5080) → VLM tiebreaker (GPU, 5090).**
- **Stage 1 (shape): DONE** — 205/205 volumes classified.
- **Stage 2 (reconcile): DONE** — 205/205. Recovered 10,317 statute pages Surya wrongly flagged non-body.
- **Stage 3 (VLM): RUNNING** on the 5090 — ~8,449 done / ~5,828 pending as of this writing. Finishes ~03:00–03:30 UTC on its own. **It survives the 5080 reboot** (it's a SYSTEM task on the 5090; the queue is on the 3060).
- **After the 5080 reboots:** the reconcile worker + loader (which ran on the 5080) are DONE and don't need restarting. Only the VLM keeps going, on the 5090. Just monitor it.

**Your job next:** (a) confirm the VLM finished, (b) run the garble-weighted final number, (c) report. Details in §6–7.

---

## 1. Context — what this work is for
PatoLex = point-in-time archive of California statutory law, 1850→present (see `CLAUDE.md`, `docs/20_ROADMAP/ROADMAP.md`). The corpus was OCR'd (205 image-scanned volumes ~1850–1990s). The **root problem** is the long tail of un-correctable OCR garble (~146,832 `no_candidate` tokens). This page-shape effort answers: **how much of that garble sits on NON-body pages (rosters / indexes / dividers) we never ingest — and thus can stop worrying about?**
**Key finding so far:** most of the garbled tail is REAL statute text (the VLM overturns ~87% of Surya's garbled-page non-body flags back to BODY). Genuine roster/index exclusion set is small (~2,500 pages). So the page-shape work is as much *diagnostic* (the tail is mostly real) as *subtractive*.

---

## 2. The three machines, SSH, and SQL/DB access

### Machines (all on Tailscale, `100.64.0.0/10`)
| Box | Tailscale IP | role | default SSH shell |
|-----|-------------|------|-------------------|
| **5090** `pk-alien-5090` | `100.70.54.56` | GPU compute (Surya + VLM). Runs as `patolex` (local admin). Repo at `C:\github\PatoLex`. surya venv at `C:\Users\patolex\PatoLex-scratch\ocr-engines\surya-venv\Scripts\python.exe`. Scratch at `C:\Users\patolex\PatoLex-scratch`. | **cmd** (use `&`, `findstr`, `dir`, `/d`) |
| **3060** `PK_XPS` | `100.113.254.6` | Rock-solid SQL queue host + file server. SSH enabled 2026-06-13. `patolex` is admin. | **PowerShell** (use `;`, `Where-Object`) |
| **5080** `PKs_2025_Alien` | `100.108.42.91` | THIS box (the interactive session host). Azure-AD `patrickkolasinski`. Hosts local Postgres corpus DB + PatoAudio. The repo lives here (`C:\Users\PatrickKolasinski\Documents\GitHub\patolex`). RAM-constrained; reboots periodically. | — (local) |

### SSH (from the 5080)
Key file: `C:\Users\PatrickKolasinski\.ssh\patolex_5090` (one ed25519 key; both boxes trust it).
```
ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 -o BatchMode=yes patolex@100.70.54.56 "hostname"   # 5090 (cmd)
ssh -i C:\Users\PatrickKolasinski\.ssh\patolex_5090 -o BatchMode=yes patolex@100.113.254.6 "hostname"   # 3060 (powershell)
```
The key + a host map are ALSO in Windows Credential Manager for any agent: `PatoLex_SSH_patolex_key`, `PatoLex_SSH_hosts`. Full doc: `docs/60_OPERATIONS/SSH_ACCESS.md`. NOTE: SSH-launched processes die when the SSH session closes — durable jobs run via **SYSTEM Scheduled Tasks**, not SSH `Start-Process` (learned the hard way).

### SQL queue (the pipeline state) — on the 3060
- Login: **`PatitoSync`** (NOT `sa`; sa is rejected on the 3060). It is **db_owner of `PatoLexQueue`**.
- Password: Windows Credential Manager, target `PatitoSql_PatitoQBCache_PatitoSync`, read via `~/.claude/scripts/CredStore.ps1`:
```powershell
. "$env:USERPROFILE\.claude\scripts\CredStore.ps1"
$pw = Get-CredSecret -Target PatitoSql_PatitoQBCache_PatitoSync
$c = New-Object System.Data.SqlClient.SqlConnection ("Server=100.113.254.6\SQLEXPRESS;Database=PatoLexQueue;User Id=PatitoSync;Password=$pw;TrustServerCertificate=True;Encrypt=True"); $c.Open()
```
- The 5090 workers read the DSN from `C:\Users\patolex\.patolex_queue_dsn.txt` (on the 5090; written via SSH stdin, gitignored, never logged). Python workers read `PATOLEX_QUEUE_DSN` env. ODBC Driver 18 + pyodbc are installed on 5090 (surya-venv) and 5080.

### Corpus DB (the actual statutes) — local Postgres on the 5080
- `DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/patolex` in `C:\Users\PatrickKolasinski\Documents\GitHub\patolex\.env.local` (gitignored). NOT Supabase. 35,332 enactments (1850-75 OCR + 1991+ + born-digital). Has act-level text (`enactment`/`provision`), `source_document` (sha256+page_count for 69 vols), `change_event.page_ref` (printed-page ranges). NO per-page OCR text — that's the cascade `out_context`.

---

## 3. The pipeline architecture (queue-driven, crash-safe)
SQL queue DB `PatoLexQueue` on the 3060. Tables (all SYSTEM-VERSIONED temporal for change audit + `state_history` for semantic transitions):
- **`dbo.ocr_queue`** — ONE row per volume (label, pdf, yr). Per-pass column groups with lease/heartbeat/fence: `prep`/`ocr`/`tess`/`doctr`/`surya`/`consensus` (the full OCR flow, currently `'na'`/inert), **`shape`** (page-shape pass), **`reconcile`** (text-reconcile pass). This is the same factory that will later run full OCR for a new corpus — enable passes + reseed.
- **`dbo.vlm_queue`** — PAGE-level (label, pdf, pidx, surya_class, verdict, state). The VLM tiebreaker worklist.
- **`dbo.volume_manifest`** — authoritative 205-volume source list (label→pdf, 0 missing; 1929/1949 flagged ambiguous). Exported to `docs/30_SYSTEM_DESIGN/sources/volume_manifest.tsv`.
- **`dbo.state_history`** — who/when transition log.

### Stage 1 — Surya shape (5090)
`pipeline/analysis/surya_page_shapes.py` renders each PDF page (PyMuPDF) → Surya layout → dominant shape label; **persists every PNG** to `page-renders/<pdfbase>/<pidx:04d>.png` (resumable). Multi-PROCESS (threads plateau on GIL). **Hard VRAM cap per process** (`--vram-frac`, default 0.15) + `cudnn.benchmark=False` — proven: a >32 GB spike would TDR-reset the 5090, so this is mandatory. Driven by `pipeline/sql/shape_worker_sql.py` (reuses `queue_worker_sql.py` lease machinery). Launched by SYSTEM task **`PatoLexShapeWorkers`** (4 workers, vram-frac 0.15). Output: `page-shapes/<pdfbase>.shapes.tsv` (pidx, class, dominant_label, conf).

### Stage 2 — procedural reconcile (5080, CPU)
`pipeline/analysis/shape_reconcile.py`: for each Surya NON-body page, RESCUE→body if the OCR text shows statute signals (enacting clause / chapter+section / appropriations money-prose), CONFIRM→nonbody if index header ("TITLE OF ACT"/CONTENTS) + no body signal, else AMBIGUOUS→VLM. Driven by `pipeline/sql/reconcile_worker_sql.py` (pulls each shape TSV from the 5090 via scp, reads LOCAL `out_context` text, appends ambiguous pages to `_cascade/vlm_worklist.tsv`). DONE (205/205). **This ran on the 5080 and is finished — nothing to restart.**

### Stage 3 — VLM tiebreaker (5090, GPU)
`pipeline/sql/vlm_worker_sql.py`: a single persistent worker that **self-gates** (waits until shape has no pending/working before loading the model → no VRAM contention), loads local Qwen2-VL-7B once, drains `dbo.vlm_queue` page-by-page using the persisted render PNGs, writes a verdict (BODY/ROSTER/INDEX_TOC/REPRINT/OTHER). Launched by SYSTEM task **`PatoLexVLM`** (ONSTART). Loader `pipeline/sql/load_vlm_queue.py` ran on the 5080 (`--watch`) to feed `vlm_queue` from the worklist — it has loaded all 14,290 ambiguous pages already (reconcile is done), so it's finished too.

---

## 4. Data locations (on the 5090 unless noted)
- Source PDFs: `C:\Users\patolex\PatoLex-scratch\chief-clerk-archive\` (422 PDFs incl. dupes; the 205 mapped via `volume_manifest`).
- Renders (PERSISTED, durable): `C:\Users\patolex\PatoLex-scratch\page-renders\<pdfbase>\<pidx:04d>.png`.
- Shape outputs: `C:\Users\patolex\PatoLex-scratch\page-shapes\<pdfbase>.shapes.tsv`.
- Cascade text (per-page OCR tokens): `...\_cascade\out_context\production-<label>.json` (also pulled LOCAL to 5080 at `C:\Users\PatrickKolasinski\PatoLex-scratch\_cascade\out_context`).
- Reconciled per-page labels: `...\_cascade\reconciled\<label>.reconciled.tsv` (on the 5080).
- VLM worklist: `...\_cascade\vlm_worklist.tsv` (5080).
- Manifest: `...\_cascade\manifest.tsv` (5090) + committed `docs/30_SYSTEM_DESIGN/sources/volume_manifest.tsv`.

---

## 5. How to check status / tell whether it's done
Connect to the 3060 SQL (see §2) and run:
```sql
SELECT shape_state, COUNT(*) FROM dbo.ocr_queue GROUP BY shape_state;          -- expect done=205
SELECT reconcile_state, COUNT(*) FROM dbo.ocr_queue GROUP BY reconcile_state;   -- expect done=205
SELECT state, COUNT(*) FROM dbo.vlm_queue GROUP BY state;                       -- DONE when pending=0 AND working=0
SELECT ISNULL(verdict,'(null)'), COUNT(*) FROM dbo.vlm_queue WHERE state='done' GROUP BY verdict ORDER BY 2 DESC;
SELECT SUM(reconcile_rescued), SUM(reconcile_confirmed), SUM(reconcile_ambiguous) FROM dbo.ocr_queue WHERE reconcile_state='done';
```
GPU on 5090: `ssh ... patolex@100.70.54.56 "nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader"`.
**The whole pipeline is DONE when `vlm_queue` has 0 pending + 0 working.** (~12 `failed` rows are acceptable — missing renders; can re-render + retry, low priority.)

### If the VLM stalled / 5090 rebooted
The VLM SYSTEM task is `PatoLexVLM` (also ONSTART). To (re)start the worker on the 5090:
```
ssh -i ...\patolex_5090 patolex@100.70.54.56 "schtasks /run /tn PatoLexVLM"
```
It self-gates on shape-done (shape is done, so it loads immediately) and resumes draining `vlm_queue` (expired leases re-claim). Shape workers task: `PatoLexShapeWorkers` (done; don't need it). To add capacity safely keep **#GPU-workers × vram-frac ≤ 0.80**.

---

## 6. What remains (your next steps)
1. **Confirm the VLM finished** (vlm_queue pending=0, working=0).
2. **Run the garble-WEIGHTED final number** — the exact "% of long tail removed". Tool: `pipeline/analysis/garble_by_shape.py` joins per-page garble × final label. It currently uses the RECONCILED labels (`PATOLEX_USE_RECONCILED=1`) but does NOT yet fold in VLM verdicts — UPDATE it so AMBIGUOUS pages take their `vlm_queue.verdict` (BODY→stays, ROSTER/INDEX_TOC/REPRINT→removed), then the buckets are: garble on BODY (real cleaning target) vs garble REMOVED (confirmed + VLM-non-body). Run it on whichever box is idle (see §8). Report removed-% overall + by era.
3. **Report to Patrick**: final removed-garble number, the verdict split, and the headline (most of the tail is real statute).

### Optional / deferred
- **Roster-confirm rule** in `shape_reconcile.py` (a Name/County/Residence header + low statute signal → confirm non-body deterministically) to move garbled rosters from pending-VLM to deterministic-removed and shrink future VLM load. Patrick is interested but hasn't said go.
- Backfill `volume_manifest.sha256`/`page_count` from `source_document` (69 vols) + compute the rest.
- The 3060 can host an **SMB source/render store** (full durable hub) — SSH now works there.
- The FULL OCR flow (prep/ocr/tess/doctr/surya/consensus passes already in `ocr_queue`) is the future use of this same factory for a new corpus.

---

## 7. KEY FINDINGS (durable — do not lose)
- **Surya page-shape**: reliable on CLEAN pages (7/7 bake-off) but **over-flags on garbled/embedded-table statute pages** — it cries `TABLE_ROSTER` at any embedded form/schedule/table inside a statute. ~87–91% of its garbled-page non-body flags are actually BODY.
- **The 3-stage funnel is the fix**: Surya (cheap, broad, noisy) → reconcile (cheap, deterministic, text) → VLM (image-based, accurate) on the residual. The VLM is validated (visual spot-check 6/7 correct, discriminates real rosters) — it reads the clean page IMAGE, which is right because the ambiguity comes from garbled OCR TEXT, not bad scans.
- **Garble payoff**: removal is MODEST. Deterministic (reconcile-confirmed) ~2% of the tail; up to ~20% max if all ambiguous were non-body, but the VLM shows ~80–87% of ambiguous is statute body, so the true removed share is small. Heaviest in the early era (1860s 52% / 1870s 60% of those years' garble sits on non-body/ambiguous pages). **Conclusion: most of the garbled long tail is real statute text that still needs cleaning/re-OCR.**

---

## 8. PROCEDURES (how to work here)
- **Token awareness**: this is a long-running, token-heavy effort. Be economical. Use the dedicated tools (Read/Grep/Glob/Edit), not shell `cat`/`grep`. Don't re-read files you just wrote.
- **Subagents**: delegate mechanical/parallel work (broad searches, reading many files, drafting) to subagents via the Agent tool — `Explore`/`general-purpose` for research, `haiku-worker` for cheap reads. For ADVERSARIAL review of product/pipeline code use the **`verify-auditor`** agent ("Hans" persona). Run background agents with `run_in_background: true` and relay only the conclusion. The VLM/visual spot-checks used a `general-purpose` agent with `model: sonnet` reading rendered PNGs.
- **Distribute load by CURRENT utilization** (memory: `distribute-load-by-current-utilization`): pick the box that's idle NOW, not a fixed rule. During a GPU campaign the 5090 is saturated → CPU analysis goes on the idle 5080. Between campaigns the 5090 (24c/64GB) is idle AND stronger → use it. The 5080 is set up as an analysis OPTION (wordfreq/pyspellchecker installed; gazetteer/corpus_freq/page-shapes local; set `PATOLEX_LOCATION_ROOT=C:\Users\PatrickKolasinski\PatoLex-scratch` + `PYTHONPATH=...\pipeline`).
- **Use the PROCESSED data, not raw**, when refined outputs already exist (e.g. reconciled labels over raw Surya).
- **VRAM is sacred**: never let GPU work risk >32 GB on the 5090 (TDR = catastrophic). Hard-cap every GPU process; gate concurrent loaders.
- **Hygiene**: keep the run log + session log current (event-driven, see CLAUDE.md). Findings go in DURABLE docs (design doc / lessons / memory), never only a run log. The pre-bash hook blocks commit/push without a current-day session log; `/ucp` updates+commits+pushes.
- **Bash hygiene**: no `cd`/`&&`/`||`/`;` compound bash (hook blocks it); no `echo`/`printf` for status. PowerShell tool allows `;`. SSH→PowerShell nested quoting is fragile — prefer committed `.ps1`/`.py` scripts run via `-File`/`-m` over inline nested quotes.
- **Confirm before disruptive actions**; present options not verdicts (Patrick makes architecture/sequencing calls); never auto-kill workers or scale down without asking.

---

## 9. Git
Repo: `C:\Users\PatrickKolasinski\Documents\GitHub\patolex` (origin `github.com/PatrickInLaw/PatoLex`, branch `main`). Everything built this session is committed + pushed (latest ~`ea04c4b`). On the 5090, pull at `C:\github\PatoLex` before running its scripts. Commit co-author line: `Co-Authored-By: Claude Code <ClaudeCode@Kolasinski-Law.com>`.
