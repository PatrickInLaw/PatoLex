# Residual-71 Recovery via Printed Contents — COMPLETE — 2026-07-24 (cc019)

**Result: 71 of 71 recovered. Zero remaining. No archive scan required for any of them.**

**Method:** contents-anchored recovery (the technique cc015 used for the 1854 dual-series parse, 174/174). Every biennial *Statutes of California* volume carries a chapter-ordered printed **CONTENTS** table in front matter (PDF p3 onward), columns `Chap. | TITLE OF ACT | No. of bill and where introduced | Page`.

**Chain of custody, per row:** Tesseract OCR located the page only (cheap, deterministic, monotonicity-filtered) → **Opus 5 read the printed row visually** and transcribed chapter, title, enactment clause, bill, and printed page. **No recorded value came from OCR.** This mattered: the OCR sweep wrongly classified **1878 ch. 418** as an Amendments-volume redirect; the printed page shows a real act with a real page. Visual verification caught it.

**Cross-corroboration:** four chapters were independently read from their *body* pages earlier in the session (1866/143, 1876/91, 1878/173, 1874/261). All four agree with the contents on chapter number, title, and printed page.

---

## Final accounting of the 71

| Class | Count | Meaning | Action |
|---|---|---|---|
| **Ordinary acts** — normal `[Approved <date>]` | **62** | Recoverable from the volume we already hold | Parse fix + reparse |
| **`[See volume of Amendments to the Codes.]`** | **5** | Enacted, but text lives in a **companion volume** | **Not in this book. Never was.** Needs the Amendments volume — NOT an archive scan |
| **Special enactment paths** (unsigned / veto override) | **4** | Became law without the Governor's signature | Parse fix (defect 1) |
| **TOTAL** | **71** | | **0 require an archive visit** |

### The 5 that are not in these volumes at all

**1874 ch. 587** (S.B. 506) · **1874 ch. 679** (A.B. 507) · **1876 ch. 306** · **1876 ch. 497** · **1876 ch. 498**

All read `[See volume of Amendments to the Codes.]` — no title, no page. Several still carry a bill number, so the enactment is identifiable. **No amount of re-OCR, re-reading, or re-scanning of these seven PDFs will ever produce their text.** They must be sourced from the companion *Amendments to the Codes* volume. Any residual scoreboard that counts them as "missing from the statutes volume" will never reach zero.

### The 4 special enactment paths

| Year/Ch. | Printed enactment clause | Path |
|---|---|---|
| 1866 ch. 143 | "became law by the operation of Constitution, February 27, 1866" | unsigned (10-day lapse) |
| 1866 ch. 198 | "became law by operation of the Constitution, March 8, 1866" | unsigned (10-day lapse) |
| 1870 ch. 431 | "became a law by constitutional provision April 3, 1870" | unsigned (10-day lapse) |
| **1870 ch. 143** | **"became a law by a constitutional majority of both Houses, over the Governor's objections, March 4, 1870"** | **veto override** |

---

## ★ Structural findings

### Finding A — THREE enactment paths, not one

The printed contents states how each act became law. **Only the first is modeled by the pipeline.**

