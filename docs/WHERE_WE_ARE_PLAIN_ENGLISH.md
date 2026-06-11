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

## One-line status
The cleaning method is basically solved and getting sharper; what's left is **measuring
two blind spots, resolving a small hard-garbage pile with images, and then loading it all in.**
