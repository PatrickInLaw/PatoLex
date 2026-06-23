# Scan-Gap Adversarial Verification — 2026-06-22

**Task:** Independently verify EVERY claimed "physical scan gap / needs re-scan / needs re-OCR" asserted
by the OCR-recall recovery sub-agents. Method: render the actual source PDF in
`C:\PatoLex-scratch\chief-clerk-archive\` and read the **printed running-head page number** on each
consecutive PDF page across the claimed gap. Continuous printed page numbers ⇒ NO gap (chapter present
somewhere — DEBUNKED). A real printed-page discontinuity (e.g. printed 1561 then 1564) ⇒ REAL GAP.
Also checked: is the chapter's body present elsewhere in the volume, and does another PDF/volume cover
the pages.

**Read-only.** No DB or parse-file writes. All evidence is page-level and reproducible.

## Headline

57 chapter-claims verified at page level (≈ the "~53 remaining" the brief flagged, plus the cross-volume
ones the notes had self-flagged). By verdict:

| Verdict | Chapters | Breakdown |
|---|---|---|
| **PRESENT-AFTER-ALL (debunked)** | **35** | 1989 ch1440-1467 (28, in Vol4 PDF) · 1959 ch1001 · 1955 ch1139 · 1988 ch398 (each = first chapter of next vol's PDF) · 1951 ch435/756/829/831 (header-loss) |
| **REAL GAP (fully absent printed leaf)** | **19** | 1905 ch389-397 (9) · 1986 ch1357/1358 (2) · 1985 ch505/506/**507** (3) · 1970 ch906/907 (2) · 1981 ch378 · 1929 ch881 · 1927 ch816 |
| **REAL GAP — title leaf only (body present, OCR-recoverable)** | **3** | 1972 ch517 · 1927 ch817 · 1986 ch1359 |

**The single biggest "scan gap" in the corpus (1989 ch1440-1467, 28 chapters) is a pure extraction
artifact — DEBUNKED.** Three "cross-volume gaps" enshrined in lessons/notes (1959 ch1001, 1955 ch1139,
1988 ch398) are also wrong: each is the FIRST chapter of the next volume's PDF. The 4 "1951 scan gaps"
were header-loss, not gaps. **So ~36 of 57 claims (63%) were artifacts, exactly the historical pattern.**
The 22 genuine gaps (19 full + 3 title-only) are concentrated in mid-volume single/double-leaf drops that
need an EXTERNAL source (HathiTrust / Internet Archive), not re-OCR of the existing local scan.

---

## Verification table

| Year | Chapter(s) | Source PDF | Printed pages claimed absent | PDF page idx to open (0-based / viewer 1-based) | Running heads actually read | VERDICT | Evidence |
|---|---|---|---|---|---|---|---|
| 1989 | 1440-1467 (28) | `1989_Vol4_DigestChapters.pdf` | none | idx 2 / pg 3 (ch1440) … idx 230 / pg 231 (ch1467) | "Ch. 1440 ] STATUTES OF 1989 6407 CHAPTER 1440" → contiguous through "Ch. 1467 … 6635"; printed pages run 6407→6635+ continuously, exactly continuing Vol3's last printed page 6406 | **PRESENT-AFTER-ALL** | Vol3 PDF truncates at idx 2173 (printed 6406, start of ch1439). All 28 chapters are full-text in `1989_Vol4_DigestChapters.pdf` (mis-named — it is the Vol4 statute-text continuation). That PDF was never OCR'd into the production set. Re-OCR it. |
| 1959 | 1001 | `1959_Vol2_Chapters.pdf` | none | idx 1 / pg 2 | "Ch. 1001] 1959 REGULAR SESSION 3023 CHAPTER 1001" | **PRESENT-AFTER-ALL** | Vol1 ends printed 3022 (ch1000, idx 2430). Ch1001 is the FIRST chapter of Vol2 (printed 3023). The recovery note/lesson claiming Vol2 "starts at ch1002" was WRONG — it misread Vol2's opening. No gap. |
| 1955 | 1139 | `1955_Vol2_Chapters.pdf` | none | idx 1 / pg 2 | "Ch. 1139] 1955 REGULAR SESSION 2133 CHAPTER 1139" | **PRESENT-AFTER-ALL** | Vol1 ends mid-ch1138; ch1139 is the FIRST chapter of Vol2 (printed 2133). Cross-volume manifest mis-assignment only. |
| 1988 | 398 | `1988_Vol2.pdf` | none | idx 2 / pg 3 | "Ch. 398] STATUTES OF 1988 1749 CHAPTER 398" | **PRESENT-AFTER-ALL** | Vol1 ends printed 1748; ch398 is the FIRST chapter of Vol2 (printed 1749). Note already self-resolved; confirmed. |
| 1986 | 1357, 1358 | `1986_Vol3.pdf` | 4812-4815 | ch1356 last at idx 1074 / pg 1075 (printed 4811); resumes idx 1075 / pg 1076 (printed 4816, ch1359) | idx1074 "Ch. 1356 … 4811" → idx1075 jumps to printed 4816 (ch1359) | **REAL GAP** | Printed 4812-4815 physically absent from Vol3 PDF (held tail of ch1356, title pages of ch1357 & ch1358, title of ch1359). No local PDF covers them. Needs external scan (HathiTrust/IA). |
| 1986 | 1359 | `1986_Vol3.pdf` | title page only (4812-4815) | idx 1076 / pg 1077 (printed 4817) | "Ch. 1359 ] STATUTES OF 1986 4817 …" | **REAL GAP (title leaf only)** | Ch1359 BODY is present from printed 4816/4817; only its title/header page (in the 4812-4815 gap) is absent. Body OCR-recoverable. |
| 1985 | 505, 506, **507** | `1985_Vol1_Chapters.pdf` | 1859-1860 | ch504 last idx 1855 / pg 1856 (printed 1858); resumes idx 1856 / pg 1857 (printed 1861, ch508) | idx1855 "1858 … [Ch. 504" → idx1856 "Ch. 508 … 1861" | **REAL GAP** | Printed 1859-1860 absent → ch505, ch506 AND **ch507** all missing (claim under-counted: it listed only 505/506). Needs external scan. |
| 1981 | 378 | `1981_Vol2.pdf` | 1562-1563 | ch377 last idx 62 / pg 63 (printed 1561); resumes idx 63 / pg 64 (printed 1564, ch379) | idx62 "Ch. 377 … 1561" → idx63 "1564 … [ Ch. 379" | **REAL GAP** | Printed 1562-1563 (entire ch378, an urgency statute) physically absent. Urgency-clause tail visible atop idx63 confirms ch378 was enacted. Needs external scan. |
| 1972 | 517 | `1972_Vol1_Chapters.pdf` | 896-897 | ch516 last idx 894 / pg 895 (printed 895); resumes idx 895 / pg 896 (printed 898, ch517 body) | idx894 "Ch. 516 … 895" → idx895 "898 … [Ch. 517" | **REAL GAP (title leaf only)** | Printed 896-897 (ch517 title/enacting page) absent, but ch517 BODY present from printed 898 (running head "Ch. 517"). Body OCR-recoverable; title needs external source. |
| 1970 | 906, 907 | `1970_Vol1_Chapters.pdf` | 1648 | ch905 last idx 1646 / pg 1647 (printed 1647); resumes idx 1647 / pg 1648 (printed 1649, ch908) | idx1646 "Ch. 905 … 1647" → idx1647 "Ch. 908 … 1649" | **REAL GAP** | Printed leaf 1648 physically skipped at scan time (held ch906, ch907 headings + start of ch908). Orphaned Gov.Code §6103 body tail atop idx1647 confirms dropped leaf. Needs external scan. |
| 1929 | 881 | `1929_Vol1_29Chapters.pdf` | 1962-1963 | ch880 last idx 1962 / pg 1963 (printed 1961); resumes idx 1963 / pg 1964 (printed 1964, ch882) | idx1962 "Ch. 880] … 1961" → idx1963 "1964 … [Ch. 882 CHAPTER 882" | **REAL GAP** | Two consecutive PDF pages span printed 1961→1964 ⇒ printed 1962-1963 (ch881) physically absent. Confirms the recovery "possibly absent" suspicion. Needs external scan. |
| 1927 | 816 | `1927_Vol1_Chapters.pdf` | 1626-1627 | ch815 last idx 1624 / pg 1625 (printed 1625); resumes idx 1625 / pg 1626 (printed 1628, ch817) | idx1624 "Ch. 815] … 1625" → idx1625 "1628 … [Ch. 817" | **REAL GAP** | Printed 1626-1627 absent (held end of ch815, all of ch816, title of ch817). ch816 fully absent. Needs external scan. |
| 1927 | 817 | `1927_Vol1_Chapters.pdf` | title page only (1626-1627) | idx 1625 / pg 1626 (printed 1628) onward | "1628 … [Ch. 817" running head | **REAL GAP (title leaf only)** | ch817 BODY (dairy-products act) present from printed 1628; only its title page (in the 1626-1627 gap) absent. Body OCR-recoverable. |
| 1905 | 389-397 | `1905_Statutes.pdf` | 497-512 | last-before-gap ch388 at idx 561 / pg 562 (printed 496); resume ch398 at idx 569 / pg 570 (printed 519/520) | idx561 printed **496** (ch388, CCCLXXXVIII) → idx562 printed **513**; idx540-561 is a literal DUPLICATE of printed 481-496 | **REAL GAP** | Printed pages 497-512 physically absent; the scan duplicated printed 481-496 (idx540-561) masking the drop. ch389-397 appear NOWHERE in the PDF (roman-heading search idx500-640). `1905_BR.pdf`/`1905_Index.pdf` hold no statute chapters. Duplicated-leaf + dropped-leaf defect. Needs external scan. |
| 1951 | 435 | `1951_Vol1_Chapters.pdf` | none | idx 1298 / pg 1299 (printed 1418) | "[Ch 435] … 1418", body "An act to amend Section 1081 of the Insurance Code"; heads continuous 1415→1418→1419 | **PRESENT-AFTER-ALL** | Header-loss only — OCR garbled the CHAPTER digits. Chapter present, recoverable. |
| 1951 | 756 | `1951_Vol1_Chapters.pdf` | none | idx 1899 / pg 1900 (printed 2020) | "[Ch 756] … 2020", body "An act to amend Section 32002.2 of the Health and Safety Code"; heads continuous 2018→2019→2020 | **PRESENT-AFTER-ALL** | Header OCR-missed on a dense page; chapter present. |
| 1951 | 829 | `1951_Vol1_Chapters.pdf` | none | idx 2196 / pg 2197 (printed 2317) | "CHAPTER 829" + "[Ch. 829]"; body "An act to amend Section 320 of the Vehicle Code"; heads continuous 2316→2317→2318 | **PRESENT-AFTER-ALL** | Header-loss only. |
| 1951 | 831 | `1951_Vol1_Chapters.pdf` | none | idx 2197 / pg 2198 (printed 2318) | "CHAPTER 831" + "[Ch. 831]"; body "An act adopting and authorizing a plan for construction of the San Lucas Dam"; heads continuous | **PRESENT-AFTER-ALL** | Resolves the original agent's "829-or-831" ambiguity: **ch831 = San Lucas Dam act, ch829 = Vehicle Code act.** Header-loss only. |

---

## Durable lesson (the unifying finding)

**"Scan gap" claims fall into three classes, and only the printed running-head page number distinguishes them:**

1. **Extraction/cross-volume artifact (NOT a gap):** the chapter is fully present in another PDF in
   `chief-clerk-archive` that was never OCR'd. The 28-chapter 1989 ch1440-1467 "gap" is the
   `1989_Vol4_DigestChapters.pdf` (a mis-named full-text Vol4). Three "cross-volume" gaps (1959 ch1001,
   1955 ch1139, 1988 ch398) are simply the FIRST chapter of the *next* volume's PDF — the recovery
   agents misread a volume's opening title-page-then-chapter as starting one chapter later. **Always
   check Vol2/Vol3/Vol4 PDFs and the next volume's first page before declaring a cross-volume gap.**
2. **Real physically-absent printed leaf (TRUE gap):** consecutive PDF pages show a printed page-number
   jump (e.g. 1561→1564). The intervening printed pages were never digitized. Confirmed for 1986
   ch1357/1358, 1985 ch505/506/**507**, 1981 ch378, 1970 ch906/907, 1929 ch881, 1927 ch816. These need
   an EXTERNAL source (HathiTrust / Internet Archive), not re-OCR.
3. **Title-leaf-only gap (body present):** the chapter BODY is present and OCR-recoverable, only the
   single title/header page fell in a gap — 1972 ch517, 1927 ch817, 1986 ch1359.

**Correction to prior records:** the 1985 gap also drops **ch507** (the recovery listed only 505/506).
The lesson file `LESSON_2026-06-21_scan_gap_vs_header_loss_visual_recovery.md` and the 1959 visual note
recorded ch1001 as "the only real scan gap of 1959" — that is FALSE; ch1001 is present in
`1959_Vol2_Chapters.pdf`.
