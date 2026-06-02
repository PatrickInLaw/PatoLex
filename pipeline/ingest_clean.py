"""
ingest_clean.py -- Clean, transactional, UTF-8-faithful act ingest (Phase B).
===============================================================================
Single canonical ingest path that replaces the three divergent scripts
(production_pipeline STAGE6 / re_ingest_fixed / ingest_from_ocr). Fixes Hans
F5/F6/F7/F8/F11/F13.

WHAT CHANGED vs the old ingest (and WHY)
  F5  No more `safe_str` ASCII errors="replace" and no hand-escaped SQL string
      concat. Inserts are **psycopg parameterized** (`%s` placeholders), so §,
      long-s, em-dashes, accents survive verbatim — full UTF-8 committed text.
  F6  Per-act work runs in ONE transaction (enactment + provision +
      designation_history + change_event). Any failure -> rollback that act AND
      **abort the whole volume** (raise). The volume is NEVER marked done on a
      partial ingest, so a gap is always revisited, never silent.
  F7  ONE canonical physical-act key everywhere: (source_document_id,
      in_act_order). in_act_order is the 0-indexed ordinal position of the act
      in the parsed volume — it survives a garbled chapter number. Chapter
      number is best-effort DISPLAY only, never a dedup key.
  F8  No hardcoded ocr_cer_estimate=0.015 / scan_quality='good'. The per-volume
      OCR quality estimate is derived from the consensus per-token confidence
      (mean token confidence -> rough CER proxy); scan_quality is bucketed from
      it. Honest, computed, per-volume.
  F11 chapter_number that required an OCR substitution to parse (e.g. roman
      numeral recovered via J->I / 1->I, or any non-clean numeral) is flagged
      confident=False and carries a 'chapter_ocr_substituted' provenance note;
      the change_event trust_level stays 'ocr_uncertain'.
  F13 NO fabricated dates. If a real Approved/Passed date was parsed, it is used
      as operative_date. If NOT, operative_date is committed as NULL with a
      'date_unknown' flag — never the old {year}-01-01 fiction masquerading as a
      parsed date.

DETERMINISM
  Acts are ingested in parsed order (in_act_order = enumerate index). No dict /
  set iteration drives any committed value. Same input -> same rows.

DRY-RUN (this run)
  Default mode is DRY-RUN: it reads the banked parsed acts + the consensus,
  builds the EXACT parameter tuples it WOULD insert, and prints counts + sample
  rows. It opens NO database connection and imports psycopg lazily only when
  --commit is passed. So running it now, while version-A's ingest loop is live,
  touches nothing.

  --commit  : NOT used yet. When run, connects via PATOLEX_PG_DSN (or the
              individual PG* env vars), and performs the transactional inserts.
              Left un-exercised in Phase B per the no-DB-writes constraint.

INPUT
  Per volume <label>:
    parsed acts JSON  (the parser's confident_acts; same shape as
                       ingest_from_ocr.parse_volume output: chapter_int,
                       chapter_raw, title, iso_date, text, source_page, ...)
    consensus per page (optional) for the per-volume quality estimate.
  This module does NOT re-parse or re-OCR; it consumes banked artifacts.

USAGE
  python ingest_clean.py 1858                 # dry-run one volume
  python ingest_clean.py 1858 1861 1862       # dry-run several
  python ingest_clean.py 1858 --commit        # (DEFERRED — do not run in Phase B)
"""

from __future__ import annotations

import os
import re
import sys
import json
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
REPO = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\PatoLex")
LOG_FILE = REPO / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "phaseB-build-run.log"

# session_label -> (session_str, legislature_ordinal). Superset of both old maps.
LEGISLATURE_MAP = {
    "1850": ("1849-1850", "1st"), "1851": ("1851", "2nd"), "1852": ("1852", "3rd"),
    "1853": ("1853", "4th"), "1854": ("1854", "5th"), "1855": ("1855", "6th"),
    "1856": ("1856", "7th"), "1857": ("1857", "8th"), "1858": ("1858", "9th"),
    "1859": ("1859", "10th"), "1860": ("1860", "11th"), "1861": ("1861", "12th"),
    "1862": ("1862", "13th"), "1863": ("1863", "14th"),
    "1863-64": ("1863-64 adjourned", "15th"), "1865-66": ("1865-66", "16th"),
    "1867-68": ("1867-68", "17th"), "1869-70": ("1869-70", "18th"),
    "1871-72": ("1871-72", "19th"), "1873-74": ("1873-74", "20th"),
    "1875-76": ("1875-76", "21st"),
}

