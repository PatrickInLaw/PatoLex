# OCR-Era Corpus Completeness — True State of Play (2026-06-29)

**Purpose:** an honest, no-rounding statement of what we KNOW and DO NOT KNOW about the completeness
of the 1850–1999 OCR-era statute corpus. Written deliberately to avoid the premature-"done" framing
that has been wrong repeatedly this session. **The OCR-era corpus is NOT verified complete.** This
document says exactly how far we've gotten and what remains genuinely unknown.

---

## 1. What is CONFIRMED

### Chapter-level (whole acts), REGULAR sessions only
- **99.98% of regular-session chapters present: 95,985 / 96,002** (effective-N, regular sessions
  1850–1999). Residual **17 chapters**, all judged to need a physical archive scan:
  - 8 original missing-leaf chapters (1927/1929/1970/1981/1985/1986), and
  - 9 chapters in the 1872 volume's four confirmed missing leaves.
- This number counts **REGULAR sessions only** — see the extra-session UNKNOWN in §2.

### Page-level (missing leaves), over the AUDITABLE subset
- A deterministic page-continuity audit (printed-page-number continuity, Hans-verified SOUND) found
  **126 high-confidence dropped leaves (even-parity, "stuck pages drop in pairs")** across the
  auditable volumes. These are real, and they are the firmest scan targets we have.
- Coverage: **211 of 225 production dirs auditable.**
- The 126 page-level leaves and the 17 chapter-level residual **OVERLAP** (the 1872 chapter leaves and
  the 8 archivist chapters ARE page-level gaps); they must be reconciled by volume+page, not summed.

---

## 2. What is OPEN / UNKNOWN (do not treat as resolved)

1. **49 odd-parity gaps — AMBIGUOUS, unresolved.** An odd-numbered page jump is usually NOT a clean
   dropped leaf (a leaf = 2 pages); it is most often an original printing/numbering skip or a torn
   half-leaf — indistinguishable from page numbers alone. We do **not** know which of these 49 need a
   scan. They are NOT confirmed losses and NOT confirmed artifacts.

2. **9 early-1850s volumes (1852–1860, 3,059 pages) — UNAUDITABLE, unknown.** Their corner page numbers
   are not machine-recoverable (diagnosed: top and bottom strips both yield body section-numbers, no
   consistent offset). We literally **cannot see** whether these volumes dropped any leaves. There may
   be missing pages here we cannot currently enumerate. Bounded in size (~3,059 pp), unknown in content.
   (Stakes are lower — these years are chapter-complete, so any undetected drop is a mid-act body leaf,
   not a lost chapter — but "lower stakes" is not "resolved.")

3. **Extra/special sessions — ENTIRELY UNMEASURED.** Extra sessions enacted chaptered statutes but are
   **not in the oracle or the scoreboard at all**, so the 99.98% above is blind to every one of them.
   We have confirmed ≥3 extra-session volumes exist with real, unique acts (1884 / 1926 / 1928), and
   **`production-1927-vol1-26chapters` (the 1926 Extra Session) has 0 parsed acts** — a possible parse
   gap. The full extent of extra-session coverage is uncharted.

4. **Proposition / initiative measures — out of scope here, separate gate.** The `measures-*` volumes
   are the proposition/initiative track (a distinct, not-yet-started parser gate), not part of this
   page/chapter audit.

---

## 3. What is NOT a final answer yet

- **There is NO complete "pages to scan" list.** A draft packet exists
  (`SACRAMENTO_SCAN_PACKET_2026-06-29.md`) covering the **126 confident leaves + the 49 odd-parity
  "inspect" set + the 17 chapter recoveries (deduped)** — but it is a DRAFT, not the answer, because
  the unknowns in §2 (odd-parity resolution, the 9 unauditable volumes, extra sessions) are not closed.
  Do not treat it as "what to bring to Sacramento" until those are resolved.

---

## 4. What closing the gaps would require (not yet done, not yet authorized)

- Resolve the **49 odd-parity** gaps (per-gap: real torn leaf vs printing/numbering artifact — likely
  needs eyes on the page images or the printed index).
- Decide what to do about the **9 unauditable 1850s volumes** (a different page-number method, or an
  explicit accepted-uncertainty statement with the bound stated).
- **Bring extra/special sessions into the oracle/scoreboard** and verify each is present and complete
  (the 1926 Extra Session 0-acts case is the first concrete lead).

---

## 5. Tooling / artifacts (durable)

- Audit tool: `C:\PatoLex-scratch\page_continuity_audit.py` (deterministic; re-OCRs the page-number
  corner, fits a monotone printed=pdf+offset step function with Patrick's position-anchoring). Results:
  `_audit_all.jsonl`. Report: `docs/80_PROJECT_HISTORY/PAGE_CONTINUITY_AUDIT_2026-06-23.md`.
- Lessons recorded this session: scrivener Roman transposition, three-tool glob-vs-alias, VLM-recovery
  ops, position-anchoring/4-digit pagination, and (process) repeated false dismissive labels.

## 6. Honest meta-note

Five dismissive/closure claims this session were wrong on inspection: "99.9%→100%", "~11 misc",
"too few pages to matter", "1883-84 must be re-acquired", and "junk stubs (safe to delete)." Each was
caught by verifying before acting. The standing rule going forward: **do not report a number as
complete, a volume as empty, or a list as final without proving it — and surface unknowns as unknowns.**
