# Session cc006 — OCR VRAM "Leak" Fixed; Dual-Box (5090×3 + 5080×1) Restored

**Date:** 2026-06-08 · **Agent:** Claude Code (cc006)

## What Was Done

1. **GitHub Desktop** — connected all 11 local repos (9 were missing). `github.bat` opens an "Add Repository" dialog needing confirmation; drove it with focus+Enter for the blocked ones. All 11 verified in the GHD store.
2. **5080 RAM cleanup** — freed ~3 GB (3.9→6.6 GB) closing game launchers / bloat. (5080 box = 16 GB system RAM.)
3. **Born-digital 2000–2008** — ran 47 volumes locally on the 5080 via the new `run_worker_5080.py`; all `rc=0` in ~5 min (text-layer extraction, near-zero RAM).
4. **Diagnosed + fixed the OCR pipeline crashes** (the core of the session — see Decisions).
5. **Recovered 31 stranded 1994–2000 volumes** that the crashes left `failed`, via a chain of fixes (worker pdf-resolution bug, requeue, decoupled-state routing).
6. **Brought both boxes online without conflict** — 5090 ×3 + 5080 ×1, four distinct volumes, serialized by the shared queue lock.
7. **Crash-safety backups to the 5080** — OCR outputs (3 GB) + prepped pages (53 GB) mirrored.
8. Built ops tooling: `run_worker_5080.py` (single RAM-bounded worker), `monitor_5090.ps1` (remote GPU crash/heat watcher run FROM the 5080 over SSH so it survives a 5090 crash).

## Decisions Made

- **Root cause of the VRAM "leak" = Surya auto-batch fragmentation, NOT page content and NOT a reference leak.** Surya 0.13 with `batch=None` auto-sizes huge, per-page-*variable* batches on a 32 GB card → CUDA caching-allocator fragmentation → `reserved` VRAM ramps across a volume (4.7→20.7 GB) → TDR (BugCheck 0x117) crashes multi-worker runs. **Proven by isolation test: 60 OCRs of the same page = +0 MB growth once the batch is pinned (batch 32 AND 128).** A *simpler* table page used 4× the VRAM of a dense prose page — disproving the content theory.
- **Fix: pin Surya batch sizes** in both `ocr_only_*.py` (before any torch/surya import): `RECOGNITION_BATCH_SIZE=128`, `DETECTOR_BATCH_SIZE=12`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Result: each worker holds a flat ~6–8 GB → 3 workers (~24 GB) safe on the 5090.
- **Hardware context (corrected):** 5080 box = 16 GB RAM; 5090 box = **64 GB RAM** (verified live); 3060 = 32 GB. The "16 GB" everyone quoted is the 5080's **VRAM**. The 5090 crashes were **GPU TDRs at ~69 °C (not thermal, not system-RAM OOM)** — driver updated to `610.47`, but the real trigger was VRAM exhaustion at 3+ workers (one worker peaked 21 GB on a 32 GB card).
- **Worker counts:** 1 worker per box while the leak was unfixed; after the fix, **3 on the 5090 + 1 on the 5080**.
- **5080 participates via the existing shared-queue path** — `queue_claim.py` extended to also claim `prepped` volumes onto the 5080's own `in_progress` lane (a status the 5090 decoupled workers never touch), so both boxes stay serialized on the one lock with no double-processing. `ocr_only_5080.py` gained a `STAGE1-2-SKIP` fast path so the 5080 OCRs the synced prep without re-rendering.

## Other bugs fixed this session

- `ocr_only_5080.py`: **`STAGE` was undefined** → every born-digital 2000+ volume `NameError`-crashed. Restored `--stage` parse (parity with 5090).
- 5080 local **surya-venv is missing `fitz`/PyMuPDF** → `run_worker_5080.py` now defaults to the system Python312 (full stack + CUDA).
- 5090's **deployed `queue_worker.py` ignored the `pdf` field** (guessed `<label>_Statutes.pdf`) → `pdf_missing` for all 1994–2000 multi-vol files. Deployed the repo version with `pdf_name_for()`.

## Files Changed

