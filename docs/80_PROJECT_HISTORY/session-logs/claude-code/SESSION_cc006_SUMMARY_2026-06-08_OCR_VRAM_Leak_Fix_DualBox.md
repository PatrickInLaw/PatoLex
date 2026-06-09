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
