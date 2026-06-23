"""Per-year OCR-era recall: completeness BEFORE (best-of merge only) and AFTER (merge + the additive
clause_seq recovery), capped at oracle N, unioned across each session-year's physical volumes.
Reports residual (oracle N - after) per year and the corpus total -- the campaign's scoreboard.

Mapping: exact leading year `production-<year>*` (biennium-named dirs are reported as UNMAPPED with
their oracle weight, never silently dropped). Writes a machine-readable table to
C:\\PatoLex-scratch\\_recall_allyears.json and prints a human table sorted by residual."""
import os, json, glob, csv, re, importlib.util
SCRATCH = r"C:\PatoLex-scratch"
ORACLE = r"C:\GitHub\PatoLex\docs\30_SYSTEM_DESIGN\sources\ca_chapter_counts.tsv"

# --- shared production-dir <-> oracle-year alias (single source of truth; loaded by abs path) -----
# Run as a standalone script, so load the shared module by path (sibling of pipeline/config.py) to
# avoid sys.path/package fragility. merge_passes.py loads the SAME module -> the alias cannot drift.
_ALIAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "year_dir_alias.py")
_spec = importlib.util.spec_from_file_location("patolex_year_dir_alias", _ALIAS_PATH)
_alias = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_alias)

oracle = {}
with open(ORACLE, encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        try:
            yr = int(row["session_year"])
        except Exception:
            continue
        if 1850 <= yr <= 1999 and row["session_type"] == "regular":
            oracle[yr] = int(row["total_chapters"])

def distinct(path, key, N, only_status=None):
    """Distinct chapter_int in a parse file. If only_status is given (e.g. 'image_verified'), count
    ONLY acts with that status -- so visual not_found/legislative_gap entries do NOT inflate the
    recovered count. Returns (counted_set, legislative_gap_set) -- the gap set lists oracle chapters
    that were NEVER enacted (denominator over-count) when present in a visual file."""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return set(), set()
    acts = d.get(key, d) if isinstance(d, dict) else d
    out, leggap = set(), set()
    for a in (acts if isinstance(acts, list) else []):
        if isinstance(a, dict):
            n = a.get("chapter_int_final") or a.get("chapter_int") or a.get("chapter")
            if isinstance(n, int) and 1 <= n <= N:
                st = a.get("status")
                if st == "legislative_gap":
                    leggap.add(n)
                elif only_status is None or st == only_status or (
                        isinstance(only_status, (tuple, list)) and st in only_status):
                    out.add(n)
    return out, leggap

# --- Explicit year->dir alias (added 2026-06-21, cc012-followon: map biennial + budget years) ---
# The naive glob `production-<year>*` misses two structural cases, leaving these oracle years
# reported UNMAPPED (oracle weight ~6,211, dragging corpus-wide coverage). The DATA exists -- it
# just lives under differently-named dirs. Alias resolution runs ONLY when the glob finds nothing,
# so already-mapped years are untouched. CRITICAL: every basename below is unique across the dict
# (asserted at runtime) and none collides with an in-scope `production-<otheryear>*` glob hit, so
# no production dir is ever counted toward two oracle years.
#
# (1) 19th-c BIENNIAL sessions: the Legislature met every 2 years; the oracle records the biennium
#     ONCE under the EVEN year (e.g. "1865-66 Regular Session" -> session_year 1866). The data dir
#     is named for the biennium span (production-1865-66). The "-code" sibling dirs are the same
#     session's code-amendment volume (same chapter numbering -> set-unioned, never summed).
# (2) TRANSITION biennium-named regular sessions 1901/1909/1911 live under production-1900-01 /
#     -1907-09 / -1910-11 (the odd-year regular session bound with the even-year extra session).
# (3) MID-CENTURY budget sessions (tiny "Regular (Budget) Session", oracle N=1..14): the even-year
#     budget chapters were bound into the FOLLOWING odd-year statute volume as a "-NNchapters"
#     sub-volume where NN = the budget calendar year's last two digits (1953_Vol1_52Chapters.pdf =
#     the 1952 chapters). Mapped to that sub-volume dir; capped at oracle N as usual. CRITICAL: the
#     greedy `production-<oddyear>*` glob would ALSO sweep these "-NNchapters" dirs into the adjacent
#     odd-year regular session (e.g. production-1953* matches -52chapters), causing a double-count.
#     We therefore EXCLUDE the budget sub-volume basenames (BUDGET_OWNED_DIRS) from every glob match,
#     handing them solely to the budget year's alias. Verified harmless: removing them costs the odd
#     years <=1 chapter total (the budget chapters 1..N are already covered by the odd year's vol1).
# The alias dicts themselves now live in pipeline/year_dir_alias.py (shared with merge_passes.py and
# _residual_manifest.py) so the merge cap and this scoreboard CANNOT drift. Re-bound here under their
# original names so the rest of this script is unchanged.
BUDGET_OWNED_DIRS = _alias.BUDGET_OWNED_DIRS
YEAR_DIR_ALIAS = _alias.YEAR_DIR_ALIAS

rows, unmapped, counted_basenames = [], [], {}
for yr, N in sorted(oracle.items()):
    dirs = [d for d in glob.glob(os.path.join(SCRATCH, f"production-{yr}*"))
            if os.path.isdir(d) and os.path.basename(d) not in BUDGET_OWNED_DIRS]
    if not dirs and yr in YEAR_DIR_ALIAS:  # glob missed it -> consult the explicit alias
        dirs = [os.path.join(SCRATCH, b) for b in YEAR_DIR_ALIAS[yr]
                if os.path.isdir(os.path.join(SCRATCH, b))]
    if not dirs:
        unmapped.append((yr, N)); continue
    for d in dirs:  # anti-double-count: a dir must never be counted under two oracle years
        b = os.path.basename(d)
        assert b not in counted_basenames, (
            f"DOUBLE-COUNT: {b} mapped to both {counted_basenames[b]} and {yr}")
        counted_basenames[b] = yr
    before, after, leg = set(), set(), set()
    for d in dirs:
        mp = os.path.join(d, "parsed_acts_merged.json")
        if os.path.exists(mp):
            b, _ = distinct(mp, "merged_acts", N); before |= b; after |= b
        cp = os.path.join(d, "parsed_acts_clauserec.json")
        if os.path.exists(cp):
            c, _ = distinct(cp, "recovered_acts", N); after |= c
        vp = os.path.join(d, "parsed_acts_visual.json")  # image_verified + ocr_text_verified count; gaps tracked
        if os.path.exists(vp):
            v, g = distinct(vp, "recovered_acts", N, only_status=("image_verified", "ocr_text_verified")); after |= v; leg |= g
    leg -= after  # a chapter both recovered somewhere AND marked gap elsewhere -> trust the recovery
    eff_N = N - len(leg)  # legislative gaps were never enacted -> reduce the true denominator
    rows.append({"year": yr, "N": N, "eff_N": eff_N, "before": len(before), "after": len(after),
                 "leg_gap": len(leg), "residual": eff_N - len(after),
                 "pct": round(100 * len(after) / eff_N, 1) if eff_N else 100.0, "vols": len(dirs)})

tot_N = sum(r["eff_N"] for r in rows)        # true denominator = oracle N minus legislative gaps
tot_oracleN = sum(r["N"] for r in rows)
tot_before = sum(r["before"] for r in rows)
tot_after = sum(r["after"] for r in rows)
tot_resid = sum(r["residual"] for r in rows)
tot_leg = sum(r["leg_gap"] for r in rows)
unmap_wt = sum(n for _, n in unmapped)
summary = {"mapped_years": len(rows), "tot_eff_N": tot_N, "tot_oracleN": tot_oracleN,
           "tot_before": tot_before, "tot_after": tot_after, "tot_residual": tot_resid,
           "legislative_gaps": tot_leg,
           "pct_before": round(100 * tot_before / tot_N, 1) if tot_N else 0,
           "pct_after": round(100 * tot_after / tot_N, 1) if tot_N else 0,
           "unmapped_years": [y for y, _ in unmapped], "unmapped_weight": unmap_wt}
json.dump({"summary": summary, "rows": rows}, open(os.path.join(SCRATCH, "_recall_allyears.json"), "w"),
          indent=1)

print(f"ANTI-DOUBLE-COUNT OK: {len(counted_basenames)} distinct production dirs, none counted under two oracle years")
print(f"OCR era 1850-1999 mapped years: {len(rows)}  oracleN={tot_oracleN} effN(minus {tot_leg} leg-gaps)={tot_N}")
print(f"  BEFORE (merge only):  {tot_before}/{tot_N} = {summary['pct_before']}%")
print(f"  AFTER (clause+VISUAL image+ocr_text-verified): {tot_after}/{tot_N} = {summary['pct_after']}%   RESIDUAL={tot_resid}")
print(f"  NOTE: pct is over the {len(rows)} MAPPED years only; {len(unmapped)} biennium/budget session-years (oracle weight {unmap_wt}) are UNMEASURED -> corpus-wide incl. those at 0% = {round(100*tot_after/(tot_N+unmap_wt),1)}%")
print(f"  unmapped (biennium-named, not measured): {summary['unmapped_years']} (weight {unmap_wt})")
print(f"\nYears still short (residual desc):")
print(f"  {'year':>5} {'effN':>5} {'before':>6} {'after':>6} {'resid':>5} {'leg':>4} {'pct':>5} vols")
for r in sorted(rows, key=lambda x: -x["residual"]):
    if r["residual"] > 0:
        print(f"  {r['year']:>5} {r['eff_N']:>5} {r['before']:>6} {r['after']:>6} {r['residual']:>5} {r['leg_gap']:>4} {r['pct']:>5} {r['vols']}")