- `pipeline/5090/ocr_only_5090.py` — pin Surya batch sizes (VRAM fix).
- `pipeline/5080/ocr_only_5080.py` — `STAGE` parse fix, batch pin, `STAGE1-2-SKIP` prep fast path.
- `pipeline/5090/queue_claim.py` — claim `prepped` volumes (5080 dual-box participation).
- `pipeline/5080/run_worker_5080.py` — NEW: RAM-bounded single-worker driver.
- `pipeline/5080/monitor_5090.ps1` — NEW: remote 5090 GPU crash/heat monitor.
- `docs/30_SYSTEM_DESIGN/PREP_MEMORY_GOVERNOR_2026-06-08.md` — NEW: prep-memory governor design.
- `docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-06_prep_runner_ram_oom_5080.md` — NEW: prep_runner RAM-OOM + commit-limit/TDR corrections.
- `docs/80_PROJECT_HISTORY/lessons/LESSONS_OVERVIEW.md` — indexed dated lessons.
- run-logs (`worker-5080-run.log`, `monitor-5090-run.log`) — progress trails.

## Open Items at Close

- **27 of 205 volumes remaining** (1994–2000 batch); 4 workers running; **ETA ~15 h (by morning 2026-06-09).**
- **Hans review** of the pipeline changes (batch pin, `queue_claim` change, `ocr_only` edits) still owed — well-tested live, but the adversarial pass is the standing rule for pipeline code.
- `prep_runner.py --parallel 8/16` should be retired in favor of the RAM-governed approach (documented in `PREP_MEMORY_GOVERNOR_2026-06-08.md`); not yet built.
- Stray `pipeline/gate_f/test.txt` (pre-existing, not this session's) left untracked.

---

## Continuation — 2026-06-08 ~22:15 PT (dual-box live + corpus-state findings)

### Dual-box is live and proven conflict-free
- **4 workers running:** 5090 ×3 (fixed-batch, stable ~12–24 GB VRAM / ~60–70 °C) + 5080 ×1.
- The 5080 worker (`queue_worker_5080.py 5080-1`) claims `prepped` volumes from the shared 5090 queue via the updated `queue_claim.py`, OCRs from the **synced local prep** (`STAGE1-2-SKIP` confirmed in its log — no re-render), and pushes results back. Both boxes serialize on the one lock; the 5080 sits on the `in_progress` lane the 5090 decoupled workers never touch → **zero double-processing** (verified: 4 distinct volumes, 4 workers).
- **Backups mirrored to the 5080** (crash-safety): OCR outputs (3 GB, 606 files) + prepped pages (53 GB, 29 vols).

### ETA is now computed from measured data (not guessed)
- Measured per-worker rate from live logs: **~21 pages/min each** (1996-vol4 21.6, 1996-vol6 20.3, 5080/1997-vol2 21.8). GPU not saturated → workers scale ≈ linearly → **aggregate ~84 pages/min**.
- Remaining at 22:00: ~27.9k image-OCR body pages (born-digital 2000s excluded, near-instant).
- **ETA ≈ 3:30 AM PT, Tue 2026-06-09** (band 3:00–4:00 AM). NOTE: the earlier "~15 h" was wrong — it used a worst-case 6 s/page (a *dense* page) instead of the measured ~2.9 s/page avg, and never measured the 4-worker aggregate. Method to reuse: remaining_body_pages ÷ aggregate_pages_per_min.

### Corpus-state findings (from the Q&A — capture these)
1. **1999-vol2 / 1999-vol4 were NOT "unclassified by design" — their prep crashed mid-render** in the TDR cascade. Render finished (2040 / 1726 raw pages) but preprocess only reached **1319 / 993** before dying, so `pages_prep_gray` is incomplete → `page_classification.json` never wrote → my page-count query read `body=0` (a *missing file*, not zero pages). They hold ~2040 / ~1726 real pages. **Action taken:** resume-prep launched on the 5090's idle cores (`ocr_only_5090.py … --stage prep`, CPU-only, ~1 GB RAM each) to finish the missing preprocess + classification ahead of the GPU workers (they're ~4 h away → no collision). *Lesson: a crash can leave a volume marked `prepped` with incomplete artifacts; "prepped" status ≠ "prep complete on disk."*
2. **The 2000s are already extracted — do NOT re-extract.** Born-digital 2000–2008 were extracted on the 5080 earlier this session (**48 result files**, labels `2000_Vol*` underscore). The 5090 queue's `2000-vol1..6` (hyphen) are **pure duplicates** sitting `prepped`. Re-running would waste GPU claims AND risk **double-ingestion** under two labels. **Decision: dedupe** — designate the 5080 `2000_Vol*` as canonical, mark the 5090 `2000-vol*` to be skipped; reconcile the `2000-vol1` vs `2000_Vol1` label split before ingest. Born-digital extraction is GPU-free/instant — it should be done *ahead* of time, never interleaved into the GPU queue.
3. **Ingestion = the whole 1876→present backlog, chronological (the user confirmed: "that is the ingestion pipeline").** Only **1850–1875 is in the DB** (4,262 acts); everything OCR'd since (1876–2000) is **un-ingested**. The event-sourced model makes ingest *order* technically flexible (materialize is a date-ordered fold), but **chronological is the sane, validatable approach** and matches build-forward. *TODO: re-query the live local Postgres to confirm the exact ingested range (roadmap figure is dated 2026-06-02).* The modern-volume parser (`parse_born_digital.py`, tier b) is "prototyped but not yet ingested" per ROADMAP — so this backlog ingest is a **build task**, not a button-press.
4. **The corpus must be CURRENT THROUGH TODAY (2026) — "2023" was only what's *downloaded*, not a target.** Leginfo PUBINFO XML is acquired for 1991/1995/1997/1999 + 2005→2023 (biennial), with **gaps at 1993 / 2001 / 2003** and **nothing for 2024–2026**. The modern (Gate F) build reconstructs **backward from the *current* leginfo snapshot**, so it anchors on today's law by design — "current" is the *starting point*. To close the chain end-to-end we must **acquire the missing sessions (2024–2026) + fill the gaps + pull a fresh current snapshot**, then reconstruct backward to the ~1993 seam.
5. **OCR↔leginfo overlap to resolve:** the OCR campaign ran *through 2000*, but tier-(c) leginfo covers *1994–present* → **1994–2000 is likely redundant** between the OCR/extract work and leginfo. Must decide which source is authoritative for that overlap before ingesting both (else double-coverage / seam conflict).

