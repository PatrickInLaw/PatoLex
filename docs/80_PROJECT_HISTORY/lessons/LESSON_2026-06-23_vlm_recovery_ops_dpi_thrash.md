# LESSON 2026-06-23 — VLM header-recovery operations: VRAM thrash, DPI, and the typo false-positive

## Context
Re-running Qwen2.5-VL over the 71 human-review chapters (with corrected full-bracket windows) to
machine-recover what the original campaign missed. Lifted recovery 29→47 of 71. Three operational
findings worth keeping.

## 1. Single-process VLM loops thrash unless the card is clean AND DPI leaves headroom
The first review pass used a **subprocess per year** (VRAM released between years) and ran ~4–5 s/page.
A later single-process loop over all years ran straight into a **full card and thrashed at ~156 s/page**
(243 pages → ~10 h ETA). Causes, both real:
- **Killed runs don't always release VRAM.** A `TaskStop`'d VLM run left ~16 GB allocated; the next
  run loaded another ~16 GB → 98% full → thrash. Always confirm with `nvidia-smi` after a kill; if VRAM
  is still high, find the stray `python.exe` (it's the big-WS one) and let it die / kill it. Clean
  baseline here was ~889 MiB.
- **350 dpi fills the card.** Qwen2.5-VL turns a 350-dpi statute page into a huge pile of visual tokens;
  weights (16.6 GB) + activations tip past 32 GB → thrash.

**Thrash signature on the GPU monitor:** util 100% but **power collapses** (~127 W vs ~350 W computing)
with VRAM pinned at ceiling. Watch power, not just utilization.

**Fix:** clean card + **render at 250 dpi** (≈half the visual tokens, ~11 GB headroom) +
`torch.cuda.empty_cache()` per page → back to ~365 W, ~3–4 s/page.

## 2. Lower DPI read BETTER, not worse
250 dpi **recovered chapters that 350 dpi missed** (e.g. 1866 ch.143, independently confirmed present
by Patrick's hand-read). Reason: an over-large image gets aggressively downsampled *inside* the model's
vision encoder (token cap), which can blur small text; a moderate-resolution image maps more faithfully.
**Higher DPI is not automatically better for VLM heading reads** — 250 was both faster and more accurate.

## 3. Typo-reconciliation false-positive
Auto-resolving scrivener typos by "read number N is an adjacent-Roman-swap of target c" produced a
FALSE positive: 1872 ch.126 flagged as "printed 124" because CXXIV↔CXXVI is one swap — but **ch.124 is a
legitimate chapter sitting at its own correct page**. The real typo (1870 ch.143 printed CLXIII=163) has
163 sitting at *143's* slot, out of 163's own position. **Rule:** only treat N as a typo of c if N is
OUT of its own sequence position (occupying c's slot) — not when N is a present chapter at its correct
spot. Until that guard exists, treat auto-typo hits as candidates, not confirmed.

## 4. "TRUE-GAP" is the wrong label for interior chapters
Chapters are numbered CONSECUTIVELY, so an interior missing chapter (c-1 and c+1 present) *was enacted
and printed* — it physically exists. A VLM reading a continuous neighbor sequence with no c almost always
means a **short act crammed on a shared page that it under-listed**, NOT a genuine absence. Do not report
interior misses as real gaps; they are unread-by-machine, for human review. (Genuine absences are mostly
volume-boundary or true legislative gaps.)

## Outcome
71 → 24 machine-unrecovered. Tooling (scratch): `_vlm_review_assist.py`, `_vlm_repass.py`,
`_paginate_check.py` (verified pagination is accurate, offset 0 — see below), `_build_remaining.py`.
Pagination spot-check (`_paginate_check.py`): recorded `source_page` == actual PDF page (offset +0
across all checks), median 1.0 pages/chapter — so bracket misses were never a pagination problem.
