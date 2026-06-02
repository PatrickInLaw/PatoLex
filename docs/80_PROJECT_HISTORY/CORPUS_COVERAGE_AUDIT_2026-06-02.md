# Corpus Coverage Audit — 1872–1911 Statutes vs. Code Amendments

**Date:** 2026-06-02
**Author:** cc (corpus-coverage audit task)
**Status:** READ-ONLY audit. No code/DB/queue/OCR modified.
**Method:** EXPECTED-vs-ACTUAL against authoritative sources (Chief Clerk archive pages, library guides, HathiTrust catalog, the volumes' own title pages), then cross-checked against our manifest, `corpus_page_counts.csv`, the live archive (HEAD requests), and the OCR queue worker code. **Findings are NOT inferred from our file sizes.**

---

## TL;DR (verdicts)

1. **Combination year = 1883 (25th regular session).** From 1883 forward, California published a single title *"Statutes of California, and Amendments to the Codes, Passed at the … Session of the Legislature."* Before that (1873–1881) the general **"Statutes"** and the **"Amendments to the Codes"** (labeled "Code Amendments" by the Chief Clerk) were **separate volumes**. VERIFIED (multiple sources below).

2. **1883 verdict: NOT a source gap. It is a naming/filter trap in our pipeline.** The 1883 *regular-session* statutes are present at the source as the file our manifest calls **`1883Code.pdf` (448 pp, live 25.9 MB)** — the Chief Clerk page labels this file **"Statutes (Chapters 1-23)"** for the 1883 session. Our OCR queue, which only processes `{label}_Statutes.pdf`, **excludes it.** The 15-page `1883_84_1E.pdf` we hold is only the First Extra session. So 1883 regular statutes = **excluded-from-queue**, not missing.

3. **The Code-amendment stream is IN SCOPE but currently OMITTED.** For codified point-in-time law (the whole post-1872 purpose), the "Amendments to the Codes" volumes ARE session law and MUST be OCR'd. The queue worker (`pipeline/5090/queue_worker.py:197`) builds its input path as `{label}_Statutes.pdf` only and never touches `_Code` files. This silently drops the **entire code-amendment stream for 1873–1883**.

4. **The already-"done" 1850–1875 range is itself incomplete w.r.t. code amendments** — the 1873-74 (511 pp) and 1875-76 (136 pp) Code volumes were never queued. CONFIRMED via queue worker logic.

5. **Sessions 1872–1911 that are incomplete in our corpus: at least 6** (1873-74, 1875-76, 1877-78, 1880, 1883, 1885-86) — all due to the `_Code` exclusion and/or the 1883 naming trap. **Zero of these are true source gaps**; every required volume is live and downloadable from the Chief Clerk.

---

## 1. Publication structure & the combination year (VERIFIED)

- **1872:** California adopts its four codes (Civil, Civil Procedure, Penal, Political). From this point the legislature both passes uncodified general acts ("Statutes") AND amends the codes ("Amendments to the Codes").
- **1873–1881 — SEPARATE volumes.** The Chief Clerk's own 1873-74 archive page labels `1873_74statutes.PDF` as **"Statutes"** and `1873_74Code.PDF` as **"Code Amendments"** — two distinct law volumes. The 1880 page identically labels `1880.PDF` = "Statutes" and `1880Code.PDF` = "Code Amendments." A library record describes "*Amendments to the codes of California … passed at the twentieth session of the legislature 1873-4*" as a standalone publication; the Advancing Genealogist statutory-law index lists, for 1874, BOTH "Statutes of California, 20th Session" AND "Acts Amendatory of the Codes, Passed at the Twentieth Session" as separate volumes.
- **1883 (25th session) — COMBINED.** The 1883 volume's title page reads *"Statutes of California, and Amendments to the Codes: Passed at the Twenty-Fifth Session of the Legislature, 1883"* (HathiTrust / reprint catalog records). From 1883 forward the single combined title is the norm; multiple library guides state "From 1883–1919, California session laws were published as Statutes of California and Amendments to the Codes." **Combination year = 1883.** (NOTE: the Chief Clerk *retroactively* titles every archive entry 1871-72 onward "Statutes and Amendments to the Codes," but that is a modern catalog label, not the historical volume title; the per-session file labels — "Statutes" vs "Code Amendments" — reveal the true separate-vs-combined structure.)

**Caveat (could-not-fully-confirm):** Whether the transition is *exactly* clean at 1883 vs. phased over 1881–1885 is not 100% pinned from a single authoritative statement; the 1883 title-page evidence + the disappearance of a separately-labeled "Code Amendments" file after 1880 is strong corroboration. Treat "1883" as VERIFIED for the combined *title*; the 1885-86 archive still ships a small separate `..code_0.PDF` (see §3), so the physical separation lingered into 1885-86 for the Extra Session.

---

## 2. Per-session coverage map, 1872–1911

Legend for **gap type**: `none` · `excluded-from-queue` (held but not OCR'd) · `merged` (code amendments folded into the combined Statutes volume) · `missing-from-source` · `anomaly` (file size/label suspicious).

| Session | Expected law volume(s) | In manifest? | Held (pages) | In OCR queue? | Gap type |
|---|---|---|---|---|---|
| **1871-72 (19th)** | Statutes (pre-code era; "Revised" = code drafts) | Yes (Statutes + Revised) | Statutes 1064; Revised 1066 | Yes (Statutes) — in_progress | none for Statutes; *Revised* (code drafts) not queued — low priority |
| **1873-74 (20th)** | Statutes **+** Amendments to the Codes | Yes (both) | Statutes 1086; **Code 511** | Statutes only (pending) | **excluded-from-queue (Code)** |
| **1875-76 (21st)** | Statutes **+** Amendments to the Codes | Yes (both) | Statutes 1025; **Code 136** | Statutes only (pending) | **excluded-from-queue (Code)** |
| **1877-78 (22nd)** | Statutes **+** Amendments to the Codes | Yes (both) | Statutes 1153; **Code 134** | Statutes only | **excluded-from-queue (Code)** |
| **1880 (Extra/23rd)** | Statutes **+** Amendments to the Codes | Yes (both) | Statutes 300; **Code 364** | Statutes only | **excluded-from-queue (Code)** |
| **1881 (24th)** | Statutes (+ Extra) | Yes (Statutes + Extra) | Statutes 151; Extra 24 | Statutes only | none for general statutes; no separate Code file at source (merged begins) |
| **1883 (25th)** | **Statutes & Amendments to the Codes (combined)** + 1st Extra | Partial — combined vol is mislabeled `1883Code.pdf`; only `_1E` (Extra) named as Statutes | **`1883Code.pdf` = 448 pp** (the REGULAR session, live 25.9 MB); Extra `_1E` 15 pp | **NO — the 448pp regular vol is excluded; queue would look for `1883-84_Statutes.pdf` which is only the 15pp Extra** | **excluded-from-queue (the main regular-session volume) — NAMING TRAP** |
| **1885-86 (26th)** | Statutes (combined) + small Extra | Yes (Statutes `1885.pdf` 294pp; `code_0` 6pp) | Statutes 294; code_0 **6** (live 105 KB) | Statutes only | general statutes covered; `code_0` is a tiny Extra-Session file (anomaly/low-priority, see §3) |
| **1887 (27th)** | Combined Statutes | Yes | 306 | Yes (Statutes) | none |
| **1889 (28th)** | Combined Statutes | Yes | 792 | Yes | none |
| **1891 (29th)** | Combined Statutes | Yes | 593 | Yes | none |
| **1893 (30th)** | Combined Statutes | Yes | 716 | Yes | none |
| **1895 (31st)** | Combined Statutes | Yes | 508 | Yes | none |
| **1897 (32nd)** | Combined Statutes | Yes | 708 | Yes | none |
| **1899 (33rd)** | Combined Statutes | Yes | 566 | Yes | none |
| **1900-01 (34th + 1st Extra)** | Combined Statutes + 1st Extra | Yes (Statutes 1030 + `1E` 40) | 1030 / 40 | Statutes (Extra not separately queued) | minor: Extra session not queued |
| **1903 (35th)** | Combined Statutes | Yes | 812 | Yes | none |
| **1905 (36th)** | Combined Statutes | Yes | 1126 | Yes | none |
| **1906-07 (1st Extra + 37th)** | Statutes + 1st Extra | Yes (Statutes 1415 + `1E` 101) | 1415 / 101 | Statutes | minor: Extra not queued |
| **1907-09 (38th + 2 Extras)** | Statutes + 1E + 2E | Yes (Statutes 1403 + 1E 34 + 2E 37) | — | Statutes | minor: Extras not queued |
| **1910-11 (39th + Extras)** | Statutes + multiple Extras | Yes (Statutes 2240 + several E files) | 2240 + extras | Statutes | minor: Extras not queued |

**Bottom line for 1872–1911:** every *general statutes* volume is held and (for ≥1885) queued. The **gaps are (a) the separately-published Amendments-to-the-Codes volumes for 1873-74, 1875-76, 1877-78, 1880, and (b) the 1883 combined regular-session volume mislabeled `1883Code.pdf`.** None are missing from the source.

---

## 3. The 1883 finding (definitive)

- **Chief Clerk 1883-84 page** labels the file `1883Code.pdf` as **"Statutes (Chapters 1-23)"** and "Resolutions" for the 1883 session, plus `1883Code_BR` (Treasurer's Report) and `1883Code_Index`. The only thing labeled separately as the Extra session is `1883_84_1E.pdf`.
- **Our manifest** (lines for 1883-84) lists `1883Code.pdf`, `1883Code_BR`, `1883Code_Index`, and `1883_84_1E.pdf` — i.e., we DID acquire the 448-page regular-session volume, but under the misleading "_Code" name.
- **Live HEAD:** `1883Code.pdf` = HTTP 200, 25,916,297 bytes — a full ~448-page volume, consistent with a complete combined Statutes+Codes book.
- **Verdict:** The 1883 regular-session statutes are **(b) present in the source but missed by our pipeline** — specifically *excluded-from-queue* because (i) the file is named `1883Code.pdf` and our queue only ingests `*_Statutes.pdf`, and (ii) the only file matching the Statutes pattern, `1883-84_Statutes.pdf` (15 pp), is actually just the First Extra session. The page-counts CSV even shows two 15-page entries (`1883-84_Statutes.pdf` and `1883-84_Statutes_1E.pdf`) — the same Extra-session content, with the real 448-page regular volume sitting unqueued as `1883-84_Code.pdf`. **This is exactly the "entirely missing volume" the prior file-size analysis was blind to.**

---

## 4. Are the `_Code` volumes in-scope? (YES — stated plainly)

The "Amendments to the Codes" volumes are the legislature's official, chaptered changes to the 1872 codes. For a **point-in-time CODIFIED-law** archive they are not optional — they are the *more* important half post-1872, because they are how the Civil/Penal/CCP/Political codes actually changed session-to-session. The Chief Clerk labels them "Code Amendments" and serves them as primary law alongside "Statutes." **They MUST be OCR'd and ingested.** Confirmed live & downloadable:

| File | Label (Chief Clerk) | Pages | Live size | Queued? |
|---|---|---|---|---|
| `1873-74_Code.pdf` | Code Amendments | 511 | 17.5 MB | **No** |
| `1875-76_Code.pdf` | Code Amendments | 136 | 6.7 MB | **No** |
| `1877-78_Code.pdf` | Code Amendments | 134 | (held) | **No** |
| `1880_Code.pdf` | Code Amendments | 364 | (held) | **No** |
| `1883_84_Code.pdf` (the combined regular vol) | "Statutes (Ch 1-23)" | 448 | 25.9 MB | **No** |

**The already-ingested 1850–1875 corpus is therefore incomplete:** it OCR'd `1873-74_Statutes` and `1875-76_Statutes` but skipped the 1873-74 (511 pp) and 1875-76 (136 pp) Code volumes. Flag for re-ingest.

---

## 5. The 1885-86 `code_0` anomaly & the small "NNChapters" fragments

- **`1885-86_Code.pdf` = 6 pp (live `1885_86code_0.PDF` = 105 KB).** Chief Clerk labels `1885_86code_0.PDF` as the **Extra-Session** "Statutes/Resolutions." This is a genuinely tiny Extra-session file, not a truncated full volume — by 1885 the substantive code amendments are folded into the combined `1885.pdf` (294 pp) general volume. **Verdict: not a major gap; low priority** (Extra-session content worth queuing for completeness).
- **`1927_Vol1_26Chapters` (4 pp), `1929_Vol1_28Chapters` (6 pp), `1935_Vol1_34Chapters` (44 pp):** these are the **trailing-chapters/extra-session fragments of the *prior* legislature** (26th, 28th, 34th sessions) bound into the next biennium's Vol 1, alongside that year's full `Vol1_Chapters` (1927=2399pp, 1929=2276pp, 1935=2679pp). They are real but small extra-session supplements, **NOT** evidence of a missing main volume. **Verdict: real small fragments, low priority; queue for completeness but not urgent.** (Outside the 1872–1911 core scope.)

---

## 6. Prioritized remediation list

### A. TRUE corpus gaps our pipeline must close (held at source, excluded by us) — HIGH
1. **`1883-84_Code.pdf` (448 pp) — the 1883 regular-session combined Statutes & Amendments to the Codes.** Highest priority: it is an *entire regular session* currently represented in the queue only by a 15-page Extra fragment. Add to queue with correct file mapping.
2. **`1873-74_Code.pdf` (511 pp)** — Code Amendments, 20th session. (Re-ingest; "done" range omitted it.)
3. **`1877-78_Code.pdf` (134 pp)** — Code Amendments, 22nd session.
4. **`1880_Code.pdf` (364 pp)** — Code Amendments, 23rd session.
5. **`1875-76_Code.pdf` (136 pp)** — Code Amendments, 21st session. (Re-ingest; "done" range omitted it.)

### B. Pipeline defect to fix (root cause) — HIGH
6. **`queue_worker.py:197` hardcodes `{label}_Statutes.pdf`.** It must enumerate ALL body volumes per session (Statutes + Code/Code-Amendments + Extra-session statutes), not a single fixed suffix. The queue-state file should list each PDF as its own work item, not one item per year. The `is_body` column in `corpus_page_counts.csv` already marks Statutes-bearing files — but note it marks `1873-74_Code.pdf` as `FALSE`/non-body, which is **incorrect** for code amendments and likely the origin of the exclusion. Re-classify `_Code` (Code Amendments) volumes as body.

### C. Lower priority — completeness
7. Extra-session statute files not currently queued: `1881_Extra`, `1900-01_1E`, `1906-07_1E`, `1907-09_1E/2E`, `1910-11_*E*`, `1885-86 code_0`. Add for full coverage.
8. Post-1911 trailing-chapter fragments (`1927_26Chapters`, `1929_28Chapters`, `1935_34Chapters`, etc.) — queue for completeness, out of core scope.

---

## 7. Sources

- Chief Clerk archive index — https://clerk.assembly.ca.gov/archive-list?archive_type=statutes
- Chief Clerk 1873-74 (labels `1873_74Code.PDF` = "Code Amendments") — https://clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-1873-74
- Chief Clerk 1880 (labels `1880Code.PDF` = "Code Amendments") — https://clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-1880
- Chief Clerk 1883-84 (labels `1883Code.pdf` = "Statutes Ch 1-23") — https://clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-1883-84
- Chief Clerk 1885-86 (`1885_86code_0.PDF` = Extra Session) — https://clerk.assembly.ca.gov/historical-information/archive-list/statutes-and-amendments-codes-1885-86
- HathiTrust catalog — Statutes of California — https://catalog.hathitrust.org/Record/010063843
- 1883 25th-session combined title (reprint catalog) — https://www.thegreatbritishbookshop.co.uk/collections/reference/products/statutes-of-california-and-amendments-to-the-codes-passed-at-the-twenty-fifth-session-of-the-legislature-1883-classic-reprint
- USF Law — Finding California Legislative History — https://legalresearch.usfca.edu/califleghist/StatutoryBackground
- Loyola Law School session-laws guide — https://guides.library.lls.edu/c.php?g=497693&p=3407408
- Advancing Genealogist — Historic California Statutory Law (1874 lists Statutes + Acts Amendatory of the Codes separately) — https://advancinggenealogist.com/historic-california-statutory-law/

### Internal evidence
- `docs/30_SYSTEM_DESIGN/sources/chief_clerk_statutes_manifest.csv` (1883 has no regular `_Statutes` URL; only `1883Code*` + `_1E`)
- `C:\Users\PatrickKolasinski\PatoLex-scratch\corpus_page_counts.csv` (`1883-84_Statutes.pdf`=15pp dup of Extra; `1883-84_Code.pdf`=448pp; `_Code` rows marked `is_body=FALSE`)
- `pipeline/5090/queue_worker.py:197` — `pdf = ARCHIVE / f"{label}_Statutes.pdf"` (single-file-per-session; excludes `_Code`)
- `pipeline/5090/production_queue_state.json` — one work-item per year label; 1873-74/1875-76 pending as Statutes-only