| # | Path | Printed forms observed | Modeled? |
|---|---|---|---|
| 1 | Signed by the Governor | `—approved February 18, 1876` | ✅ yes |
| 2 | **Became law unsigned** (10-day lapse) | `became law by the operation of Constitution` · `became law by operation of the Constitution` · `became a law by constitutional provision` | ❌ **no** |
| 3 | **Passed over the Governor's veto** | `became a law by a constitutional majority of both Houses, over the Governor's objections` | ❌ **no** |

**The wording is not stable** — three distinct phrasings for path 2 alone. A `LAPSE_RE` must anchor on the stable core `became (a )?law` and treat the qualifier as free text, **not** match any single phrasing. Paths 2 and 3 are constitutionally distinct and must be recorded as distinct values, not collapsed.

**These cluster.** 1870 ch. 428, 429, 430, **431** are four *consecutive* unsigned enactments, all dated April 3, 1870 — bills passed at the close of session hit the ten-day window together. That is why they concentrate in the residual instead of scattering.

### Finding B — the bracket defect, quantified

`HUMAN_REVIEW_LIST_2026-06-22.md` sends a reviewer to **PDF 224–227** for 1872 ch. 125–128, labelled *"multi-act cluster."*

| Source | Value |
|---|---|
| Contents (printed pages) | ch. 125 → **131** · 126 → **131** · 127 → **132** · 128 → **134** |
| Measured PDF offset (1872) | PDF = printed **+ 90** (PDF p225 = printed 135, read directly) |
| **True PDF pages** | **221–222** (ch. 125–127); 224 (ch. 128) |
| Range given | 224–227 |

The stated range does not merely miss — **it lands on chapter 128's own body.** The long roads act at printed 135–136 (*"shall not apply to … the Town of San Luis Obispo"*) is ch. 128, matching its contents title exactly. The "multi-act cluster" label is also wrong: these are ordinary acts on consecutive pages.

Similarly, 1866 ch. 343/344/345 — labelled *"multi-act cluster (343/344/345 share this band)"* — are three ordinary acts on **three consecutive pages** (415, 416, 417).

### Finding C — `[See volume of Amendments to the Codes.]` is a large, real class

Not an artifact, not a gap. Extremely common in 1874–1878. On **one** 1876 contents page (p0029) nine chapters carry it: 488, 490, 497, 498, 499, 502, 504, 505, 506. Any parser reading only the statutes volume will see these as permanent holes.

### Finding D — headings that are not "An Act…"

`is_confident_act` requires `AN_ACT_RE` to match. Two observed forms defeat it:

- **1876 ch. 508** — `[An amendment to the Code, but which also repeals the Act of March twenty-eighth, eighteen hundred and seventy-four, in relation to solvent debts]` · S.B. 391 · **p. 772**. Bracketed descriptive text, **but it has a page — the act IS printed in this volume.**
- **1870 ch. 427** — `Charter of the City of Stockton—An Act to reincorporate the City of Stockton`. Begins "Charter of…".

### Finding E — the printed volumes contradict themselves

**1874 ch. 261:** the contents places ch. 260 *and* ch. 261 both on printed **p. 358**. The body running head on that page is printed **`CHAPTER CLXI.`** (161) where `CCLXI` (261) belongs. **The contents is the correct witness; the body running head is the typo.** Two independent printed sources inside the same volume disagree — and cross-checking them resolves it without inference.

The reverse also occurs: **1866 contents** prints **`242`** where **342** belongs (*"An Act to provide for a system of common schools,"* S.B. 226, p. 383). So misprints exist in **both** directions. Neither the contents nor the body running heads can be trusted alone; agreement between them is the reliable signal.

### Finding F — bill designations vary more than expected

Observed: `A.B.` · `S.B.` · `S.S.B.` (substitute senate) · `Sub. A.B.` · `S.A.B. 1,100` · `Substitute for S.B. 475` · `S.B. 517, substitute for S.B's 105, 122, 191 and 369`. The 1870 volume uses an entirely different column layout (`Where introduced` / `No. of bill` split into two columns) from the other six.

---

## Verified rows — all 71

Every row read visually off the printed contents page.