### Decisions added
- 5080 participates via the existing shared-queue path (`queue_claim` now claims `prepped` → `in_progress` lane); OCRs synced prep with `STAGE1-2-SKIP`. No partition hack needed (the shared lock already serializes — they ran together fine before; the only blocker was the decoupled-state I introduced, now handled).
- Do born-digital extraction ahead of time, off the GPU path; never re-do already-extracted volumes; dedupe to one canonical label set before ingest.
- Ingest the full OCR/extract backlog chronologically (1876→present) as the next build.
- Corpus target is current-through-today; modern build anchors on the live leginfo snapshot.

### Open items / next-steps (detailed, prioritized)
1. **Finish OCR** (ETA ~3:30 AM) — monitor running; 1999-vol2/4 resume-prep in flight.
2. **Dedupe the 2000s** — canonical = 5080 `2000_Vol*`; skip the 5090 `2000-vol*`; reconcile label scheme.
3. **Confirm DB ingested range** (expected: 1850–1875 only) → then **stand up chronological ingest of 1876→present**. Verify/finish the modern-volume parser (`parse_born_digital.py`) — it's only prototyped.
4. **Resolve the 1994–2000 OCR-vs-leginfo overlap** (which source is authoritative).
5. **Leginfo acquisition to current** — pull 2024–2026 sessions + fill gaps (1993/2001/2003) + fresh current snapshot; this is the spine of Gate F (modern, "not started").
6. **Quality owed:** human-gold OCR audit (~10–20 pages) to *certify* the ~1.5 % CER; **Hans review** of this session's pipeline changes (batch pin, `queue_claim`, `ocr_only` edits).
7. **Cleanup:** decommission `prep_runner.py` (the `--parallel 16` OOM cause) in favor of the RAM-governed design.

### Key facts not to lose
- Real hardware: **5080 box = 16 GB RAM**, **5090 box = 64 GB RAM**, **3060 = 32 GB**. ("16 GB" everyone quoted = the 5080's *VRAM*.) 5090 crashes were **GPU TDRs (BugCheck 0x117) at ~69 °C** — driver updated to `610.47`; real trigger was **VRAM exhaustion at 3+ workers** (one worker peaked 21 GB on a 32 GB card) — now bounded by the batch pin.
- The VRAM "leak" was **Surya `batch=None` auto-sizing → allocator fragmentation**, NOT content, NOT a reference leak (proven: 60 OCRs of one page = +0 MB growth at fixed batch).
- 5080 local **surya-venv lacks `fitz`** → use system Python312 for OCR there.
- Crash monitor (`monitor_5090.ps1`) runs **on the 5080**, polling the 5090 over SSH, so it survives a 5090 crash (detects the SSH drop = crash).
