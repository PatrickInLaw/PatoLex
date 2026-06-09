# Lesson: prep_runner fan-out OOMs the 16 GB 5080 box (RAM, not VRAM)

**Date:** 2026-06-06 · **Source:** RAM-OOM investigation on the 5080 box while the 5090 was down.

> **ROOT-CAUSE CORRECTION (2026-06-08).** Live forensics on the 5090 reframed the *crash* mechanism
> (distinct from the prep RAM cost documented below). The 5090's crashes are **commit-limit
> exhaustion → Event 41 dirty shutdown**, NOT physical-RAM OOM and NOT a bugcheck:
> - 5090 = 64 GB RAM but a **4 GB pagefile** → commit limit only **67.5 GB**. Three fully-loaded
>   OCR workers commit ~40–50 GB; the `prep_runner --parallel 16` burst (+16–32 GB) tips total
>   commit past 67.5 GB → allocations fail → box wedges → power-cycled (Event 41 on 06-06 & 06-08).
>   No Event 1001 (no BSOD), zero OOM/CUDA markers in worker logs = commit starvation, not OOM.
> - 5080 = 16 GB RAM but a **48 GB pagefile** → commit limit 63.7 GB → bursts PAGE (thrash) instead
>   of crashing → **no Event 41 in 14 days**. The big-RAM box crashes; the small-RAM box doesn't —
>   because of pagefile size, not RAM.
> - **Fixes:** (1) give the 5090 a large fixed pagefile (~64 GB → ~128 GB commit ceiling); (2) bound
>   prep concurrency (no `--parallel 16`); (3) keep workers ≤3 (VRAM 25.8/32 GB at 3 — a 4th
>   CUDA-OOMs); (4) investigate the ~13–15 GB/worker commit (CUDA pinned host memory).
> The prep fan-out below is still the BURST SOURCE; the pagefile/commit ceiling is what turns a
> survivable burst into a hard crash. Both levers matter.

## Finding

Running "the pipeline" on the **16 GB** 5080 box loaded **~25 GB of images into RAM** and
crashed the machine. The cause is **`prep_runner.py`** (live copy in
`C:\Users\PatrickKolasinski\PatoLex-scratch\`, also on the 5090), which is a fan-out
launcher: it spawns **`--parallel N` concurrent `--stage prep` subprocesses**, each rendering
an entire multi-hundred-page volume to 300-DPI PNGs at the same time. The default is
`PARALLEL = 16` (`prep_runner.py:26`); `run_prep_runner.bat` passes `--parallel 8`; commit
`c022f63` is literally "prep runner fixed 3->8 workers." **8–16 simultaneous full-volume
render+preprocess processes on a 16 GB box = the ~25 GB load.**

Why each prep process is not RAM-cheap: the Sauvola binarizer builds **float64 integral
images of a padded full-page array** (`cv2.integral(g_pad)` and `cv2.integral(g_pad**2)`) —
~8 bytes/px × several copies ≈ 50–150 MB transient per page, on top of the BGR page buffer.
Multiply by 8–16 processes + OS file-cache pressure from all the PNGs → ~25 GB.

## Not the cause (exonerated)

The single-volume OCR workers (`ocr_only_5080.py`, `ocr_only_5090.py`, `ocr_only_sql.py`)
**stream page-by-page**: the render loop writes each PNG and discards it; the OCR loop reads
one PNG at a time, `del`s the text, calls `torch.cuda.empty_cache()` + periodic `gc.collect()`.
A *single* worker's footprint is ~1–2 GB. The blowup is **process-count fan-out, not
in-process image accumulation.** There is no `convert_from_path`/image-list anywhere in the
OCR path.

## Why the 5090 "doesn't do this" (CORRECTED 2026-06-08)

It is NOT the same RAM. SSH assessment of the live 5090 box (`PK_Alien_5090`) shows it has
**63.5 GB system RAM** (~46 GB free), not 16 GB. The "16 GB" everyone quotes is the **5080's
GPU VRAM**, not system memory. Real RAM topology:

| Box | System RAM | OOM-prone |
|-----|-----------|-----------|
| 5080 (PatrickKolasinski) | 16 GB | always tight |
| 5090 (PK_Alien_5090) | 64 GB (~46 free) | only under prep fan-out |
| 3060 (prep box) | 32 GB (~20 free) | `--parallel 16` OOMs it too |

So the 5090 tolerates the same `prep_runner` fan-out the 5080 cannot, purely on RAM headroom.
The per-prep process is itself small (~0.5–1.5 GB; a `--stage prep` process renders/preprocesses
and does NOT load torch/surya/docTR until STAGE 4). **The OOM is uncontrolled CONCURRENCY**
(~16 × ~1 GB + file-cache + OS), not any single huge object. Bounding concurrency by free RAM
fixes it on every box. The newer **SQL pipeline bounds prep-ahead** (`queue_worker_sql.py`
`PREP_BUFFER_MAX = 3`) — a queue-depth bound — but that is NOT a RAM bound; the structural fix
is a RAM-governed admission gate (see `docs/30_SYSTEM_DESIGN/PREP_MEMORY_GOVERNOR_2026-06-08.md`).

## Corrects an earlier note

`LESSON_2026-06-02_ocr_cpu_prep_bottleneck.md` says "5080 … OOM is not a constraint." True for
**VRAM** (Surya uses ~1–5 GB). It is **false for system RAM** under prep fan-out. Keep both
limits distinct.

## Operational guidance — running a single bounded worker on the 5080 box

- **Do NOT run `prep_runner.py` / `run_prep_runner.bat` on the 16 GB box.** If prep-ahead is
  ever wanted here, cap it at `--parallel 1` (maybe 2), never 8/16.
- Use **`pipeline/5080/run_worker_5080.py`** (added this session): processes volumes **strictly
  one at a time** (one `ocr_only_5080.py` subprocess alive at once → full memory reclaimed
  between volumes), with a **hard RAM guard** (`--min-ram-gb`, default 3.0) that waits before
  starting a volume if free RAM is low, and a single-worker invariant (refuses to start if
  another OCR worker is already alive). It has **no `--parallel` knob on purpose.**
- The canonical one-volume command remains
  `python pipeline/5080/ocr_only_5080.py <pdf> <label>` (prep+OCR inline, streaming).
- Worklist caveat: the local `production_queue_state.json` is **stale** (9 old 1862–1876
  entries). Stem-derived labels do **not** match the campaign's irregular historical labels
  (`production-1929-vol1-28chapters`, etc.), so an archive-scan would re-OCR everything. Drive
  `run_worker_5080.py` with an explicit `--worklist` (or a corrected queue) of volumes that
  genuinely still need OCR. Run `--dry-run` first.

## Related

- `[[patolex-production-ocr-state]]`, `[[sql-pipeline-rework-plan]]`, `[[confirm-before-disruptive-actions]]`
- `LESSON_2026-06-02_ocr_cpu_prep_bottleneck.md`