### 1866 — `1865-66_Statutes.pdf` (10/10)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 143 | An Act for the relief of J. B. Cook, County Treasurer of Lake County | **became law by the operation of Constitution, Feb 27, 1866** | A.B. 56 | 126 |
| 150 | An Act to authorize Mart T. Smith to construct and maintain a wharf at Punta Arenas, Mendocino | approved Feb 28, 1866 | S.B. 10 | 132 |
| 198 | An Act to authorize the executors of Joseph L. Folsom, deceased, to sell real estate of their testator at private sale without notice | **became law by operation of the Constitution, Mar 8, 1866** | A.B. 109 | 191 |
| 275 | An Act granting to the Black Diamond Coal Mining Company the right to construct a tramroad or railroad from the mines at Mount Diablo to the San Joaquin River | approved Mar 20, 1866 | S.B. 211 | 307 |
| 343 | An Act to authorize the Board of Supervisors of San Luis Obispo County to fix the amount of the bond of the Tax Collector | approved Mar 26, 1866 | S.B. 222 | 415 |
| 344 | An Act to provide for the time of holding the County Court and Probate Court of Contra Costa | approved Mar 26, 1866 | S.B. 308 | 416 |
| 345 | An Act to provide for the construction of a canal for irrigating certain lands between the Mokelumne and Calaveras Rivers, San Joaquin County | approved Mar 26, 1866 | S.B. 161 | 417 |
| 423 | An Act to confirm a certain deed of the Public Administrator of the City and County of San Francisco | approved Mar 31, 1866 | S.B. 405 | 532 |
| 448 | An Act to provide for the establishment, maintenance, and protection of public roads in Napa County | approved Mar 31, 1866 | S.B. 412 | 570 |
| 613 | An Act to fix the compensation of the County Clerk and County Superintendent of Public Schools of San Luis Obispo | approved Apr 2, 1866 | S.B. 350 | 838 |

### 1868 — `1867-68_Statutes.pdf` (1/1)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 483 | An Act to aid in giving effect to an Act of Congress relating to the California and Oregon Railroad Company | approved Mar 30, 1868 | S.B. 493 | 655 |

### 1870 — `1869-70_Statutes.pdf` (9/9)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 143 | An Act to provide and pay for services rendered for the City and County of San Francisco | **became a law by a constitutional majority of both Houses, over the Governor's objections, Mar 4, 1870** | Senate 7 | 146 |
| 181 | An Act for the protection of deer in the County of San Mateo | approved Mar 12, 1870 | Assembly 107 | 279 |
| 384 | An Act to establish a Municipal Criminal Court in the City and County of San Francisco | approved Mar 31, 1870 | Assembly 536 | 528 |
| 431 | An Act granting certain privileges to the Central Railroad Company of San Francisco | **became a law by constitutional provision Apr 3, 1870** | Senate 192 | 624 |
| 453 | An Act to provide for the funding of the indebtedness of Levee District Number One, Sutter County | approved Apr 2, 1870 | Assembly 714 | 657 |
| 483 | An Act to create a Board of Water Commissioners in the City of Los Angeles, and to define their powers and duties | approved Apr 2, 1870 | Senate 607 | 702 |
| 484 | An Act to empower the City and County of San Francisco to aid in the construction of the Southern Pacific Railroad | approved Apr 2, 1870 | Senate 666 | 707 |
| 491 | An Act to amend an Act declaring certain rivers and creeks navigable, passed February eighteenth, 1851 | approved Apr 4, 1870 | Assembly 728 | 721 |
| 525 | An Act to determine the lines and grades of streets, avenues, highways and lanes in the City and County of San Francisco | approved Apr 4, 1870 | Assembly 406 | 782 |

### 1872 — `1871-72_Statutes.pdf` (14/14)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 125 | An Act amendatory of an Act to regulate fees of office, approved March 28, 1868 | approved Feb 20, 1872 | A.B. 144 | 131 |
| 126 | An Act to amend an Act concerning roads and highways in the County of Mendocino… | approved Feb 21, 1872 | A.B. 110 | 131 |
| 127 | An Act to amend "An Act to provide for the formation of corporations for the accumulation and investment of funds and savings," approved April 11, 1862 | approved Feb 21, 1872 | S.B. 87 | 132 |
| 128 | An Act concerning roads in the Counties of Santa Barbara and San Luis Obispo | approved Feb 21, 1872 | S.B. 136 | 134 |
| 363 | An Act to amend an Act concerning street railroads, approved March 29, 1870 | approved Mar 23, 1872 | A.B. 683 | 515 |
| 364 | An Act to restore the Great Register of the County of Sutter | approved Mar 23, 1872 | A.B. 570 | 516 |
| 417 | An Act to add additional sections to the Political Code | approved Mar 27, 1872 | A.B. 613 | 586 |
| 418 | An Act for the relief of purchasers of State lands | approved Mar 27, 1872 | A.B. 700 | 587 |
| 433 | An Act to repeal, in part, an Act to make, open, and establish a public street in San Francisco, to be called Montgomery Street South… | approved Mar 28, 1872 | A.B. 83 | 646 |
| 434 | An Act to extend the time in which Swamp Land Districts 68, 69, and 70 shall complete their work of reclamation | approved Mar 28, 1872 | A.B. 306 | 649 |
| 435 | An Act to establish Pilots and Pilot regulations for the port of San Diego | approved Mar 26, 1872 | A.B. 358 | 650 |
| 436 | An Act concerning streams in the County of Santa Clara | approved Mar 28, 1872 | S.B. 460 | 652 |
| 439 | An Act appropriating fifty-six thousand dollars in United States legal tender notes for the necessary incidental expenses of the State Capitol and Governor's Mansion | approved Mar 28, 1872 | S.B. 500 | 655 |
| 538 | An Act to amend an Act to regulate fees in office, approved April 10, 1855 | approved Mar 30, 1872 | S.B. 465 | 776 |

