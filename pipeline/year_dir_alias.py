r"""year_dir_alias.py -- the SINGLE source of truth for the production-dir <-> oracle-session-year
alias used by the OCR-era recall scoreboard AND the best-of merge.

WHY THIS MODULE EXISTS
----------------------
Most production dirs are named `production-<year>*` where the LEADING 4-digit year IS the oracle
regular-session year, so a naive regex (`production-(\d{4})`) resolves them correctly. Two
structural cases break that naive rule, and BOTH `_recall_allyears.py` (scoreboard) and
`merge_passes.py` (merge) must agree on the remap or they silently disagree:

  (1) 19th-c BIENNIAL sessions -- the Legislature met every 2 years and the oracle records the
      biennium ONCE under the EVEN year (e.g. "1865-66 Regular Session" -> session_year 1866),
      but the data dir is named for the biennium SPAN (production-1865-66, leading year 1865).
      The naive regex grabs 1865 (no/ tiny oracle row) instead of 1866 (N=650).
      The "-code" sibling dirs are the same session's code-amendment volume (same chapter
      numbering -> set-unioned by the scoreboard, never summed).

  (2) TRANSITION biennium-named regular sessions 1901/1909/1911 live under production-1900-01 /
      -1907-09 / -1910-11 (odd-year regular session bound with the even-year extra session), and
      1907 lives under production-1906-07. The naive regex grabs the EVEN leading year, whose
      oracle row is a tiny extra session (1900=15, 1906=64, 1910=1, 1907-extra=...) -> the merge
      caps N FAR too low, clipping the real regular-session chapters. This is the exact
      `n_for()` mis-cap bug that corrupted 1901/1909/1911/1907 (see
      docs/80_PROJECT_HISTORY/lessons/LESSON_2026-06-22_biennial_volume_offset_merge_cap.md).

  (3) MID-CENTURY budget sessions (tiny "Regular (Budget) Session", oracle N=1..14): the even-year
      budget chapters were bound into the FOLLOWING odd-year statute volume as a "-NNchapters"
      sub-volume where NN = the budget calendar year's last two digits (1953_Vol1_52Chapters.pdf =
      the 1952 chapters). Mapped to that sub-volume dir, capped at the budget year's REGULAR N.

The merge MUST cap at the REGULAR session's N (not the max across session types): the 1952 budget
year, for instance, has regular N=14 but extra sessions N=33/34 -- capping at 34 would over-admit.
So this module resolves dir -> REGULAR-session N straight from the oracle TSV (the same regular-only
rule _recall_allyears.py uses), independent of how any caller builds its own oracle dict.

INTERFACE (do not break either consumer):
  YEAR_DIR_ALIAS    : dict[int, list[str]]  -- oracle session-year -> production-dir basenames.
                      Re-exported VERBATIM for _recall_allyears.py (it consults this when its
                      `production-<year>*` glob finds nothing).
  BUDGET_OWNED_DIRS : set[str]              -- basenames the greedy odd-year glob must EXCLUDE so
                      they are handed solely to their alias (prevents double-count).
  DIR_TO_YEAR       : dict[str, int]        -- INVERSE of YEAR_DIR_ALIAS (basename -> oracle year),
                      asserted 1:1 at import. This is what merge_passes.n_for() consults.
  regular_oracle()  : dict[int, int]        -- session_year -> total_chapters for REGULAR rows only,
                      read once from the oracle TSV.
  n_for_dir(name)   : (N, year|None)        -- resolve a basename to (regular-N, resolved-year) via
                      the alias; returns (None, None) if the basename is not an aliased dir (caller
                      falls back to its leading-year regex for normal production-<year>* dirs).

This module imports NOTHING from ingest/ or analysis/ -> no import cycle is possible.
"""
import csv
import os

# Oracle TSV -- same file both consumers already read (absolute; this module is standalone).
ORACLE_TSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "docs", "30_SYSTEM_DESIGN", "sources", "ca_chapter_counts.tsv",
)

