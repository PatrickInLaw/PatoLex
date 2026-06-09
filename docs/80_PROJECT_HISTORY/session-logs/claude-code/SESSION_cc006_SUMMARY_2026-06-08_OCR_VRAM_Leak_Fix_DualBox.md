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

---

## Continuation #2 — 2026-06-08 ~22:40 PT (DB inventory + Gate F discovery — ROADMAP-CORRECTING)

Ran tasks #1/#2/#3 (two parallel Sonnet subagents + a direct write) and then acquired the leginfo gap. **Findings materially correct the ROADMAP's "Current Status."**

### DB inventory (Sonnet subagent, live psql, read-only) — NOT "1850–1875 only"
- **`enactment` = 35,332 rows, span 1850–2024** (provision 84,118; designation_history 84,118; change_event 151,763; source_document 69; **lineage_edge 0; provision_version 0** — materialize/recodification sweeps never run).
- **Two layers:**
  - **OCR-linked (has `source_document_id`): 12,552 acts, 1850–2008** — the scanned session-law pipeline. **1850–1875 dense (~3,946); 1876–1989 nearly EMPTY (1876–94 ≈ 320; 1895–1989 ≈ 39).** ← the real hole.
  - **Gate F unlinked (`source_document_id IS NULL`): 22,780 acts, 1991–2024** — see next.

### The "mystery" unlinked layer = the MODERN ERA, ALREADY RECONSTRUCTED (not stubs)
- It is the **Gate F layer**: CA law **1991–2024 reconstructed from official leginfo CAML bill-XML**, written by `pipeline/gate_f/ingest_gate_f.py` (← `parse_bill_versions.py` parsing `pubinfo_YYYY/BILL_VERSION_TBL.dat`+`.lob` CAML).
- **139,211 section-level change_events**, all `trust_level='official_xml'`, `confidence=1.0`, `confident=TRUE`, `new_text` populated (99.6%). Citations `CA {year} Ch. {n}` (one enactment per chapter; ~6 change_events each; amend 104k / add 26k / repeal 8.8k). `title` NULL by design ("unknown from CAML").
- **14 sessions present: 1991-92, 1995-96, 1997-98, 1999-2000, 2005-06 … 2023-24.**
- **Gate F GAPS: 1993-94, 2001-02, 2003-04 are entirely absent.** Ends at 2023-24 (Sep 2024).
- **=> The ROADMAP is wrong:** Gate F ("Modern Layer") is listed **"Not started"** but is **largely DONE**. And "1850–1875 ingested (4262)" is badly stale — the DB holds 35,332 acts. **ROADMAP Current-Status + Gate F/E rows need rewriting.** (Flagged as open item, not yet done.)

### Leginfo acquisition (task #3 → acquire) — modern source now COMPLETE & CURRENT
- Subagent found `acquire_leginfo_pubinfo.py` had a **stale assumption** that 1989/1993/2001/2003/2025 were on disk — they were never downloaded. **Acquired all 5** (`acquire_missing_5.py`, scratch): pubinfo_2025 (930 MB, **LAW_SECTION_TBL=True** = current-law anchor), 1993 (69 MB), 1989 (16 MB), 2001 (214 MB), 2003 (194 MB).
- **PUBINFO series now complete: all 19 biennial sessions 1989→2025.** Source: `https://downloads.leginfo.legislature.ca.gov/pubinfo_{YYYY}.zip`.
- **The acquired archives map EXACTLY onto the Gate F gaps + current extension:** 1993/2001/2003 → fill the 3 missing Gate F sessions; **2025 → extend Gate F to current (2025-26)**; 1989 → earliest. So running `parse_bill_versions.py` + `ingest_gate_f.py` on these four makes the modern era **gap-free 1989→2026**.

### Strategic reframe (the big takeaways)
1. **The real un-built span is 1876–1993 historical** (~360 ingested acts), pure OCR territory (no XML pre-~1991). That is where OCR + ingest effort belongs.
2. **The OCR campaign's 1994–2000 work is largely redundant for the *served corpus*** — Gate F already covers 1995–2000 with higher-quality official XML. **But it's the seam-validation oracle** (roadmap: "the seam is a correctness oracle — both directions must agree where they overlap"). Finishing it (≈done 3:30 AM) gives that oracle for free; for serving, **Gate F is authoritative**.
3. **2005–2008 has BOTH OCR and Gate F** (2,818 overlapping year+chapter, no citation collision: OCR `Stats. YYYY_VolN ch.NNN` vs Gate F `CA YYYY Ch.N`). The query/publish layer must **arbitrate (Gate F wins)** — arbitration rule undefined.

### Tasks done this block
- #1 dedupe: 6× `2000-vol*` → `held` (canonical born-digital = 5080 `2000_Vol*`); lock-safe write.
- #2 DB inventory (above).
- #3 leginfo gap → acquired all 5 missing PUBINFO archives.
- 1999-vol2/4 resume-prep finished (body=2037 / 1724; crash damage repaired).

