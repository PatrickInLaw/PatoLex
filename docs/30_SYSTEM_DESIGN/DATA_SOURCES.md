# Data Sources & Reconstruction Strategy (Gate B Report)

**Status:** Gate B complete (cc002, 2026-05-31). Recon performed by sonnet subagents; synthesized here. No code written.

This document is the authoritative record of *what California legislative data actually exists* and *how PatoLex reconstructs point-in-time statute text from it*. It drives the schema (Gate C) and pipeline (Gate D).

---

## 1. The Source: leginfo PUBINFO bulk data

- **Host:** `https://downloads.leginfo.legislature.ca.gov/` (the `faces/downloadList.xhtml` page 404s; the downloads subdomain is the real endpoint).
- **Format:** Biennial archives `pubinfo_YYYY.zip` (odd-year session start), **1989 → 2025**. A MySQL database named `capublic`, dumped as tab-delimited `.dat` files + per-row `.lob` text files, with `pubinfo_load.zip` providing the schema DDL.
- **Public domain** (Gov. Code §10248.5).
- **Size:** Current archive (`pubinfo_2025.zip`) ≈ 915 MB compressed, ≈ 1.56 GB uncompressed (193k files). The statute-text corpus proper is ≈ **215 MB** (162,169 current sections, avg ~1.3 KB each) across **30 codes + the Constitution**.

### Key tables
- `LAW_SECTION_TBL` — current code text. Columns include `law_code`, `section_num`, `op_statues`/`op_chapter`/`op_section` (the *enacting* statute of the current text), `effective_date` (populated ~58%), `law_section_version_id`, `history` (human-readable amendment string, 100% populated), `content_xml` (the text, as `<caml:Content>` XML in a `.lob`), `active_flg`.
- `LAW_TOC_TBL` / `LAW_TOC_SECTIONS_TBL` — the code hierarchy (division/title/part/chapter/article) and section ordering. Gives us the browse tree directly.
- `CODES_TBL` — the 30 code abbreviations (BPC, CIV, PEN, GOV, …) + CONS.
- `BILL_VERSION_TBL` — **every version of every bill, including chaptered text**, as XML in `.lob` files. `urgency` flag, `bill_version_action_date` (chaptering date on the "Chaptered" version).
- `BILL_TBL` / `BILL_HISTORY_TBL` — bill metadata (chapter number/year) and the action log.

---

## 2. THE CRITICAL FINDING — there are no historical text snapshots

**`LAW_SECTION_TBL` is a current-law snapshot, not a time series.** Every row in the current archive has `active_flg='Y'`; the loader `TRUNCATE`s and replaces on each load. There is no prior-version text, no repealed-version text, no version chain in the law tables. Worse: the **older archives (1989–2003 inspected) do not contain the law tables at all** — only bill data. So we cannot simply diff biennial code snapshots; the historical code text is not retrievable that way.

**Consequence:** Point-in-time text cannot be *downloaded*. It must be **reconstructed** by parsing chaptered bill text (`BILL_VERSION_TBL`, available back to the 1993–94 session) and applying each amendment to each section in operative order. The current `LAW_SECTION_TBL` snapshot becomes the **end-state validation anchor**: reconstruct forward from the earliest available bill text, and the computed present-day state must match the current snapshot.

This is the central engineering reality of the project. It is harder than "load the dumps," but tractable — and it is exactly what AI-assisted parsing is good at.

---

## 3. Reconstruction Strategy (recommended)

**Amendment-application, validated against the current snapshot.**

1. **Baseline:** earliest reliable chaptered-bill coverage = **1993–94 session**. POC floor = **January 1, 1994**.
2. For every chaptered bill (`BILL_TBL.chapter_num` not null), parse its chaptered XML to find each `(code, section)` it adds / amends / repeals and the new text.
3. Compute the **operative date** of each change (see §4) and order changes within a session by chapter number (Gov. Code §9605 — higher chapter prevails).
4. Emit one version row per `(section_id, operative_range, text, source_chapter, source_url)`.
5. **Validate:** the reconstructed present-day state must equal the current `LAW_SECTION_TBL` snapshot. Discrepancies = parser bugs. This is a free, complete, ground-truth check.

Pre-1993 reconstruction has no machine-readable bill text → **Phase 2 OCR** of the Assembly Chief Clerk's *Statutes and Amendments to the Codes* PDFs (1850–2008) + HathiTrust scans.

---

## 4. Legal-correctness rules the pipeline MUST encode

These confirm the schema decisions already recorded in ARCHITECTURE.md.

- **Operative vs. effective date (Gov. Code §9600).** Regular bills: effective Jan 1 after a 90-day period; **urgency** statutes: effective/operative on the **chaptering date** (any date in-year); local-program bills (§17580): operative July 1. There is **no structured operative-date field** — it must be parsed from bill text (e.g., "This section shall become operative on …"). Point-in-time correctness depends on the **operative** date, not the effective date.
- **Double-jointing / chaptering-out (Gov. Code §9605).** When two bills amend the same section in one session, the higher chapter number wins unless "double-jointing" language conditions each version. ~140–221 bills/session use this. The pipeline must parse the conditions and resolve which version became operative; keep the losing version in an audit table.
- **Section identity.** Do **not** key versions on `(code, section_num)` across time. Sections are repealed, **renumbered**, re-added under old numbers, and mass-**recodified** (e.g., the 2021 Public Records Act move from GOV 6250→7920+). Use a synthetic `section_id` + a `section_number_history(section_id, code, number, start, end)` table. `history` notes ("Formerly § X") flag renumbering vs. re-addition.
- **Provenance.** Every version carries its chaptered bill (`Stats. YYYY, Ch. N`) + source URL so users can verify against the official record.

---

## 5. Remaining unknowns — spike these before/early in Gate D

1. **Chaptered bill XML format & linkage (HIGHEST RISK).** Does `BILL_VERSION_TBL` explicitly link a bill version to the `(code, section)` it amends, or must that be parsed from "Section X of the Y Code is amended to read:" text? Is chaptered text clean "as-enacted" or tracked-changes markup? *Spike: pull 10–20 chaptered bills (incl. one double-jointed, e.g. SB 747 2023–24) and inspect.*
2. **Bill-text coverage/quality 1993–1998** (older XML may be sparse/inconsistent → may raise the practical floor toward ~1999).
3. **Do old archives contain the bill text we need**, or only recent ones? Check whether Wayback has historical archives if not.
4. **Operative-clause parser accuracy** — measure false-negative rate on double-jointed/contingent bills.
5. **Section granularity** — track at full-section level for POC (sub-section is later).
6. **CLRC mass-recodification events** list (1994–present) to model as bulk renames.

Full subagent reports (data inventory + methodology, with all column lists, samples, and citations) are preserved in the cc002 session record. Scratch download retained at `C:\Users\PatrickKolasinski\PatoLex-scratch\gate-b\`.

---

## Revision History

| Date | Change |
|------|--------|
| 2026-05-31 | cc002: Gate B reconnaissance. Confirmed bulk source; found law tables are current-only (no historical snapshots); strategy = amendment-application validated against current snapshot; POC floor Jan 1 1994; legal-correctness rules and remaining unknowns documented. |