### 1874 — `1873-74_Statutes.pdf` (4/4)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 261 | An Act to authorize the payment of a debt on Washington School District, Cloverdale Township, Sonoma County | approved Mar 13, 1874 | S.B. 323 | **358** ⚠ body head misprinted `CHAPTER CLXI.` |
| **587** | **`[See volume of Amendments to the Codes.]`** | — | S.B. 506 | — |
| 678 | An Act to legalize certain proceedings in Reclamation District No. 124 | approved Mar 30, 1874 | S.B. 436 | 957 |
| **679** | **`[See volume of Amendments to the Codes.]`** | — | A.B. 507 | — |

### 1876 — `1875-76_Statutes.pdf` (22/22)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 91 | An Act to provide for the funding of the levee indebtedness of the City of Marysville | approved Feb 18, 1876 | A.B. 304 | 60 |
| **306** | **`[See volume of Amendments to the Codes.]`** | — | — | — |
| 403 | An Act to provide for the distribution of school moneys in the County of Marin | approved Mar 30, 1876 | A.B. 456 | 568 |
| 417 | An Act to amend "An Act to regulate salaries and fix the compensation of certain county officers in the County of Sonoma," approved March 16, 1874 | approved Mar 30, 1876 | A.B. 733 | 576 |
| 418 | An Act in relation to the county officers of Santa Cruz County, their fees and salaries | approved Mar 30, 1876 | A.B. 476 | 576 |
| 421 | An Act to regulate fees of office and salaries of officers in the County of San Diego | approved Mar 31, 1876 | S.S.B. 443 | 586 |
| 431 | An Act to amend "An Act concerning roads and highways in the County of Santa Clara," approved March 18, 1874 | approved Mar 31, 1876 | A.B. 486 | 606 |
| 438 | An Act to permit Nancy Wilson (a widow) to redeem certain lands sold to the State for delinquent taxes for FY 1874–75 | approved Mar 31, 1876 | A.B. 776 | 623 |
| 442 | An Act to utilize the prison labor and govern the House of Correction of the City and County of San Francisco | approved Mar 31, 1876 | A.B. 463 | 632 |
| 443 | An Act to authorize the Board of Supervisors of Sutter County to redistrict North Butte, Buttesylvania, and Columbia School Districts | approved Mar 31, 1876 | A.B. 695 | 636 |
| 447 | An Act to amend an Act to protect agriculture and to prevent the trespassing of animals in Tehama County, approved March 30, 1874 | approved Mar 31, 1876 | S.S.B. 519 | 643 |
| 452 | An Act to authorize the Board of Supervisors of Lake County to levy a special tax | approved Mar 31, 1876 | A.B. 587 | 648 |
| 459 | An Act in relation to public roads in the County of Sacramento | approved Apr 1, 1876 | A.B. 792 | 658 |
| 477 | An Act to authorize the Controller and Treasurer of State to transfer certain funds | approved Apr 1, 1876 | S.B. 287 | 723 |
| 478 | An Act to amend "An Act to incorporate the City of Gilroy," approved March 12, 1870 | approved Apr 1, 1876 | S.B. 647 | 724 |
| **497** | **`[See volume of Amendments to the Codes.]`** | — | — | — |
| **498** | **`[See volume of Amendments to the Codes.]`** | — | — | — |
| 503 | An Act to transfer certain funds in the State treasury belonging to the State Harbor Commission | approved Apr 3, 1876 | S.B. 501 | 761 |
| 508 | `[An amendment to the Code, but which also repeals the Act of March 28, 1874, in relation to solvent debts]` ⚠ non-"An Act" heading | — | S.B. 391 | 772 |
| 518 | An Act to regulate the practice of medicine in the State of California | approved Apr 3, 1876 | S.B. 549 | 792 |
| 522 | An Act to authorize James McClatchy to sue the County of Sacramento | approved Apr 1, 1876 | S.B. 646 | 796 |
| 541 | An Act to provide a supply of water for the University, and for the Asylum for the Deaf, Dumb, and Blind | approved Apr 1, 1876 | A.B. 711 | 816 |