### Open items added
- **REWRITE ROADMAP current-status** (Gate F is largely built, not "not started"; DB has 35,332 acts not 4,262).
- **Run Gate F pipeline on the 4 new archives** (1993/2001/2003/2025[/1989]) → gap-free + current-through-2026 modern era. *(High value, data on disk, independent of OCR finishing.)*
- **Fill the 1876–1993 historical OCR ingest** (the actual hole).
- **Define OCR↔Gate-F arbitration** for the overlap years (Gate F authoritative; OCR = seam oracle).
- **Fix `acquire_leginfo_pubinfo.py`** stale `MISSING_YEARS` assumption.

---

## Continuation #3 — 2026-06-08 ~23:25 PT (ingestion plan + worklist + DB-over-Tailscale)

### Ingestion runs on the 5090, DB on the 5080 (corrected — I overcomplicated this)
- **The patolex DB lives on the 5080** (this box, local Postgres). **Ingestion *runs* on the 5090**
  (64 GB CPU) and **connects to the 5080 DB over Tailscale.** Not two DBs — one DB, remote client.
- **5080 Tailscale IP = `100.108.42.91`.** **Verified: 5090 → `100.108.42.91:5432` TCP reachable**
  (`TcpTestSucceeded=True`) — so listen_addresses + Windows firewall already allow it. Remaining for
  tomorrow: a `pg_hba.conf` entry for the 5090 (100.70.54.56) → patolex + creds. 5090 ingest env:
  `PGHOST=100.108.42.91 PGPORT=5432 PGDATABASE=patolex PGUSER=postgres PGPASSWORD=…`.

### Patrick's ingestion strategy (tomorrow AM, Opus-supervised, never automatic)
**Back up DB → purge ingested data → re-ingest ALL chronologically (1850→present) → diff vs backup.**
A mismatch ⇒ something broke. **CAVEAT I flagged:** the current DB is missing 1877–1990, so a full
re-ingest is a **SUPERSET** of the backup, not a byte-match — frame the diff as "every backup row
reappears unchanged + overlap identical," not strict equality. **Also flagged for Hans:**
`uuid_generate_v7()` `public_id`s and `retrieved_at` timestamps regenerate per ingest → a naive
byte-diff WILL mismatch; the diff must exclude/normalize non-deterministic columns.

### Ingest worklist drafted → `docs/60_OPERATIONS/INGEST_WORKLIST_2026-06-09.md`
- **Already ingested (verified live):** OCR 1850–1876 (dense), 2000–2008 (dense, born-digital),
  Gate F 1991–2024 (22,780, `official_xml`).
- **Phase 1 = OCR ingest of the real gap 1877–1990** (un-ingested; the DB has only strays there).
  Caveats: exclude 1862–1876 (re-OCR dupes of already-ingested years); **dedup variant labels**
  (`1927-vol1-26chapters` vs `-chapters`, `1929-…-28/29chapters`, etc.); confirm `ingest_clean.py`
  dedup key.
- **Phase 2 = Gate F ingest of the 5 staged sessions** (1989/1993/2001/2003/2025) → gap-free 1989→2026.
- **Overlap 1991–2000 (OCR ⟂ Gate F): Gate F is authoritative** (Patrick — settled); OCR = seam oracle.
- **Gate F JSONL staged on the 5090** (`gate_f_out/`, 51,834 actions, 5 files).

### Stray rows flagged + under investigation
- Anomalous `source_document`-linked enactments scattered 1877–1999 (1–8/yr; e.g. 1993:1) **shouldn't
  exist** — Patrick wants the root cause. **Sonnet forensic launched** (read-only) to trace origin
  (mis-dated vs partial-ingest vs test) + whether any hold real data before purge.
  - **FORENSIC RESULT (done):** the 51 strays are **NOT junk — a `chaptered_date` PARSER BUG.** All
    51 are real acts with correct text/citation/session; only the date is wrong. (A) 28 rows: OCR
    misread the year digit in `[Approved … 18XX]` on the 1855–1870 volumes; `parse_act_date()` in
    `ingest_from_ocr.py` lacks a year sanity check. (B) 22 rows: in born-digital 2000–2008,
    `APPROVED_RE` (before `APPROVED_MODERN_RE`) grabbed a historical date from the act *body* (B&P
    §473.15 boilerplate poisoned 6 vols); bug in `parse_born_digital_prod.py`. (1) `2003_Vol1 ch.70`
    date is actually correct (1993 act filed late in 2003); only its session label is wrong.
    **DON'T purge — fix dates in place; FIX THE PARSER BEFORE re-ingest** (else it reproduces the
    bug and the diff "matches the bug"); add a permanent ±N-year clamp. Detail in
    `INGEST_WORKLIST_2026-06-09.md` §A.2.

### Running overnight (read-only / no DB writes)
- OCR campaign → **ETA ~4:30–6:00 AM** (14 vols, ~26k pages, 4 workers); crash/heat monitor on the 5080.
- **Hans** verifying the worklist; **forensic** tracing the stray rows. Verdicts to be folded in.

### Roadmap updated this session
- `ROADMAP.md` Current-Status + Gate F row corrected (Gate F largely built; DB = 35,332 acts).
