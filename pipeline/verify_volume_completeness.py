"""
verify_volume_completeness.py
------------------------------
Checks OCR completeness for each production-* volume by:
  1. Parsing "CHAPTER N" headers from consensus_text
  2. Detecting session boundaries (Regular / Extraordinary sessions)
  3. Checking page contiguity (gaps within the OCR key range = possible missing pages)
  4. Checking local chapter density (does chapter density drop to zero in any window,
     suggesting a block of missing pages?)
  5. Comparing found chapter sequence against the folder-encoded expected count
  6. Flagging low-confidence pages as suspect OCR spots
  7. Emitting a per-volume verdict: COMPLETE / LEADING_GAP_ONLY / GAPS_FOUND / SUSPECT / STUB

Usage:
    python verify_volume_completeness.py --label 1953-vol1-52chapters
    python verify_volume_completeness.py --label 1953-vol1-chapters
    python verify_volume_completeness.py --all

For --all, also writes JSON report to:
    docs/80_PROJECT_HISTORY/run-logs/completeness-report.json

Background / design notes:
  - OCR key convention: JSON keys in page_ocr_results.json are 0-based pidx values
    (pidx=0 = physical page 1). page_1indexed = pidx + 1.  Pages before the first
    OCR'd page (pidx < min_key) are intentionally skipped front matter — they are
    NOT content gaps. Most volumes start at pidx=2 (skipping 2 cover/title pages).
    The contiguity check only counts gaps BETWEEN the minimum and maximum present key.
  - Page-gap classification:
      LEADING gap  : missing pidx values only below the first present key (front-matter
                     skips). These do NOT indicate missing statute content.
                     Reported as `leading_missing` and given a LEADING_GAP_ONLY verdict
                     when no mid-volume gaps are found.
      MID-VOLUME gap: missing pidx values between present keys (min_key < missing < max_key).
                     These indicate genuinely absent OCR pages and drive re-OCR.
  - Chapter-number gap analysis is limited for multi-volume sets (e.g. 1953-vol1 +
    vol2 share the same session), because each volume covers a contiguous PAGE range
    not a contiguous CHAPTER range. The script reports chapter gaps but does NOT use
    them as the primary verdict signal for volumes with clearly non-sequential chapter
    distributions. Instead, it uses:
      (a) page contiguity -- gaps within min..max of present keys?
      (b) chapter density -- no window of 75 body pages with zero chapters?
      (c) folder-name expected count vs lowest-session chapter count
  - Chapter numbering restarts within a volume for each extra session.
    The script groups chapters into sessions by detecting session-title pages.
  - The "expected count" is parsed from the folder name suffix
    (e.g. "52chapters" -> 52). This refers to the TOTAL chapters in the volume's
    primary session, NOT necessarily 1..N (it may be a partial vol of a session
    spanning multiple physical volumes).
  - Verdict logic:
      STUB            : < MIN_CHAPTER_THRESHOLD chapters found total (empty/incomplete scan)
      SUSPECT         : high proportion of low-confidence pages (>15%)
      LEADING_GAP_ONLY: only leading (pre-content) keys missing; no mid-volume gaps
      GAPS_FOUND      : mid-volume gaps in OCR keys, OR folder-name expected count not met,
                        OR significant sequential chapter-number gaps for single-session
                        single-volume
      COMPLETE        : passes all checks above
  NOTE: zero-density windows add a note but do NOT by themselves change the verdict
  (a very long single statute can span 100+ pages with no new chapter header).
  - Known limitations:
      * Multi-volume sets: chapter gaps are expected between volumes; the script notes
        the volume is part of a multi-volume set but cannot cross-check completeness
        across volumes.
      * Extra sessions restart numbering; gap analysis is per-session.
      * Front-matter index parsing is best-effort; not all volumes have one.
      * Some chapter numbers appear in statute citations ("Chapter N of the Statutes
        of 19XX") -- the act-evidence filter removes most but not all false positives.
      * For the 1853-era and earlier volumes with very sparse chapters (1-20 per
        volume), the density window check is disabled (not enough chapters to judge).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ── paths ──────────────────────────────────────────────────────────────────────
SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
REPO_ROOT = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex")
REPORT_PATH = REPO_ROOT / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "completeness-report.json"

# ── tunable thresholds ─────────────────────────────────────────────────────────
MIN_CHAPTER_THRESHOLD = 5          # fewer than this = STUB
GAP_RATE_THRESHOLD = 0.15          # >15% gaps in 1..max for single-session single-volume → GAPS_FOUND
LOW_CONF_RATE_THRESHOLD = 0.15     # >15% low-confidence pages → SUSPECT
# Density window: flag if any window of this many BODY pages has zero chapters
# (disabled for volumes with fewer than MIN_CHAPTERS_FOR_DENSITY_CHECK total chapters)
DENSITY_WINDOW_PAGES = 75
MIN_CHAPTERS_FOR_DENSITY_CHECK = 20
# A volume is considered multi-volume if it has a volN label AND there are other
# production dirs for the same year+vol pattern (checked at runtime for --all,
# estimated from folder name for single-volume runs)
SEQUENTIAL_GAP_THRESHOLD = 0.30    # only flag chapter gaps if gap rate > 30% AND single-session single-vol

# ── chapter header regex ───────────────────────────────────────────────────────
# Matches "CHAPTER N" at the start of a line, followed within 4 lines by
# evidence of a statute act:  "An act", "Resolved", "Assembly/Senate ... Resolution",
# "[Approved", or "[Filed".
# Primary pattern: modern format (post ~1915) -- "CHAPTER N" on its own line,
# optionally followed by a period: "CHAPTER N." or "CHAPTER N\n"
CHAPTER_HEADER_PAT = re.compile(
    r"(?i)^CHAPTER\s+(\d+)\s*\.?\s*\n((?:.*\n){0,5})",
    re.MULTILINE,
)
# Secondary pattern: old format (1850-1870s) -- "Chapter N." / "Chap. N." / "Chap N,"
# followed by "AN ACT" on same or next line (early volumes use abbreviated form)
CHAPTER_HEADER_OLD_PAT = re.compile(
    r"(?i)^(?:Chapter|Chap\.?)\s+(\d+)\s*[.\-,]?\s*((?:.*\n){0,3})",
    re.MULTILINE,
)
ACT_EVIDENCE_PAT = re.compile(
    r"(?i)an act|resolved\b|assembly.*resolution|senate.*resolution|\[approved|\[filed",
)
# Old-format act evidence: "AN ACT" or "People of the State"
ACT_EVIDENCE_OLD_PAT = re.compile(
    r"(?i)an act|people of the state|passed\s+\w+\s+\d+",
)

# Session-title patterns
SESSION_TITLE_PAT = re.compile(
    r"(?i)STATUTES\s+OF\s+CALIFORNIA\s*\n"
    r"(?:PASSED\s+AT\s+THE\s+)?"
    r"(\d{4})\s+"
    r"((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)?\s*"
    r"(?:EXTRAORDINARY|EXTRA\s*ORDINARY|REGULAR|SPECIAL)\s+SESSION)",
    re.MULTILINE,
)

# Front-matter index patterns (best-effort)
INDEX_CHAPTER_PAT = re.compile(
    r"(?i)CHAPTER\s+(\d+)[\s\.]+(?P<title>[A-Z][^\n]{5,80}?)[\s\.]{2,}(\d+)\s*$",
    re.MULTILINE,
)

# ── data classes ───────────────────────────────────────────────────────────────
@dataclass
class SessionResult:
    label: str              # e.g. "REGULAR", "EXT_1", "EXT_2"
    chapters_found: list[int] = field(default_factory=list)
    gaps: list[int] = field(default_factory=list)
    max_chapter: int = 0
    min_chapter: int = 0
    gap_rate: float = 0.0

@dataclass
class VolumeResult:
    volume_label: str
    total_pages: int = 0
    body_pages: int = 0
    front_matter_pages: int = 0
    low_conf_pages: list[int] = field(default_factory=list)
    low_conf_rate: float = 0.0
    leading_missing: list[int] = field(default_factory=list)        # pidx values skipped before OCR starts (front matter)
    missing_pages: list[int] = field(default_factory=list)          # mid-volume pidx values absent from OCR JSON
    zero_density_windows: list[tuple[int,int]] = field(default_factory=list)  # (start, end) page ranges with no chapters
    sessions: list[SessionResult] = field(default_factory=list)
    expected_count: Optional[int] = None   # from folder name
    expected_source: str = ""              # "folder_name" / "front_matter" / "none"
    frontmatter_expected: Optional[int] = None
    outlier_chapters: list[int] = field(default_factory=list)
    session_boundaries: list[tuple[int,str]] = field(default_factory=list)  # (page, label)
    verdict: str = "UNKNOWN"
    notes: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0


# ── helpers ────────────────────────────────────────────────────────────────────
def parse_expected_from_label(label: str) -> Optional[int]:
    """Extract chapter count from folder name like '1953-vol1-52chapters'."""
    m = re.search(r"-(\d+)chapters?$", label, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_frontmatter_expected(pages_data: dict) -> Optional[int]:
    """
    Attempt to find a 'Table of Acts' or chapter index in early pages
    and return the highest chapter number listed.
    Returns None if nothing found.
    """
    max_ch: int = 0
    index_trigger = re.compile(
        r"(?i)(TABLE\s+OF\s+(ACTS|CONTENTS|STATUTES)|INDEX\s+TO|ACTS\s+PASSED|CHAPTERED\s+BILLS)",
    )
    # Scan first 30 present keys (sorted) — keys are 0-based pidx, not 1-based
    numeric_keys = sorted([k for k in pages_data.keys() if k.lstrip("-").isdigit()], key=lambda x: int(x))
    first_30 = numeric_keys[:30]
    in_index = False
    for pg_str in first_30:
        text = pages_data.get(pg_str, {}).get("consensus_text", "")
        if not text:
            continue
        if index_trigger.search(text):
            in_index = True
        if in_index:
            for m in INDEX_CHAPTER_PAT.finditer(text):
                ch = int(m.group(1))
                if ch > max_ch:
                    max_ch = ch
    return max_ch if max_ch > 0 else None


def _numeric_keys_sorted(pages_data: dict) -> list[str]:
    """Return pages_data keys that are numeric strings, sorted by integer value."""
    numeric = [k for k in pages_data.keys() if k.lstrip("-").isdigit()]
    return sorted(numeric, key=lambda x: int(x))


def find_chapter_headers(pages_data: dict) -> list[tuple[int, int]]:
    """
    Return list of (pidx, chapter_num) for all real chapter headers,
    in key order.  Tries modern format first, then old format (pre-1875).
    Non-numeric keys are silently skipped.
    """
    results = []
    found_any_modern = False
    for pg_str in _numeric_keys_sorted(pages_data):
        text = pages_data[pg_str].get("consensus_text", "")
        for m in CHAPTER_HEADER_PAT.finditer(text):
            num = int(m.group(1))
            following = m.group(2).lower()
            if ACT_EVIDENCE_PAT.search(following):
                results.append((int(pg_str), num))
                found_any_modern = True

    # If no modern-format chapters found, try old format (1850-1870s)
    if not found_any_modern:
        for pg_str in _numeric_keys_sorted(pages_data):
            text = pages_data[pg_str].get("consensus_text", "")
            for m in CHAPTER_HEADER_OLD_PAT.finditer(text):
                num = int(m.group(1))
                following = m.group(2).lower()
                if ACT_EVIDENCE_OLD_PAT.search(following):
                    results.append((int(pg_str), num))

    return results


def find_session_boundaries(pages_data: dict) -> list[tuple[int, str]]:
    """
    Scan all pages for session-title blocks.
    Return list of (page_1indexed, 'REGULAR' / 'EXT_1' / 'EXT_2' etc.)
    """
    ext_count = 0
    boundaries: list[tuple[int, str]] = []
    ext_ordinal_map = {
        "first": 1, "second": 2, "third": 3,
        "fourth": 4, "fifth": 5, "sixth": 6,
    }
    for pg_str in _numeric_keys_sorted(pages_data):
        text = pages_data[pg_str].get("consensus_text", "")
        for m in SESSION_TITLE_PAT.finditer(text):
            session_desc = m.group(2).strip().lower()
            if "regular" in session_desc:
                label = "REGULAR"
            else:
                # Extract ordinal
                ordinal = None
                for word, n in ext_ordinal_map.items():
                    if word in session_desc:
                        ordinal = n
                        break
                ext_count += 1
                label = f"EXT_{ordinal or ext_count}"
            # Only record the first occurrence of each label
            if not any(b[1] == label for b in boundaries):
                boundaries.append((int(pg_str), label))
    return boundaries


def group_chapters_by_session(
    chapter_sequence: list[tuple[int, int]],
    session_boundaries: list[tuple[int, str]],
) -> list[tuple[str, list[tuple[int, int]]]]:
    """
    Assign each (page, chapter_num) to a session based on which session started
    most recently before that page.
    Returns list of (session_label, [(page, chapter_num), ...]).
    """
    if not session_boundaries:
        return [("UNKNOWN", chapter_sequence)]

    # Sort boundaries by page
    bounds = sorted(session_boundaries, key=lambda x: x[0])

    sessions: dict[str, list[tuple[int, int]]] = {b[1]: [] for b in bounds}
    # Default: first session label
    current_label = bounds[0][1]
    bound_idx = 0

    for pg, ch in sorted(chapter_sequence, key=lambda x: x[0]):
        # Advance session pointer
        while bound_idx + 1 < len(bounds) and pg >= bounds[bound_idx + 1][0]:
            bound_idx += 1
            current_label = bounds[bound_idx][1]
        sessions.setdefault(current_label, []).append((pg, ch))

    return [(label, chapter_sequence) for label, chapter_sequence in sessions.items() if chapter_sequence]


def find_primary_cluster(nums: list[int]) -> tuple[list[int], list[int]]:
    """
    Given an unordered list of chapter numbers, find the primary contiguous
    cluster (the largest run) and return (primary_nums, outlier_nums).

    Strategy:
    1. Sort and find all "runs" — groups where consecutive unique values are
       within a tolerance gap of each other (tolerance = OUTLIER_CLUSTER_GAP).
    2. The largest run by count is the primary cluster.
    3. Anything > PRIMARY_CLUSTER_OUTLIER_RATIO * primary_max is an outlier.
    """
    if not nums:
        return [], []

    sorted_unique = sorted(set(nums))
    if len(sorted_unique) == 1:
        return list(nums), []

    # Find runs: splits when gap between successive values > tolerance
    # We use a generous tolerance (1000) to keep sparse high-chapter volumes together
    TOLERANCE = 1000
    runs: list[list[int]] = []
    current_run = [sorted_unique[0]]
    for v in sorted_unique[1:]:
        if v - current_run[-1] > TOLERANCE:
            runs.append(current_run)
            current_run = [v]
        else:
            current_run.append(v)
    runs.append(current_run)

    # Largest run by count
    primary_run = max(runs, key=len)
    primary_max = max(primary_run)
    primary_min = min(primary_run)

    # Outliers: anything more than PRIMARY_CLUSTER_OUTLIER_RATIO × primary_max
    # above the primary cluster ceiling (handles OCR-garbled extra-digit numbers)
    OUTLIER_RATIO = 2.5
    outliers = [n for n in nums if n > primary_max * OUTLIER_RATIO and n not in set(primary_run)]
    # Also flag isolated low-count runs that are not the primary
    for run in runs:
        if run is not primary_run and max(run) > primary_max * OUTLIER_RATIO:
            outliers.extend(run)
    primary_nums = [n for n in nums if n not in set(outliers)]

    return primary_nums, sorted(set(outliers))


def analyze_session(label: str, seq: list[tuple[int, int]]) -> tuple[SessionResult, list[int]]:
    """
    Compute gaps and stats for one session's chapter sequence.
    Also return outlier chapter numbers (implausible jumps).

    Uses find_primary_cluster to remove obviously out-of-range chapter numbers
    (e.g. OCR-garbled "1735" instead of "735", or real chapters from a different
    session that slipped through boundary detection) before computing gap rate.
    """
    chapter_nums = [ch for _, ch in seq]
    if not chapter_nums:
        return SessionResult(label=label), []

    filtered_nums, outliers = find_primary_cluster(chapter_nums)

    if not filtered_nums:
        return SessionResult(label=label), outliers

    min_ch = min(filtered_nums)
    max_ch = max(filtered_nums)
    found_set = set(filtered_nums)
    expected_set = set(range(min_ch, max_ch + 1))
    gaps = sorted(expected_set - found_set)
    gap_rate = len(gaps) / max(1, max_ch - min_ch + 1)

    sr = SessionResult(
        label=label,
        chapters_found=sorted(found_set),
        gaps=gaps,
        max_chapter=max_ch,
        min_chapter=min_ch,
        gap_rate=gap_rate,
    )
    return sr, outliers


def check_page_contiguity(pages_data: dict) -> tuple[list[int], list[int]]:
    """
    Check OCR key contiguity.

    OCR JSON keys are 0-based pidx values (pidx=0 = physical page 1).
    Pages before the first present key are intentionally skipped front matter
    (cover/title pages) and do NOT indicate content gaps.

    Returns:
        (leading_missing, mid_volume_missing)
        leading_missing  : pidx values in 0..(min_key-1) — front-matter skips, not content gaps
        mid_volume_missing: pidx values in (min_key+1)..(max_key-1) that are absent — real gaps
    """
    if not pages_data:
        return [], []
    numeric_keys = [k for k in pages_data.keys() if k.lstrip("-").isdigit()]
    if not numeric_keys:
        return [], []
    page_nums = {int(k) for k in numeric_keys}
    min_pg = min(page_nums)
    max_pg = max(page_nums)
    # Leading: anything before the first present key (front matter intentionally skipped)
    leading_missing = list(range(0, min_pg)) if min_pg > 0 else []
    # Mid-volume: gaps strictly between min and max present keys
    mid_missing = sorted(set(range(min_pg + 1, max_pg)) - page_nums)
    return leading_missing, mid_missing


def check_chapter_density(
    chapter_sequence: list[tuple[int, int]],
    pages_data: dict,
    total_pages: int,
    window: int = DENSITY_WINDOW_PAGES,
) -> list[tuple[int, int]]:
    """
    Slide a window over body pages and flag any window with zero chapter headers
    AND where the pages do NOT appear to be body text of a single long act.

    A window is suspicious (possible missing pages) if:
      - Zero chapter headers in the window, AND
      - The pages have content (not blank), AND
      - The pages do NOT contain "People of the State" / "do enact as follows"
        (which would indicate they are part of a single long statute).

    Returns list of (window_start_page, window_end_page) for suspicious zero-density windows.
    Only meaningful if there are enough total chapters.
    """
    if total_pages < window * 2:
        return []

    # Text that indicates we're inside a legitimate long statute body (not a gap)
    long_act_pat = re.compile(
        r"(?i)(people of the state of california do enact|"
        r"section \d+\.|"
        r"this act shall|"
        r"declared to be an urgency)",
        re.MULTILINE,
    )

    chapter_pages = {pg for pg, _ in chapter_sequence}
    zero_windows = []
    for start in range(1, total_pages - window + 1, window // 2):
        end = start + window - 1
        window_pages = set(range(start, end + 1))
        if chapter_pages.intersection(window_pages):
            continue  # has chapters, skip

        # Check if these pages look like a long statute body
        sample_pages = sorted(window_pages)[::10]  # sample every 10th page
        in_long_act = 0
        for pg in sample_pages:
            text = pages_data.get(str(pg), {}).get("consensus_text", "")
            if long_act_pat.search(text):
                in_long_act += 1
        # If most sampled pages look like statute body text, it's not a gap
        if in_long_act > len(sample_pages) * 0.4:
            continue  # likely a long single act, not missing pages

        zero_windows.append((start, end))

    # Merge overlapping windows
    merged: list[list[int]] = []
    for w in zero_windows:
        if merged and w[0] <= merged[-1][1] + 1:
            merged[-1] = [merged[-1][0], max(merged[-1][1], w[1])]
        else:
            merged.append(list(w))
    return [(w[0], w[1]) for w in merged]


def compute_verdict(result: VolumeResult) -> str:
    # Select primary session: prefer REGULAR, then UNKNOWN, then first found.
    # Iterate ALL sessions rather than breaking early on the first entry.
    primary_session: Optional[SessionResult] = None
    for s in result.sessions:
        if s.label == "REGULAR":
            primary_session = s
            break
        if s.label == "UNKNOWN" and primary_session is None:
            primary_session = s
        elif primary_session is None:
            primary_session = s

    total_chapters = sum(len(s.chapters_found) for s in result.sessions)

    if total_chapters < MIN_CHAPTER_THRESHOLD:
        return "STUB"

    # Mid-volume page contiguity failure = definite content gap problem
    if result.missing_pages:
        result.notes.append(
            f"Mid-volume missing pidx keys in OCR output (re-OCR candidates): {result.missing_pages[:20]}"
            + (f" (+{len(result.missing_pages)-20} more)" if len(result.missing_pages) > 20 else "")
        )
        return "GAPS_FOUND"

    # Leading gap only: front-matter pages before OCR start — not a content gap
    if result.leading_missing:
        result.notes.append(
            f"Leading pidx values not OCR'd (front-matter skip, {len(result.leading_missing)} pages before "
            f"pidx={result.leading_missing[-1]+1}): expected, not a content gap"
        )

    # Zero-density windows = possibly missing pages (informational; not always a GAPS_FOUND
    # because a very long single statute can span 100+ pages with no new chapter header)
    if result.zero_density_windows:
        result.notes.append(
            f"Suspicious page windows with no chapter headers (review manually): "
            + ", ".join(f"{s}-{e}" for s, e in result.zero_density_windows[:5])
        )

    if result.low_conf_rate > LOW_CONF_RATE_THRESHOLD:
        return "SUSPECT"

    if result.outlier_chapters:
        result.notes.append(
            f"Outlier chapter numbers (possible false positives, reported only): {result.outlier_chapters[:10]}"
        )

    if primary_session is None:
        return "SUSPECT"

    # For single-session volumes, check sequential chapter gaps in the primary cluster
    is_single_session = len(result.sessions) == 1
    if is_single_session and primary_session.gap_rate >= SEQUENTIAL_GAP_THRESHOLD:
        # But skip this check if the volume is clearly part of a multi-vol set
        # (folder name has "vol1" and there's no explicit chapter count)
        label = result.volume_label
        is_multi_vol_candidate = bool(re.search(r"-vol\d+", label, re.IGNORECASE))
        if not is_multi_vol_candidate:
            result.notes.append(
                f"High chapter gap rate ({primary_session.gap_rate*100:.0f}%) "
                f"for single-session single-volume — may indicate missing pages."
            )
            return "GAPS_FOUND"
        else:
            result.notes.append(
                f"Chapter gap rate {primary_session.gap_rate*100:.0f}% — likely multi-vol set; "
                f"gaps expected between volumes."
            )

    # Check against expected count from folder name
    if result.expected_count is not None:
        # For each session, the chapter count found should be at least expected_count * 0.9
        # But for multi-vol sets, expected_count may refer to the entire session
        # so we check primary session's MAX chapter vs expected_count
        actual_max = primary_session.max_chapter if primary_session else 0
        # Allow slack for OCR misses
        slack = max(5, int(result.expected_count * 0.08))
        if actual_max < result.expected_count - slack:
            result.notes.append(
                f"Folder-name expected {result.expected_count} chapters "
                f"but primary session max found = {actual_max} — possible truncation."
            )
            return "GAPS_FOUND"

    # No mid-volume gaps, no other failures. If only leading gaps (front-matter skip), say so.
    if result.leading_missing and not result.missing_pages:
        return "LEADING_GAP_ONLY"

    return "COMPLETE"


def load_volume(scratch_dir: Path) -> Optional[VolumeResult]:
    """
    Load and analyze a single production volume directory.
    Returns None if no OCR data found.
    Returns a VolumeResult with verdict=ERROR if processing fails unexpectedly.
    """
    label = scratch_dir.name.removeprefix("production-")
    ocr_path = scratch_dir / "ocr_consensus" / "page_ocr_results.json"
    cls_path = scratch_dir / "page_classification.json"

    if not ocr_path.exists():
        return None

    try:
        with open(ocr_path, encoding="utf-8") as f:
            pages_data: dict = json.load(f)

        result = VolumeResult(volume_label=label, total_pages=len(pages_data))

        # Page classification
        if cls_path.exists():
            with open(cls_path, encoding="utf-8") as f:
                cls_data = json.load(f)
            result.body_pages = len(cls_data.get("body", []))
            result.front_matter_pages = len(cls_data.get("front_matter", []))
        else:
            result.body_pages = result.total_pages
            result.front_matter_pages = 0

        # Low-confidence pages — skip non-numeric keys gracefully
        low_conf = []
        for pg_str, entry in pages_data.items():
            if not pg_str.lstrip("-").isdigit():
                continue
            agr = entry.get("agreement_ratio", 1.0)
            hc = entry.get("high_confidence", True)
            if not hc or agr < 0.75:
                low_conf.append(int(pg_str))
        result.low_conf_pages = sorted(low_conf)
        result.low_conf_rate = len(low_conf) / max(1, result.total_pages)

        # Expected count from folder name
        result.expected_count = parse_expected_from_label(label)
        result.expected_source = "folder_name" if result.expected_count else "none"

        # Front-matter index (best-effort)
        result.frontmatter_expected = parse_frontmatter_expected(pages_data)
        if result.frontmatter_expected and not result.expected_count:
            result.expected_count = result.frontmatter_expected
            result.expected_source = "front_matter"

        # Page contiguity check — returns (leading_missing, mid_volume_missing)
        result.leading_missing, result.missing_pages = check_page_contiguity(pages_data)

        # Session boundaries
        result.session_boundaries = find_session_boundaries(pages_data)

        # Chapter headers
        chapter_sequence = find_chapter_headers(pages_data)

        # Chapter density check (only if enough chapters)
        total_ch_prelim = len(chapter_sequence)
        if total_ch_prelim >= MIN_CHAPTERS_FOR_DENSITY_CHECK:
            result.zero_density_windows = check_chapter_density(
                chapter_sequence, pages_data, result.total_pages
            )
        else:
            result.zero_density_windows = []

        # Group by session
        session_groups = group_chapters_by_session(chapter_sequence, result.session_boundaries)

        all_outliers: list[int] = []
        for sess_label, seq in session_groups:
            sr, outliers = analyze_session(sess_label, seq)
            result.sessions.append(sr)
            all_outliers.extend(outliers)

        result.outlier_chapters = sorted(set(all_outliers))

        # Verdict — called exactly once here
        result.verdict = compute_verdict(result)

        return result

    except Exception as exc:  # noqa: BLE001
        err_result = VolumeResult(volume_label=label)
        err_result.verdict = "ERROR"
        err_result.notes.append(f"Processing exception: {exc}")
        return err_result


def format_result(r: VolumeResult) -> str:
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"Volume : {r.volume_label}")
    lines.append(f"Verdict: {r.verdict}")
    lines.append(f"Pages  : total={r.total_pages}  body={r.body_pages}  front_matter={r.front_matter_pages}")
    if r.leading_missing:
        lines.append(
            f"Leading (front-matter skipped): {len(r.leading_missing)} pidx values "
            f"(pidx 0..{r.leading_missing[-1]}) — expected, not a content gap"
        )
    if r.missing_pages:
        lines.append(
            f"MID-VOLUME MISSING pidx keys in OCR JSON (re-OCR candidates): {r.missing_pages[:20]}"
            + (f" (+{len(r.missing_pages)-20} more)" if len(r.missing_pages) > 20 else "")
        )
    else:
        lines.append(f"Mid-volume contiguity: OK (no gaps within OCR key range)")
    lines.append(
        f"Low-conf pages: {len(r.low_conf_pages)} ({r.low_conf_rate*100:.1f}%)"
        + (f"  — first few: {r.low_conf_pages[:10]}" if r.low_conf_pages else "")
    )
    if r.zero_density_windows:
        lines.append(f"Zero-density windows (no chapter headers; may be long single acts):")
        for s, e in r.zero_density_windows[:10]:
            lines.append(f"  pidx {s}-{e} (review manually)")
    if r.expected_count:
        lines.append(f"Expected count: {r.expected_count} (source: {r.expected_source})")
    if r.session_boundaries:
        lines.append(f"Session boundaries detected:")
        for pg, lbl in r.session_boundaries:
            lines.append(f"  pidx {pg}: {lbl}")
    for s in r.sessions:
        if not s.chapters_found:
            continue
        lines.append(f"Session [{s.label}]:")
        lines.append(f"  chapters found: {len(s.chapters_found)}  min={s.min_chapter}  max={s.max_chapter}")
        lines.append(f"  gap rate (1..max): {s.gap_rate*100:.1f}%  ({len(s.gaps)} gaps in {s.min_chapter}..{s.max_chapter})")
        if s.gaps:
            shown = s.gaps[:30]
            more = len(s.gaps) - len(shown)
            suffix = f"  ...+{more} more" if more > 0 else ""
            lines.append(f"  gaps: {shown}{suffix}")
    if r.outlier_chapters:
        lines.append(f"Outlier/false-positive chapter nums (informational): {r.outlier_chapters[:20]}")
    for note in r.notes:
        lines.append(f"NOTE: {note}")
    lines.append(f"Elapsed: {r.elapsed_sec:.1f}s")
    return "\n".join(lines)


def result_to_dict(r: VolumeResult) -> dict:
    """Convert to a JSON-serializable dict."""
    return {
        "volume_label": r.volume_label,
        "verdict": r.verdict,
        "total_pages": r.total_pages,
        "body_pages": r.body_pages,
        "front_matter_pages": r.front_matter_pages,
        "leading_missing_count": len(r.leading_missing),  # front-matter skips (not content gaps)
        "mid_volume_missing_count": len(r.missing_pages),  # real content gaps
        "missing_pages": r.missing_pages[:50],             # mid-volume missing pidx values
        "low_conf_page_count": len(r.low_conf_pages),
        "low_conf_rate": round(r.low_conf_rate, 4),
        "zero_density_windows": [{"start": s, "end": e} for s, e in r.zero_density_windows],
        "expected_count": r.expected_count,
        "expected_source": r.expected_source,
        "frontmatter_expected": r.frontmatter_expected,
        "session_count": len(r.session_boundaries),
        "session_boundaries": [{"pidx": pg, "label": lbl} for pg, lbl in r.session_boundaries],
        "sessions": [
            {
                "label": s.label,
                "chapters_found_count": len(s.chapters_found),
                "min_chapter": s.min_chapter,
                "max_chapter": s.max_chapter,
                "gap_count": len(s.gaps),
                "gap_rate": round(s.gap_rate, 4),
                "gaps": s.gaps[:200],  # cap at 200 for readability
            }
            for s in r.sessions
        ],
        "outlier_chapters": r.outlier_chapters[:50],
        "notes": r.notes,
        "elapsed_sec": round(r.elapsed_sec, 2),
    }


# ── main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Verify OCR completeness for PatoLex production volumes.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--label", help="Volume label (e.g. 1953-vol1-52chapters)")
    group.add_argument("--all", action="store_true", help="Sweep all production-* directories")
    parser.add_argument(
        "--scratch",
        default=str(SCRATCH_ROOT),
        help=f"Root directory containing production-* folders (default: {SCRATCH_ROOT})",
    )
    args = parser.parse_args()

    scratch = Path(args.scratch)

    if args.all:
        dirs = sorted(d for d in scratch.iterdir() if d.is_dir() and d.name.startswith("production-"))
        print(f"Found {len(dirs)} production directories.")
        all_results = []
        # Write report incrementally so partial results survive if the sweep is interrupted.
        # We accumulate results and write after each volume.
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        for d in dirs:
            label = d.name.removeprefix("production-")
            print(f"  Analyzing {label}...", end="", flush=True)
            t0 = time.time()
            r = load_volume(d)   # verdict computed inside; per-volume exceptions produce ERROR result
            if r is None:
                print(" (no OCR data, skipped)")
                continue
            r.elapsed_sec = time.time() - t0
            # DO NOT call compute_verdict again here — it was already called inside load_volume
            # and would duplicate note strings via side-effects.
            print(f" {r.verdict} ({r.elapsed_sec:.1f}s)")
            all_results.append(r)
            # Incremental write: overwrite report after each volume so progress survives crashes
            try:
                with open(REPORT_PATH, "w", encoding="utf-8") as f:
                    json.dump([result_to_dict(x) for x in all_results], f, indent=2)
            except Exception:
                pass  # Don't let a write failure abort the sweep

        # Print summary table
        print()
        print(f"{'VOLUME':<40} {'VERDICT':<18} {'PAGES':>6} {'SESSIONS':>8} {'TOTAL_CH':>9} {'MID_GAPS':>9} {'LOWCONF%':>9}")
        print("-" * 110)
        for r in all_results:
            total_ch = sum(len(s.chapters_found) for s in r.sessions)
            total_gaps = sum(len(s.gaps) for s in r.sessions)
            print(
                f"{r.volume_label:<40} {r.verdict:<18} {r.total_pages:>6} "
                f"{len(r.sessions):>8} {total_ch:>9} {len(r.missing_pages):>9} "
                f"{r.low_conf_rate*100:>8.1f}%"
            )

        # Print verdict counts
        print()
        from collections import Counter
        counts = Counter(r.verdict for r in all_results)
        print("Verdict summary:")
        for v in ("COMPLETE", "LEADING_GAP_ONLY", "GAPS_FOUND", "SUSPECT", "STUB", "ERROR"):
            print(f"  {v:<20} {counts.get(v, 0)}")

        # Final report write
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump([result_to_dict(r) for r in all_results], f, indent=2)
        print(f"\nReport written to: {REPORT_PATH}")

    else:
        label = args.label
        vol_dir = scratch / f"production-{label}"
        if not vol_dir.exists():
            print(f"ERROR: Directory not found: {vol_dir}", file=sys.stderr)
            sys.exit(1)
        t0 = time.time()
        r = load_volume(vol_dir)
        if r is None:
            print(f"ERROR: No OCR data found in {vol_dir}", file=sys.stderr)
            sys.exit(1)
        r.elapsed_sec = time.time() - t0
        print(format_result(r))


if __name__ == "__main__":
    main()