### 1878 — `1877-78_Statutes.pdf` (11/11)

| Ch. | Title | Enactment | Bill | p. |
|---|---|---|---|---|
| 173 | An Act to provide for the building of a school house in the Fresno City School District, County of Fresno | approved Mar 9, 1878 | — | 205 |
| 418 | An Act to provide for the opening of new streets and for the extending and widening of existing streets in the City of San José ⚠ *OCR wrongly called this an Amendments redirect* | approved Mar 28, 1878 | S.B. 517 | 620 |
| 428 | An Act to amend an Act to establish a Board of Commissioners for the former Pueblo or City of Sonoma… approved March 30, 1868 | approved Mar 29, 1878 | S.B. 457 | 633 |
| 441 | An Act to close an unused street in San Francisco | approved Mar 29, 1878 | S.B. 598 | 682 |
| 447 | An Act in relation to division fences in the County of Sonoma, and the lines of counties bordering thereon | approved Mar 29, 1878 | A.B. 198 | 692 |
| 448 | An Act to provide a new Great Register for the County of Fresno and other counties, and re-register the votes thereof | approved Mar 29, 1878 | A.B. 274 | 693 |
| 449 | An Act to prohibit and punish the sale of adulterated syrup | approved Mar 29, 1878 | A.B. 352 | 695 |
| 484 | An Act giving a lien to loggers and laborers, employed in logging camps, upon the logs cut and hauled by the persons who employ them | approved Mar 30, 1878 | A.B. 417 | 747 |
| 534 | An Act to confer further powers on the Board of Regents of the University of the State of California | approved Mar 30, 1878 | S.B. 672 | 834 |
| 642 | An Act to provide for the payment of deficiencies in the appropriation for procuring and listing lands to the State by the United States, FY 24–25 | approved Apr 1, 1878 | A.B. 568 | 987 |
| 662 | An Act to provide for the election of Supervisors in the County of Mendocino | approved Apr 1, 1878 | A.B. 802 | 1021 |

---

## Consequences

1. **The archive trip does not need any of these.** `ARCHIVES_VISIT_PACKET_2026-07-27.md` §4 already excluded the 71; this closes it definitively with per-chapter evidence.
2. **`HUMAN_REVIEW_LIST_2026-06-22.md` is superseded.** No human needs to page through seven volumes. Its bracket ranges are unreliable (see Finding B) and its "multi-act cluster" labels are wrong.
3. **The residual can never reach zero as currently defined** — 5 of the 71 are in a different book. They need re-classification, not recovery.
4. **The parser work has a validation set.** These 71 rows (chapter → title → date → bill → printed page) are now a fixture set for defects 1–3. After the fixes, a reparse should independently rediscover the 62 ordinary acts and the 4 special-path acts.
5. **Body-text OCR is still owed** for these chapters. This pass recovers the *identity* (number, title, date, page) — not the statutory text.