# --- Explicit oracle-year -> dir-basename alias (mirrors _recall_allyears.py VERBATIM) -----------
# CRITICAL invariants (asserted below at import time):
#   * every basename is unique across the dict (no dir aliased to two oracle years), and
#   * each budget/transition basename that the greedy glob could also sweep is in BUDGET_OWNED_DIRS.
BUDGET_OWNED_DIRS = {
    "production-1953-vol1-52chapters", "production-1955-vol1-54chapters",
    "production-1957-vol1-56chapters", "production-1959-vol1-58chapters",
    "production-1961-vol1-60chapters", "production-1963-vol1-62chapters",
    "production-1965-vol1-64chapters",
    # TRANSITION collision: production-1907-09 holds the 1909 REGULAR session (N=729); the greedy
    # `production-1907*` glob for oracle 1907 would also sweep it (the historic bug). Excluded here
    # and handed solely to 1909's alias. Oracle 1907 (N=539) is served by production-1906-07.
    "production-1907-09",
}
YEAR_DIR_ALIAS = {
    # biennial (even-year oracle row -> biennium-span dir [+ code-volume sibling])
    1866: ["production-1865-66"],
    1868: ["production-1867-68"],
    1870: ["production-1869-70"],
    1872: ["production-1871-72"],
    1874: ["production-1873-74", "production-1873-74-code"],
    1876: ["production-1875-76", "production-1875-76-code"],
    1878: ["production-1877-78", "production-1877-78-code"],
    # transition (odd-year regular session bound in the biennium volume)
    1901: ["production-1900-01"],
    1911: ["production-1910-11"],
    # 1907/1909 biennial volumes are offset by one (see lesson 2026-06-22):
    #   production-1906-07 holds the 1907 REGULAR session (oracle 539).
    #   production-1907-09 holds the 1909 REGULAR session (oracle 729); excluded from the 1907 glob.
    1907: ["production-1906-07"],
    1909: ["production-1907-09"],
    # mid-century budget sessions (-NNchapters sub-volume = even-year budget chapters)
    1952: ["production-1953-vol1-52chapters"],
    1954: ["production-1955-vol1-54chapters"],
    1956: ["production-1957-vol1-56chapters"],
    1958: ["production-1959-vol1-58chapters"],
    1960: ["production-1961-vol1-60chapters"],
    1962: ["production-1963-vol1-62chapters"],
    1964: ["production-1965-vol1-64chapters"],
}

# --- inverse: dir-basename -> oracle session-year (1:1; the merge resolves dirs through this) -----
DIR_TO_YEAR = {}
for _yr, _dirs in YEAR_DIR_ALIAS.items():
    for _b in _dirs:
        assert _b not in DIR_TO_YEAR, (
            f"ALIAS COLLISION: {_b} maps to both {DIR_TO_YEAR[_b]} and {_yr}")
        DIR_TO_YEAR[_b] = _yr


def regular_oracle(path=ORACLE_TSV):
    """session_year -> total_chapters for REGULAR session rows only (the cap rule the scoreboard
    uses). max() across duplicate regular rows for a year is harmless (1850-1999 has at most one
    in-scope regular row per relevant year here)."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("session_type") != "regular":
                continue
            try:
                y = int(row["session_year"])
            except (TypeError, ValueError):
                continue
            out[y] = max(out.get(y, 0), int(row["total_chapters"]))
    return out


def n_for_dir(name, oracle_regular=None):
    """Resolve a production-dir BASENAME to (regular-N, resolved-year) THROUGH THE ALIAS only.
    Returns (None, None) when `name` is not an aliased dir -- the caller then falls back to its
    own leading-year regex for ordinary `production-<year>*` dirs. `oracle_regular` may be passed
    to avoid re-reading the TSV; otherwise it is loaded on demand."""
    yr = DIR_TO_YEAR.get(name)
    if yr is None:
        return (None, None)
    if oracle_regular is None:
        oracle_regular = regular_oracle()
    n = oracle_regular.get(yr)
    return (n, yr) if n is not None else (None, None)
