# PatoLex Artifact Registry

**Status:** Extended (cc004, 2026-06-01) — full provenance field set.
**Schema:** `source_document` table — see full field reference below.
**Tool:** `scripts/ingest/register-artifact.ts`

---

## The core principle: content is the authority

Filenames are **convenience labels only**. The registry — specifically the
`source_document` table in the database — is the **authoritative** record of
every artifact's identity and provenance.

**The ingest pipeline reads `edition_year` and all provenance from the registry.
It never reads the year, corpus, or coverage from a filename.**

---

## Full field reference

| Column | Authoritative? | Description |
|--------|---------------|-------------|
| `id` | — | Surrogate PK (bigint identity). |
| `content_sha256` | **AUTHORITATIVE** | SHA-256 hex of the raw file bytes. The content-derived identity. UNIQUE (partial: non-null). Same bytes = same artifact regardless of filename. |
| `edition_year` | **AUTHORITATIVE** | The **VERIFIED** publication/edition year, read from the artifact's own content (title page, colophon, section text, copyright notice). This is what the ingest pipeline uses. |
| `claimed_year` | Audit only | What a filename, catalog entry, or acquisition agent asserted before verification. Kept so mismatches can be flagged and audited. Nullable. |
| `verification_note` | Evidence | How `edition_year` was determined — human-readable evidence trail. E.g. `"title page p.3: 'Sacramento, 1872'"`. |
| `corpus` | **AUTHORITATIVE** | Which body of law the artifact covers. Values: `penal_code` \| `civil_code` \| `code_civil_procedure` \| `political_code` \| `uncodified_statutes` \| `index` \| `other`. Text (not enum) for flexibility. |
| `coverage_start_year` | **AUTHORITATIVE** | First year of the span of law the artifact covers. E.g. a code origin year for a reprint (1872 for an 1880 reprint that incorporates all 1872–1880 amendments). |
| `coverage_end_year` | **AUTHORITATIVE** | Last year of the span of law the artifact covers. E.g. 1880 for an 1880 reprint; same as start for a single-session volume. |
| `source_channel` | Informational | Repository/channel **name**: "Internet Archive" or "CA Assembly Chief Clerk". This is the **name**, not a URL. |
| `source_uri` | Informational | Exact source locator: IA details URL, Chief Clerk direct file URL, etc. Distinct from `source_channel`. |
| `file_name` | **NON-AUTHORITATIVE** | Current filename or relative path on disk (convenience pointer only). Auto-derived from `--file` basename if not supplied. Do NOT derive identity or year from this. |
| `media_format` | Informational | Physical format: `pdf` \| `ocr_text` \| `parsed_json`. Nullable. |
| `section_range` | Informational | Human-readable section number range: e.g. `"1-1685"` or `"Penal 1-1620"`. Nullable. |
| `page_count` | Informational | Total pages in the artifact (PDF page count, etc.). Nullable — set when verifiable from the file. |
| `type` | Classification | Source artifact class: `session_law` \| `bill` \| `annotated_edition` \| `scan` \| `regulatory_action` \| `official_xml`. |
| `trust_level` | Quality | `official_xml` \| `human_verified` \| `derived` \| `ocr_uncertain`. |
| `clean_channel` | Licensing | `true` = source is IA-non-Google or CA-gov (suitable for serving raw text publicly). |
| `scan_quality` | Quality | Qualitative OCR quality indicator (`"good"`, `"poor"`, `"missing"`). Nullable. |
| `ocr_engine` | Quality | OCR engine used (e.g. `"tesseract-5"`). Nullable. |
| `ocr_cer_estimate` | Quality | Estimated character error rate (0–1). Nullable. |
| `citation` | Human-readable | Human-readable citation string. |
| `jurisdiction` | Classification | Jurisdiction code: `"CA"`, `"US"`, etc. |
| `retrieved_at` | Operational | UTC timestamp when the artifact was retrieved/ingested. |

---

## Why this matters: the 1880-masquerading-as-1872 problem

During the cc002 corpus build, two files were acquired with filenames that
implied they were 1872 baseline texts:

- `civil_1872_sections.json` → actually the **1880 Hart/Whitney reprint** of the
  Civil Code (IA `civilcodestatec09hartgoog`), which folds in all 1873–1880
  amendments. Using it as a 1872 baseline would silently double-count eight years
  of legislative changes.
- `ccp_1872_sections.json` → actually the **1880 Newman reprint** of the Code of
  Civil Procedure (IA `codecivilproced03caligoog`).

Both were quarantined and renamed (`*_1880REPRINT_sections_DO_NOT_USE_AS_1872.json`),
and registered in `source_document` with `edition_year=1880`, `claimed_year=1872`.
The registry makes the mismatch permanent and queryable:

