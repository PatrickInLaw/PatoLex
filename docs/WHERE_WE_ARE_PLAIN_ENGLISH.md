# PatoLex — Where We Are, in Plain English

*A non-technical snapshot of the corpus text-quality work. Updated 2026-06-11.*

## What we're actually doing
We have **~134 million words** of California law that computers scanned out of old
books (OCR). Scanning makes typos. The work is: (1) measure how dirty the text is, and
(2) build an automatic cleaner. That's it.

## Where we are — the good news
- **The text is ~99.6% clean.** Only ~0.4% of words are "bad."
- We built a cleaner that sweeps the **entire corpus in ~20 minutes** and fixes the
  obvious errors. The current version (v8) is the smartest yet.
- Big realization: **most "bad" words aren't garbage — they're real words our dictionary
  didn't know** (names, places, legal terms). So we taught it **California's 58 counties,
  159 cities, and 55 legislators**, so it stops calling "Tuolumne" or "Karnette" errors.

## What we're having trouble with (the honest hard parts)
1. **Typo vs. fragment.** Is `ablished` a typo of *abolished*, or a piece of *established*?
   A dumb rule guesses wrong ~10–15% of the time. (v8 adds a guard for this.)
2. **The errors we can't even see.** When the scanner turns a real word into a *different
   real word* — `State→Slate`, or a digit `8→3` — dictionary tools are blind, because the
   wrong word is still a real word. **We haven't measured how common this is. Biggest unknown.**
3. **Margin notes bleeding in.** Old law books have summaries in the margin in tiny print;
   the scanner sometimes mixed them into the main text, and split words across lines get
   the margin note jammed in the middle. (See the spatial-pairing approach we're developing.)
4. **The truly-garbled bits** (~340 distinct strings) can't be recovered from text at all —
   they need eyes (or a vision model) on the **actual scanned image**. Only ~225 pages to look at.

## The plan
- **Never touch the original.** Store every fix as a **reversible layer on top** — nothing
  is destroyed, everything is undoable, every change is traceable (safe for a legal record).
- **Apply the safe automatic fixes; escalate the uncertain ones** to a smart model
  (Sonnet) or a vision model reading the scan; later, community wiki polish.
- **Two things to MEASURE before we trust the corpus:** (a) the invisible real-word
  substitution rate, (b) a spot-check of the lower-confidence fixes.
- **Home stretch:** fix the Roman-numeral chapter-number parser, then the one big ingest
  (back up → wipe → load all of 1850–2026 → compare).

## Both blind spots are now MEASURED (2026-06-11)
- **Split words / margin notes (Path 1):** of 229k words split across lines, 95% were
  already handled; the line-aware pass recovered **11,156** more (incl. ~1,500 true
  margin-interleaved). Solved from text — no image coordinates needed.
- **Real-word substitutions (Path 2):** the invisible class (State→Slate, lion→lien,
  1038→1938) measured at **~0.055% overall** (0.11% in pre-1900 scans → 0.015% modern)
  via a 498-window stratified sample judged by Sonnet. Small.
- **DECISION: coordinate re-derivation SKIPPED.** Both text paths are strong; the
  invisible residue (~0.055%, ≈74k instances corpus-wide) is handled by the layered
  correction architecture (on-demand LLM + community wiki + reversible overlay), not by
  re-deriving pixel coordinates. Not a launch blocker — a bounded polish tail.

## One-line status
Text quality is **characterized and solved**: both error classes measured (visible
~1.14%→~0.4% corrected; invisible ~0.055%), cleaning method built. What's left is the
**parser fix (Roman-numeral chapters)** and the **one big ingest** (back up → wipe →
load 1850–2026 → compare).
