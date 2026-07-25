# Verify Report: phase - 2026-07-25

Scope: phase (adversarial audit, Hans persona, Opus)
Context: cc019 commits 44d6a16 and 690c0d2, baseline f152284
Verdict: FAIL

## Findings

### 1. FAIL (severe) -- Lapse-date regexes reproduce cross-act date poisoning on REAL corpus text

pipeline/ingest/ingest_from_ocr.py (LAPSE_SPELLED_RE, LAPSE_NUMERIC_RE) use [^.]{0,120}? as a free-text qualifier between the "became law" core and the date. Running both regexes against the real consensus OCR text of every production-* volume on the 5090, production-1865-66 page 24 (a printed CONTENTS page) produced this match:

"became a law by operation of the Constitution, 380 | An Act to transfer certain fands-approved March 30, 1866"

The real printed page 24 text reads:

379 | Au Act for relief of Pliny M. Whitney, late Collector of Fishing
      Licenses-became a law by operation of the Constitution,
380 | An Act to transfer certain fands-approved March 30, 1866...... | S.B. 812 .....008 AB5

Chapter 379's own date is missing or wrapped away in the OCR, and the qualifier span crossed the "380 |" page-index token and captured chapter 380's APPROVED date as if it were chapter 379's lapse date. Chapter 380 is a separately signed act. This is the "Cluster-B" cross-entry date poisoning the file's own parse_act_date docstring documents as a known bug class, and the plus-or-minus-3-year clamp does not catch it, because the poisoned date is the same year and within weeks of the correct one.