```sql
SELECT citation, claimed_year, edition_year, verification_note
FROM source_document
WHERE claimed_year IS NOT NULL AND claimed_year != edition_year;
```

---

## The claimed-vs-verified edition guard

`scripts/ingest/register-artifact.ts` fires a **loud, box-framed WARNING** to
stderr whenever `--claimed-year` is provided and differs from `--edition-year`.
This is intentional and non-optional — it cannot be silenced with a flag.

The warning:
- Is emitted **before** any DB write (visible in dry-run too).
- Identifies the file, the claimed year, the verified year, and the first line
  of the evidence.
- Reminds the operator not to ingest the artifact as the claimed year's baseline.

The artifact is still registered — with the **correct** `edition_year`. The
`claimed_year` is stored for the audit trail.

---

## Filename convention (going forward, non-authoritative)

New artifacts acquired after cc003 should follow this naming pattern:

```
{jurisdiction}-{corpus}-{editionYear}-{sourceId}-{kind}.{ext}
```

Examples:
- `ca-penal-1872-penalcodecalifo00burcgoog-djvu.txt`
- `ca-civil-1880-civilcodestatec09hartgoog-sections.json`
- `ca-statutes-1850-clerk-assembly-session.pdf`

**This convention is a convenience only.** The registry is authoritative. The
pipeline never derives edition year or identity from the filename.

**Do NOT mass-rename existing files** in scratch directories — other agents
may be writing to them. The convention applies to new acquisitions going forward.

---

## Registering an artifact

```sh
npx tsx scripts/ingest/register-artifact.ts \
  --file     <absolute-path>      \   # required
  --type     scan                 \   # required: session_law|bill|annotated_edition|scan|regulatory_action|official_xml
  --jurisdiction CA               \   # required
  --edition-year 1872             \   # required: VERIFIED from content
  --verification-note "..."       \   # required: evidence for edition_year
  --citation "..."                \   # optional
  --source-channel "Internet Archive"  \  # optional: repository NAME
  --source-uri "https://archive.org/details/..." \  # optional: exact URL
  --corpus penal_code             \   # optional: body of law
  --coverage-start 1872           \   # optional: first year of law coverage
  --coverage-end 1872             \   # optional: last year of law coverage
  --section-range "1-1685"        \   # optional: section number range
  --page-count 480                \   # optional: total pages
  --media-format ocr_text         \   # optional: pdf|ocr_text|parsed_json
  --file-name "override-name.txt" \   # optional: override auto-derived basename
  --claimed-year 1872             \   # optional: triggers mismatch check if != edition-year
  --trust-level ocr_uncertain     \   # optional: default ocr_uncertain
  --clean-channel                 \   # optional flag
  --dry-run                           # optional: no DB write
```

The tool is **idempotent on `content_sha256`**: running it twice on the same
file updates the metadata row; it does not create a duplicate.

`file_name` is auto-derived from the `--file` argument's basename if not
supplied explicitly with `--file-name`.

---

## Querying the registry

**Sample audit query — full provenance for all artifacts:**
```sql
SELECT
  corpus,
  edition_year,
  claimed_year,
  coverage_start_year,
  coverage_end_year,
  section_range,
  media_format,
  source_channel,
  file_name,
  source_uri,
  left(content_sha256, 16) || '...' AS sha_prefix,
  CASE WHEN claimed_year IS NOT NULL AND claimed_year != edition_year
    THEN 'MISMATCH' ELSE '' END AS mismatch_flag
FROM source_document
WHERE content_sha256 IS NOT NULL
ORDER BY edition_year, corpus;
```

**All registered artifacts with year mismatch (quarantined):**
```sql
SELECT id, citation, claimed_year, edition_year, verification_note
FROM source_document
WHERE claimed_year IS NOT NULL AND claimed_year != edition_year;
```

**Look up an artifact by SHA-256 (content identity, filename-independent):**
```sql
SELECT * FROM source_document WHERE content_sha256 = '<hex>';
```

**All verified artifacts for a given edition year:**
```sql
SELECT id, corpus, citation, source_channel, source_uri, section_range, content_sha256
FROM source_document
WHERE edition_year = 1872
ORDER BY corpus;
```

**All artifacts covering a given law-year (coverage span):**
```sql
SELECT id, corpus, edition_year, coverage_start_year, coverage_end_year, file_name
FROM source_document
WHERE coverage_start_year <= 1872 AND coverage_end_year >= 1872
ORDER BY corpus;
```

---

## Revision history

| Date | Change |
|------|--------|
| 2026-06-01 | cc003: Initial implementation — schema migration 0001, registry tool, 5 artifacts retrofitted. |
| 2026-06-01 | cc004: Migration 0002 — added file_name, source_uri, corpus, coverage_start_year, coverage_end_year, section_range, page_count, media_format. Updated register-artifact.ts. Re-registered all 5 artifacts with complete provenance records. |