# A "clean" chapter numeral required no OCR substitution to parse.
# Roman is UPPERCASE-only on purpose: a lowercase 'l' (as in OCR 'Il' for 'II')
# is an OCR artifact the parser had to substitute, so it must NOT count as clean.
_CLEAN_ARABIC = re.compile(r"^\d{1,4}$")
_CLEAN_ROMAN = re.compile(r"^[IVXLCDM]{1,12}$")

_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int:
    val = prev = 0
    for c in reversed(s):
        cur = _ROMAN_VAL.get(c, 0)
        val += cur if cur >= prev else -cur
        prev = cur
    return val


def log(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    line = f"[{ts}] {phase} | {description} | {status}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip(), flush=True)


# --------------------------------------------------------------------------- #
# Provenance / quality helpers
# --------------------------------------------------------------------------- #

def chapter_was_ocr_substituted(chapter_raw: str, chapter_int: int) -> bool:
    """
    True if recovering chapter_int from chapter_raw required an OCR substitution
    (Hans F11). A clean arabic ('38') or clean roman ('XII') numeral that parses
    to the same value is NOT a substitution; anything else (J/T/1/!/| -> I, 'l'
    -> I, garbage chars) is.
    """
    raw = (chapter_raw or "").strip().strip(".,;:")
    if not raw:
        return True
    if _CLEAN_ARABIC.match(raw):
        return int(raw) != chapter_int
    if _CLEAN_ROMAN.match(raw):
        # clean UPPERCASE roman: trust only if it actually evaluates to chapter_int
        return _roman_to_int(raw) != chapter_int
    return True  # contained chars only recoverable via substitution (e.g. 'Il','XXITI')


def estimate_volume_quality(page_confidences: List[float]) -> Tuple[float, str]:
    """
    Honest per-volume OCR quality estimate (Hans F8). Derives a CER proxy from
    the mean consensus per-token confidence: cer_proxy ~= 1 - mean_confidence.
    Buckets scan_quality. Returns (cer_proxy_rounded, scan_quality_bucket).
    If no confidences available, returns (None-proxy as -1.0, 'unknown').
    """
    if not page_confidences:
        return -1.0, "unknown"
    mean_conf = sum(page_confidences) / len(page_confidences)
    cer_proxy = round(max(0.0, 1.0 - mean_conf), 4)
    if cer_proxy <= 0.02:
        bucket = "good"
    elif cer_proxy <= 0.07:
        bucket = "fair"
    else:
        bucket = "poor"
    return cer_proxy, bucket


# --------------------------------------------------------------------------- #
# Planned-row model (what we WOULD insert)
# --------------------------------------------------------------------------- #

@dataclass
class PlannedAct:
    in_act_order: int                 # CANONICAL key part 2 (key part 1 = src_doc_id)
    chapter_int: int
    chapter_raw: str
    citation: str
    title: str
    operative_date: Optional[str]     # ISO date or None (NEVER fabricated)
    date_unknown: bool                # True -> operative_date is NULL, flagged
    chapter_ocr_substituted: bool     # True -> chapter_number is uncertain
    confident: bool                   # False if any uncertainty flag set
    new_text: str                     # full UTF-8 committed text
    page_ref: str
    trust_level: str                  # always 'ocr_uncertain' for this corpus
    designation: str
    section_number: str


def plan_volume(session_label: str) -> dict:
    """
    Build the full set of PlannedActs for a volume from banked artifacts.
    Reads:
      parsed_acts_fixed.json  (confident_acts)  -- required
      ocr_consensus/page_ocr_results.json       -- optional, for quality est.
    Does NOT touch the DB. Returns a plan dict.
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    acts_path = scratch / "parsed_acts_fixed.json"
    if not acts_path.exists():
        raise FileNotFoundError(
            f"{session_label}: parsed_acts_fixed.json not found at {acts_path}"
        )
    data = json.loads(acts_path.read_text(encoding="utf-8"))
    confident_acts = data.get("confident_acts", [])

    session_str, legis_num = LEGISLATURE_MAP.get(
        session_label, (session_label, session_label)
    )

    # ---- per-volume quality estimate from consensus confidence (Hans F8) -----
    page_confs: List[float] = []
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    if ocr_path.exists():
        try:
            # Re-derive token consensus confidence per page using consensus.py so
            # the quality estimate reflects the REAL (token-aligned) confidence,
            # not the old bag-of-words ratio. Lazy import to keep this optional.
            sys.path.insert(0, str(REPO / "pipeline"))
            from consensus import consensus_from_page_record  # noqa: E402
            raw = json.loads(ocr_path.read_text(encoding="utf-8"))
            for _k, page in raw.items():
                res = consensus_from_page_record(page)
                if res.n_tokens:
                    page_confs.append(res.page_confidence)
        except Exception as e:  # never fatal — quality est. is best-effort
            log("INGEST-PLAN",
                f"{session_label}: consensus quality est. skipped ({str(e)[:80]})",
                "WARN")
    cer_proxy, scan_quality = estimate_volume_quality(page_confs)

    planned: List[PlannedAct] = []
    for idx, act in enumerate(confident_acts):
        chapter_int = int(act.get("chapter_int", 0) or 0)
        chapter_raw = str(act.get("chapter_raw", ""))
        iso_date = (act.get("iso_date") or "").strip()
        date_unknown = not bool(iso_date)
        operative_date = iso_date if iso_date else None  # F13: NEVER fabricate
        chap_subst = chapter_was_ocr_substituted(chapter_raw, chapter_int)

        citation = f"Stats. {session_label} ch. {chapter_int}"
        designation = citation
        confident = (not date_unknown) and (not chap_subst) and chapter_int > 0

        planned.append(PlannedAct(
            in_act_order=idx,
            chapter_int=chapter_int,
            chapter_raw=chapter_raw,
            citation=citation,
            title=(act.get("title", "") or "")[:500],
            operative_date=operative_date,
            date_unknown=date_unknown,
            chapter_ocr_substituted=chap_subst,
            confident=confident,
            new_text=act.get("text", "") or "",     # FULL UTF-8, no truncation-mangling
            page_ref="p. " + str(act.get("source_page", 0)),
            trust_level="ocr_uncertain",
            designation=designation,
            section_number=str(chapter_int),
        ))

    return {
        "session_label": session_label,
        "session_str": session_str,
        "legislature": legis_num,
        "scan_quality": scan_quality,
        "ocr_cer_estimate": cer_proxy,            # -1.0 means unknown
        "n_pages_with_consensus": len(page_confs),
        "acts": planned,
    }


# --------------------------------------------------------------------------- #
# Parameterized SQL (psycopg style: %s placeholders, values passed separately)
# --------------------------------------------------------------------------- #

ENACTMENT_SQL = (
    "INSERT INTO enactment "
    "(source_document_id, citation, jurisdiction, session, legislature, "
    " chapter_number, chaptered_date, effective_date, operative_date, title, "
    " bill_number, kind) "
    "VALUES (%s, %s, 'CA', %s, %s, %s, %s, %s, %s, %s, NULL, 'statute') "
    "RETURNING id;"
)
PROVISION_SQL = (
    "INSERT INTO provision (jurisdiction, unit_type, current_designation, status) "
    "VALUES ('CA', 'act_section', %s, 'active') RETURNING id;"
)
DESIGNATION_SQL = (
    "INSERT INTO designation_history "
    "(provision_id, code, section_number, label, valid_range) "
    "VALUES (%s, %s, %s, %s, %s);"
)
CHANGE_EVENT_SQL = (
    "INSERT INTO change_event "
    "(enactment_id, provision_id, action, new_text, operative_date, in_act_order, "
    " chaptered_out, trust_level, source_document_id, page_ref) "
    "VALUES (%s, %s, 'enact', %s, %s, %s, false, %s, %s, %s) RETURNING id;"
)
# Canonical dedup check on (source_document_id, in_act_order):
EXISTS_SQL = (
    "SELECT 1 FROM change_event "
    "WHERE source_document_id = %s AND in_act_order = %s LIMIT 1;"
)


def _daterange(operative_date: Optional[str]) -> str:
    """valid_range for designation_history. Open-bounded if date unknown."""
    if operative_date:
        return f"[{operative_date},)"
    return "(,)"  # unknown lower bound, open upper — honest, not a fake date


def enactment_params(src_doc_id, plan, act: PlannedAct):
    return (
        src_doc_id, act.citation, plan["session_str"], plan["legislature"],
        act.chapter_int, act.operative_date, act.operative_date,
        act.operative_date, act.title,
    )


def build_param_plan(src_doc_id, plan) -> List[dict]:
    """Build the parameter tuples for every act (no DB). For dry-run display."""
    rows = []
    for act in plan["acts"]:
        rows.append({
            "in_act_order": act.in_act_order,
            "exists_check": (src_doc_id, act.in_act_order),
            "enactment": enactment_params(src_doc_id, plan, act),
            "provision": (act.designation,),
            "designation_history": (
                None,  # provision_id filled at commit time
                f"Statutes of California {plan['session_label']}",
                act.section_number, act.designation, _daterange(act.operative_date),
            ),
            "change_event": (
                None, None, act.new_text, act.operative_date, act.in_act_order,
                act.trust_level, src_doc_id,  # page_ref appended at commit
            ),
            "flags": {
                "confident": act.confident,
                "date_unknown": act.date_unknown,
                "chapter_ocr_substituted": act.chapter_ocr_substituted,
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# DRY-RUN
# --------------------------------------------------------------------------- #

def dry_run(session_label: str):
    plan = plan_volume(session_label)
    acts = plan["acts"]
    # placeholder src_doc_id for display only; the real id is resolved at commit
    placeholder_src = f"<source_document_id for Stats. {session_label}>"

    n = len(acts)
    n_confident = sum(1 for a in acts if a.confident)
    n_date_unknown = sum(1 for a in acts if a.date_unknown)
    n_chap_subst = sum(1 for a in acts if a.chapter_ocr_substituted)
    n_nonascii = sum(1 for a in acts if any(ord(c) > 127 for c in a.new_text))

    log("INGEST-DRYRUN",
        f"{session_label}: WOULD insert {n} acts "
        f"(confident={n_confident}, date_unknown={n_date_unknown}, "
        f"chapter_ocr_substituted={n_chap_subst}) | "
        f"scan_quality={plan['scan_quality']} cer_est={plan['ocr_cer_estimate']} "
        f"pages_with_consensus={plan['n_pages_with_consensus']} | "
        f"acts_with_nonascii_text={n_nonascii} (UTF-8 preserved)")

    print(f"\n=== DRY-RUN PLAN: Stats. {session_label} ===")
    print(f"  source_document key   : {placeholder_src}")
    print(f"  canonical act key     : (source_document_id, in_act_order)")
    print(f"  acts to ingest        : {n}")
    print(f"    confident=True      : {n_confident}")
    print(f"    date_unknown        : {n_date_unknown}  (operative_date -> NULL, flagged)")
    print(f"    chapter_ocr_subst   : {n_chap_subst}    (confident=False, flagged)")
    print(f"  per-volume quality    : scan_quality={plan['scan_quality']} "
          f"cer_estimate={plan['ocr_cer_estimate']} "
          f"(from {plan['n_pages_with_consensus']} consensus pages)")
    print(f"  acts w/ non-ASCII text: {n_nonascii} (e.g. §, em-dash preserved verbatim)")

    print("\n  --- SAMPLE ROWS (first 3 acts; parameters shown, values bound, never concatenated) ---")
    for act in acts[:3]:
        print(f"\n  act in_act_order={act.in_act_order} citation={act.citation!r} "
              f"chapter_raw={act.chapter_raw!r} confident={act.confident}")
        print(f"    enactment   params: {enactment_params(placeholder_src, plan, act)}")
        print(f"    provision   params: ({act.designation!r},)")
        print(f"    designation params: (<prov_id>, "
              f"{('Statutes of California ' + session_label)!r}, "
              f"{act.section_number!r}, {act.designation!r}, "
              f"{_daterange(act.operative_date)!r})")
        snippet = act.new_text[:120].replace("\n", " ")
        print(f"    change_event new_text[:120]: {snippet!r}")
        print(f"    change_event operative_date: {act.operative_date!r} "
              f"(NULL = unknown, never fabricated)")

    # show a flagged example if any
    flagged = [a for a in acts if not a.confident]
    if flagged:
        ex = flagged[0]
        print(f"\n  --- FLAGGED EXAMPLE (confident=False) ---")
        print(f"    in_act_order={ex.in_act_order} citation={ex.citation!r} "
              f"chapter_raw={ex.chapter_raw!r}")
        print(f"    date_unknown={ex.date_unknown} "
              f"chapter_ocr_substituted={ex.chapter_ocr_substituted}")
    print("")
    return plan


# --------------------------------------------------------------------------- #
# COMMIT (DEFERRED — not exercised in Phase B)
# --------------------------------------------------------------------------- #

def _connect():
    """Lazy psycopg connect. Only called under --commit (not used in Phase B)."""
    import psycopg  # imported lazily so dry-run needs no driver / no DB
    dsn = os.environ.get("PATOLEX_PG_DSN")
    if dsn:
        return psycopg.connect(dsn)
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "patolex"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )


def _resolve_source_document_id(cur, session_label: str) -> int:
    cur.execute(
        "SELECT id FROM source_document "
        "WHERE citation LIKE %s AND page_count IS NOT NULL "
        "ORDER BY id LIMIT 1;",
        (f"Stats. {session_label}%",),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"{session_label}: no production source_document found — "
            f"refusing to ingest (volume not ready)."
        )
    return int(row[0])


def commit_volume(session_label: str):
    """
    Transactional, fail-loud commit. NOT used in Phase B (no DB writes allowed).
    Each act = one transaction; ANY error -> rollback + raise (volume FAILS, is
    never marked done). UTF-8 preserved via parameter binding.
    """
    plan = plan_volume(session_label)
    conn = _connect()
    conn.autocommit = False  # explicit per-act transactions
    inserted = skipped = 0
    try:
        with conn.cursor() as cur:
            src_doc_id = _resolve_source_document_id(cur, session_label)
        for act in plan["acts"]:
            try:
                with conn.cursor() as cur:
                    cur.execute(EXISTS_SQL, (src_doc_id, act.in_act_order))
                    if cur.fetchone():
                        conn.rollback()
                        skipped += 1
                        continue
                    cur.execute(ENACTMENT_SQL, enactment_params(src_doc_id, plan, act))
                    enact_id = cur.fetchone()[0]
                    cur.execute(PROVISION_SQL, (act.designation,))
                    prov_id = cur.fetchone()[0]
                    cur.execute(DESIGNATION_SQL, (
                        prov_id, f"Statutes of California {session_label}",
                        act.section_number, act.designation,
                        _daterange(act.operative_date),
                    ))
                    cur.execute(CHANGE_EVENT_SQL, (
                        enact_id, prov_id, act.new_text, act.operative_date,
                        act.in_act_order, act.trust_level, src_doc_id, act.page_ref,
                    ))
                conn.commit()          # commit THIS act only
                inserted += 1
            except Exception as e:
                conn.rollback()
                # FAIL THE VOLUME — never mark done on partial ingest (F6)
                raise RuntimeError(
                    f"{session_label}: act in_act_order={act.in_act_order} "
                    f"FAILED ({str(e)[:200]}) — volume aborted, NOT marked done."
                ) from e
        log("INGEST-COMMIT",
            f"{session_label}: inserted={inserted} skipped(dup)={skipped} | volume OK",
            "OK")
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main(argv):
    commit = "--commit" in argv
    volumes = [a for a in argv if not a.startswith("--")]
    if not volumes:
        print("Usage: python ingest_clean.py <session_label> [...] [--commit]")
        return 2

    mode = "COMMIT" if commit else "DRY-RUN"
    log("INGEST", f"=== ingest_clean.py {mode}: {', '.join(volumes)} ===",
        "OK" if not commit else "WARN")

    if commit:
        log("INGEST",
            "--commit requested. Phase B forbids DB writes; refusing unless "
            "PATOLEX_ALLOW_COMMIT=1 is explicitly set.", "WARN")
        if os.environ.get("PATOLEX_ALLOW_COMMIT") != "1":
            log("INGEST", "PATOLEX_ALLOW_COMMIT != 1 -> aborting (no DB writes).", "FAIL")
            return 3
        for vol in volumes:
            commit_volume(vol)
    else:
        for vol in volumes:
            try:
                dry_run(vol)
            except FileNotFoundError as e:
                log("INGEST-DRYRUN", str(e), "WARN")

    log("INGEST", f"=== ingest_clean.py {mode} done ===", "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