Whether this specific occurrence reaches a committed DB row depends on header_starts_act (gated on AN_ACT_RE -- a bare "379 |" numeral doesn't match HEADER_RE's glyph requirement, so a buffer likely wouldn't open here specifically). But the regex itself, not the surrounding harness, is unsafe, and this is now permanent, general-purpose code that will run unattended across the entire un-reviewed 1877-1994 forward campaign, not just the 71 hand-verified chapters. The commit message says the 71 recovered values were read visually off the printed page -- that protects the 71 already-classified rows, but does nothing for future automatic runs of this same regex against the rest of the corpus, where this exact contents-page shape recurs constantly.

Fix required: tighten the qualifier span so it cannot cross a digit-pipe page-index token or an intervening act title. Add a same-row/same-title boundary check before trusting a lapse-date match, and re-run a full-corpus scan (method used in this audit) as a regression gate before this ships to the forward campaign.

### 2. FAIL (moderate) -- The commit's "0 false positives against body text" claim for the widened separator is empirically false

The new _HDR_SEP separator widens the gap between the CHAP glyph and the numeral to allow commas and repeated dash/period/space runs, where the old separator allowed only one optional dot then whitespace. Diffing OLD vs NEW regex line-by-line across every page_ocr_results.json in C:\PatoLex-scratch (15,727,023 non-empty lines): 768 lines match only under the new regex. The majority are genuine recovered chapter headers (OCR comma-for-period garble). But filtering to lines with no act-related keyword nearby still surfaces 55 clear false positives, concentrated in index pages of modern volumes, for example:

production-1969-vol2-chapters page 2261: "crabs, 47"
production-1993-vol5 page 681: "charges, 1192"
production-1994-vol5 page 1215: "change, 131"
production-1997-vol6 page 606: "copies, 395"
production-1998-vol6 page 768: "card, 828"
production-1999-vol5 page 1429: "covers, 787"

Every one of these is a standard back-of-book subject-index entry. Also found a genuine body-text false positive: production-1873-74-code page 387, "cease. - i", matches fully as a header (numeral "i").

The commit message claims: "MEASURED: canonical regex 5/9 -> 9/9 on real printed forms, with 0 false positives against body text, running heads, enacting clauses and [Approved] lines." That measurement was against a curated 9-sample set, not the corpus. As stated, the claim is false.

Practical mitigation (verified, reduces severity from severe to moderate): the only production consumer that opens an act buffer from a HEADER_RE match is header_starts_act(), which additionally requires AN_ACT_RE to match within the next 4 non-empty lines. Index entries like "crabs, 47" are not followed by "An Act" text, so they will not open a spurious buffer under the current harness. The same guard exists in chapter_reconstruct.py via ENACT_MARKER_RE. The commit's stated test claim is still wrong, and any future caller of HEADER_RE that doesn't carry that guard will inherit this false-positive surface silently.

Fix required: correct the commit message and lesson file's "0 false positives" claim. Consider excluding the comma from _HDR_SEP (keep it in the existing trailing dash-tail class only) since every genuine recovery inspected already had a dash present and did not need a comma in the pre-numeral position. This narrower fix was not verified against the corpus in this audit.

### 3. FAIL (moderate) -- Undisclosed third live copy of HEADER_RE (pipeline/5080/reparse.py) was NOT updated, conflicts with the repo's own canonical-parser labeling

The commit's own in-code comment claims (restated in the commit message): "pipeline/ingest/ingest_from_ocr.py:393 (CANONICAL parser)." But pipeline/README.md (untouched by this change) documents a different split: pipeline/ingest_clean.py is labeled "CANONICAL. This is the system of record," while pipeline/5080/ingest_from_ocr.py is labeled "SUPERSEDED / LOSSY. Do NOT treat its DB output as final."

pipeline/5080/ingest_from_ocr.py no longer exists (moved to pipeline/ingest/ingest_from_ocr.py, confirmed via git log and this commit's own message, which notes the same path move broke test_date_parser_fix.py's import). So the README's SUPERSEDED label is stale-by-path, but nobody updated it, and the new commit's comment asserts the opposite designation without reconciling the README. The file now writes parsed_acts_fixed.json directly and has a __main__ guard, both of which contradict what the README says about the file it describes.

Separately and more concretely: pipeline/5080/reparse.py contains its own, un-synced copy of HEADER_RE (last touched 2026-06-12, over a month before this fix), still using the OLD separator -- it is blind to every em-dash-era header this commit fixed. re_ingest_fixed.py still references it directly ("parsed_acts_fixed.json not found -- run reparse.py first"), and pipeline/README.md still lists reparse.py as a live parse/build script. Whether or not reparse.py is actually exercised in the current forward campaign, it was not deleted, deprecated, or brought in sync -- if it is ever run, it will silently regenerate a parsed_acts_fixed.json missing every em-dash-era chapter this commit says was fixed, and per the README, that file is what the actual canonical ingest_clean.py commits to the DB.

Fix required: resolve the canonical-parser ambiguity in pipeline/README.md, and either delete/archive pipeline/5080/reparse.py (per the project's archive-don't-delete convention) and scrub its references, or port the identical separator fix into it so it cannot silently diverge a fourth time.

### 4. WARN (minor, self-disclosed) -- spelled_ordinal_to_int guard admits calendar-impossible days (32-39) despite its own comment saying it shouldn't

The guard "if 21 <= v <= 39: return v" is documented as intending "only 21-29 and 31," but the range check admits 30-39 broadly. spelled_ordinal_to_int("thirty-second") returns 32, not a valid day-of-month, confirmed by direct execution. Low real-world risk since no printed date reads "the thirty-second day of," but it is a latent defect in a date parser whose whole job is not admitting a wrong-but-plausible value silently. Tighten the guard to 21 <= v <= 29 or v == 31.

### 5. WARN (minor) -- ENACT_MARKER_RE is unanchored and matches ordinary prose, not just the formal enacting clause

ENACT_MARKER_RE matches the bare phrase "people of the State of California" anywhere in the text, not the formal constitutional enacting formula. Confirmed on the real corpus (production-1889, page 786): a Senate Concurrent Resolution, printed under its own "CHAPTER XXII." heading, matches ENACT_MARKER_RE purely because its preamble text reads "...of great commercial importance to the people of the State of California..." -- incidental, non-operative usage. is_confident_act's docstring frames this marker as "the legally operative signal," which overstates what the regex actually detects.

Verified mitigation: header_starts_act (unchanged by this commit) still gates buffer-opening on AN_ACT_RE only, not ENACT_MARKER_RE, and this resolution's visible text has no "An Act" wording nearby, so it would not open a buffer under the current harness. A corpus scan for pages mentioning Joint/Concurrent Resolution AND matching ENACT_MARKER_RE without "An Act" text found 457 hits -- not exhaustively confirmed that none of those ever falls inside an opened buffer, so an occasional resolution slipping through cannot be ruled out.

Fix required: tighten ENACT_MARKER_RE to the actual enacting formula, and soften the docstring's "legally operative signal" claim.

### 6. PASS -- parse_act_date branch ordering and year clamp

Verified directly: APPROVED_MODERN_RE is tried first, APPROVED_RE second, and the new lapse branch (parse_lapse_date) is tried strictly last, only reached when the first two produce no match, exactly as the commit claims. The year-clamp check is applied to the lapse branch's result identically to the two approval branches, including recording the rejection for out-of-window lapse dates. No ordering defect found. As documented under Finding 1, the clamp does not help when the poisoned date is in-window, which is the actual failure mode reproduced above.

### 7. PASS (with caveat) -- _residual_manifest.py bracket_for / _run_lengths

Traced the bisect logic: bisect_left(have, c) on a c known not to be in have correctly yields lo = nearest present chapter below, hi = nearest above. Start-of-volume and end-of-volume cases are both handled with directionally-correct one-sided ranges. The source_page-of-zero truthiness bug is genuinely fixed. The span_implausible heuristic only catches "span too narrow for the run," and, as the docstring itself discloses, does not catch the actually-documented 1872 failure mode (a neighbour's own recorded page being wrong). This is honestly scoped as a partial fix in both the code comment and the commit message, so it is not flagged as a doc-honesty violation.

### 8. PASS (with a documentation nuance) -- RESIDUAL_71_CONTENTS_RECOVERY doc "71 of 71 recovered" claim

The doc's headline could mislead a skim-reader into thinking statutory body text was recovered for all 71. It was not: 5 of the 71 are Amendments-volume redirects with explicitly no title, no page, no text. The doc itself states this plainly a few lines below the headline and again in the Key Implications section. Because the caveat is present, explicit, and not buried, this is treated as sound-but-imprecise headline wording rather than a FAIL-worthy overclaim. Recommend tightening the headline to distinguish text-recovered vs. classified-only chapters.

## What could not be verified

- Full exhaustive proof that no resolution/junk buffer is ever committed via the is_confident_act relaxation across the entire 1850-1994 corpus. parse_volume/flush_act was not run end-to-end (avoided as this is a read-only audit).
- Whether pipeline/5080/reparse.py is still exercised in the live scheduled-task pipeline today, or is genuinely dead code. No scheduled-task or supervisor script was found in the repo that invokes it directly.
- Catastrophic-backtracking risk on the lapse regexes under pathological adversarial input. Both ran across the entire real corpus without a hang, which is reasonable but not a formal ReDoS proof.
- test_enactment_paths.py and test_residual_bracket.py -- logic was read directly rather than re-running the test files. pytest was not executed in this session.

## Required Fixes (ranked)

1. Fix the lapse-date regex qualifier so it cannot cross a page-index token or a second act's title. Re-run a full-corpus regex sweep as a regression gate before this ships to the forward campaign.
2. Correct the "0 false positives against body text" claim in the commit message and lesson file. Document the header_starts_act guard as the actual mitigation. Consider narrowing _HDR_SEP to drop comma (verify before applying).
3. Resolve the reparse.py divergence: delete/archive it and scrub references, or port the separator fix into it. Resolve the README vs. commit-comment conflict over which parser is canonical.
4. Tighten spelled_ordinal_to_int's range guard to match its documented invariant.
5. Anchor ENACT_MARKER_RE to the actual enacting formula and soften the is_confident_act docstring claim.
6. Rephrase the RESIDUAL_71 doc headline to distinguish text-recovered vs. classified-only chapters.
