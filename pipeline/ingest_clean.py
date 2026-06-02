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
  F6  The WHOLE VOLUME runs in ONE transaction (every act's enactment +
      provision + designation_history + change_event). Any failure -> rollback
      the ENTIRE volume (all acts or none) + raise (Hans S2-B: the old per-act
      commit left acts 0..N-1 durably committed on a mid-volume failure). The
      volume is NEVER marked done on a partial ingest, so a gap is always
      revisited, never silent.
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

# Banked per-token consensus artifact name (Phase C disagreement / review
# substrate). Written ALONGSIDE page_ocr_results.json, under ocr_consensus/.
CONSENSUS_OUTPUT_NAME = "consensus_output.json"

# A page is bucketed by its consensus page_confidence (mean per-token confidence,
# weighted by engines present). Thresholds are honest, not tuned to flatter.
PAGE_HIGH_CONF = 0.98   # confidence >  this -> "high"
PAGE_MED_CONF = 0.93    # confidence >  this (and <= HIGH) -> "med"; else "low"

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


def estimate_volume_quality(
    page_confidences: List[float],
) -> Tuple[Optional[float], str]:
    """
    Honest per-volume OCR quality estimate (Hans F8). Derives a CER proxy from
    the mean consensus per-token confidence: cer_proxy ~= 1 - mean_confidence.
    Buckets scan_quality. Returns (cer_proxy_rounded, scan_quality_bucket).

    If no confidences are available, returns (None, 'unknown') — NOT -1.0
    (Hans S2-C): ocr_cer_estimate carries a `>= 0` CHECK constraint, so an
    "unknown" estimate MUST be committed as SQL NULL, never a sentinel that
    would violate the constraint (or, worse, masquerade as a real CER).
    """
    if not page_confidences:
        return None, "unknown"
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
    # --- capture-ALL-signals: per-act OCR consensus signal (Phase C substrate) -
    confidence: Optional[float]       # agreement ratio in [0,1] or None (-> NULL)
    ocr_provenance: dict              # full jsonb provenance written to change_event


def _page_index(page_rec: dict, fallback_key) -> Optional[str]:
    """Normalized 1-indexed page-number string for a page_ocr_results record.

    page_ocr_results.json is keyed by page number; records also carry
    'page_1indexed'. We key our consensus cache by the STRING page number so an
    act's source_page (also a string) maps directly with no int/str ambiguity.
    """
    pi = page_rec.get("page_1indexed", fallback_key)
    if pi is None:
        return None
    return str(pi)


def build_page_consensus(session_label: str) -> dict:
    """
    Build the per-page token consensus for a volume ONCE (with per-engine
    candidates captured) and assemble the banked consensus_output.json payload +
    the per-volume distribution stats. Reads only banked artifacts; no DB.

    Returns a dict:
      {
        "by_page": { page_str: ConsensusResult-as-dict-with-low-conf-summary },
        "page_confs": [float, ...],           # for quality estimate
        "stats": { mean/median/high/med/low/engines/n_pages },
        "output_payload": { ... }             # what gets written to consensus_output.json
        "output_path": Path | None
      }
    """
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    ocr_path = scratch / "ocr_consensus" / "page_ocr_results.json"
    out_path = scratch / "ocr_consensus" / CONSENSUS_OUTPUT_NAME
    by_page: dict = {}
    page_confs: List[float] = []
    engines_seen: set = set()
    pages_payload: dict = {}

    if not ocr_path.exists():
        return {
            "by_page": {}, "page_confs": [], "stats": _empty_stats(),
            "output_payload": None, "output_path": None,
        }

    sys.path.insert(0, str(REPO / "pipeline"))
    from consensus import (  # noqa: E402
        consensus_from_page_record, LOW_CONFIDENCE_THRESHOLD,
    )

    raw = json.loads(ocr_path.read_text(encoding="utf-8"))
    for k, page in raw.items():
        res = consensus_from_page_record(page, capture_candidates=True)
        if not res.n_tokens:
            continue
        page_key = _page_index(page, k)
        page_confs.append(res.page_confidence)
        engines_seen.update(res.engines_used)

        # --- low-confidence (Phase C review) tokens for THIS page -------------
        low_tokens = []
        for t in res.tokens:
            if t.confidence < LOW_CONFIDENCE_THRESHOLD:
                low_tokens.append({
                    "surface": t.surface,
                    "confidence": t.confidence,
                    "n_agree": t.n_agree,
                    "n_present": t.n_present,
                    "candidates": t.candidates or [],
                })

        # banked per-token record (FULL token stream + the low-conf disagreement)
        pages_payload[page_key] = {
            "page_confidence": res.page_confidence,
            "token_agreement_ratio": res.token_agreement_ratio,
            "method": res.method,
            "engines_used": res.engines_used,
            "n_tokens": res.n_tokens,
            "tokens": [
                {
                    "surface": t.surface,
                    "confidence": t.confidence,
                    "n_agree": t.n_agree,
                    "n_present": t.n_present,
                    "candidates": t.candidates or [],
                }
                for t in res.tokens
            ],
            "low_confidence_token_count": len(low_tokens),
        }
        # compact per-page handle the act provenance step uses (avoid re-walking
        # the full token list per act)
        by_page[page_key] = {
            "page_confidence": res.page_confidence,
            "token_agreement_ratio": res.token_agreement_ratio,
            "method": res.method,
            "engines_used": res.engines_used,
            "low_confidence_tokens": low_tokens,
        }

    stats = _distribution_stats(page_confs, sorted(engines_seen))
    output_payload = {
        "session_label": session_label,
        "consensus_module": "consensus.py token_majority (S1-A/S1-B)",
        "low_confidence_threshold": float(
            __import__("consensus").LOW_CONFIDENCE_THRESHOLD
        ),
        "n_pages": len(pages_payload),
        "stats": stats,
        "pages": pages_payload,
    }
    return {
        "by_page": by_page,
        "page_confs": page_confs,
        "stats": stats,
        "output_payload": output_payload,
        "output_path": out_path,
    }


def _empty_stats() -> dict:
    return {
        "mean_agreement": None, "median_agreement": None,
        "high_count": 0, "med_count": 0, "low_count": 0,
        "engines": [], "n_pages": 0,
    }


def _distribution_stats(page_confs: List[float], engines: List[str]) -> dict:
    if not page_confs:
        return {**_empty_stats(), "engines": engines}
    s = sorted(page_confs)
    n = len(s)
    mid = n // 2
    median = s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
    high = sum(1 for c in page_confs if c > PAGE_HIGH_CONF)
    med = sum(1 for c in page_confs if PAGE_MED_CONF < c <= PAGE_HIGH_CONF)
    low = sum(1 for c in page_confs if c <= PAGE_MED_CONF)
    return {
        "mean_agreement": round(sum(page_confs) / n, 4),
        "median_agreement": round(median, 4),
        "high_count": high, "med_count": med, "low_count": low,
        "engines": engines, "n_pages": n,
    }


def bank_consensus_output(plan: dict) -> Optional[str]:
    """
    Persist the per-token consensus_output.json (Phase C substrate) ALONGSIDE
    page_ocr_results.json. No DB. Idempotent: overwrites with the freshly-derived
    deterministic payload. Returns the written path (or None if no consensus).

    This is what makes the Phase C disagreement/review queue a QUERY over
    persisted data: source_document.ocr_stats.consensus_output_path points here,
    and each change_event.ocr_provenance.disagreement summarizes the per-act slice.
    """
    payload = plan.get("consensus_output_payload")
    path_str = plan.get("consensus_output_path")
    if not payload or not path_str:
        log("INGEST-CONSENSUS",
            f"{plan['session_label']}: no consensus payload to bank "
            f"(no page_ocr_results / no tokens)", "WARN")
        return None
    out_path = Path(path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log("INGEST-CONSENSUS",
        f"{plan['session_label']}: banked {out_path.name} "
        f"({payload['n_pages']} pages, "
        f"low_conf_threshold={payload['low_confidence_threshold']})", "OK")
    return str(out_path)


def plan_volume(session_label: str) -> dict:
    """
    Build the full set of PlannedActs for a volume from banked artifacts.
    Reads:
      parsed_acts_fixed.json  (confident_acts)  -- required
      ocr_consensus/page_ocr_results.json       -- optional, drives ALL signals
    Does NOT touch the DB. Returns a plan dict.

    capture-ALL-signals: the per-page token consensus is built ONCE (with
    per-engine candidates), banked as consensus_output.json, summarized into
    per-volume ocr_stats, and joined per-act (by source_page) into the act's
    ocr_provenance + confidence. Nothing computed is discarded (Patrick).
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

    # ---- per-page consensus (once) + bank consensus_output.json + stats ------
    consensus = {"by_page": {}, "page_confs": [], "stats": _empty_stats(),
                 "output_payload": None, "output_path": None}
    try:
        consensus = build_page_consensus(session_label)
    except Exception as e:  # never fatal — signals are best-effort, ingest still runs
        log("INGEST-PLAN",
            f"{session_label}: consensus build skipped ({str(e)[:80]})", "WARN")

    page_confs = consensus["page_confs"]
    by_page = consensus["by_page"]
    stats = consensus["stats"]
    cer_proxy, scan_quality = estimate_volume_quality(page_confs)

    consensus_output_path = (
        str(consensus["output_path"]) if consensus["output_path"] else None
    )
    ocr_stats = {
        "mean_agreement": stats["mean_agreement"],
        "median_agreement": stats["median_agreement"],
        "high_count": stats["high_count"],
        "med_count": stats["med_count"],
        "low_count": stats["low_count"],
        "engines": stats["engines"],
        "n_pages": stats["n_pages"],
        "consensus_output_path": consensus_output_path,
    }

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

        # ---- join the act to its source page's consensus signal --------------
        src_page = str(act.get("source_page", "")).strip()
        page_ref = "p. " + (src_page if src_page else "0")
        pc = by_page.get(src_page)
        if pc is not None:
            agreement = pc["page_confidence"]
            engines = pc["engines_used"]
            method = pc["method"]
            low_toks = pc["low_confidence_tokens"]
        else:
            # no consensus for this page -> honest NULLs, not a fabricated 1.0
            agreement = None
            engines = []
            method = None
            low_toks = []

        # page-level n_agree/n_present proxy (engines that produced this page):
        n_present = len(engines) if engines else None
        n_agree = None  # per-act agreement is page_confidence; per-token in payload

        ocr_provenance = {
            "engines": engines,
            "consensus_method": method,
            "agreement": agreement,
            "chapter_raw": chapter_raw,
            "chapter_ocr_substituted": chap_subst,
            "date_unknown": date_unknown,
            "page_ref": page_ref,
            "n_agree": n_agree,
            "n_present": n_present,
            "disagreement": {
                "low_confidence_token_count": len(low_toks),
                # cap the inline list so a pathological page can't bloat the row;
                # the FULL per-token stream lives in consensus_output.json, which
                # this provenance references via source_document.ocr_stats.
                "low_confidence_tokens": low_toks[:50],
            },
        }

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
            page_ref=page_ref,
            trust_level="ocr_uncertain",
            designation=designation,
            section_number=str(chapter_int),
            confidence=agreement,                    # None -> SQL NULL (S2-C convention)
            ocr_provenance=ocr_provenance,
        ))

    return {
        "session_label": session_label,
        "session_str": session_str,
        "legislature": legis_num,
        "scan_quality": scan_quality,
        "ocr_cer_estimate": cer_proxy,            # None means unknown -> SQL NULL (S2-C)
        "n_pages_with_consensus": len(page_confs),
        "ocr_stats": ocr_stats,
        "consensus_output_payload": consensus["output_payload"],
        "consensus_output_path": consensus_output_path,
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
    " chaptered_out, trust_level, source_document_id, page_ref, "
    " confident, confidence, ocr_provenance) "
    "VALUES (%s, %s, 'enact', %s, %s, %s, false, %s, %s, %s, %s, %s, %s) "
    # S2-A canonical key: idempotent re-ingest. Requires the UNIQUE index
    # uq_change_event_src_doc_in_act_order to exist (apply per migration plan).
    "ON CONFLICT (source_document_id, in_act_order) DO NOTHING "
    "RETURNING id;"
)
# Per-volume source_document quality signals (capture-ALL-signals). Writes the
# REAL scan_quality + ocr_cer_estimate (NULL if unknown — never -1.0/hardcoded)
# + the ocr_stats jsonb. Targets the resolved production source_document row.
SOURCE_DOC_UPDATE_SQL = (
    "UPDATE source_document "
    "SET scan_quality = %s, ocr_cer_estimate = %s, ocr_stats = %s "
    "WHERE id = %s;"
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
                act.trust_level, src_doc_id, act.page_ref,
                act.confident, act.confidence,
                act.ocr_provenance,  # wrapped as Jsonb at commit time
            ),
            "flags": {
                "confident": act.confident,
                "confidence": act.confidence,
                "date_unknown": act.date_unknown,
                "chapter_ocr_substituted": act.chapter_ocr_substituted,
                "low_confidence_token_count":
                    act.ocr_provenance.get("disagreement", {})
                    .get("low_confidence_token_count", 0),
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

    # ---- WOULD-WRITE: source_document per-volume signal row -------------------
    st = plan["ocr_stats"]
    print("\n  --- source_document UPDATE (per-volume signals; WOULD write) ---")
    print(f"    scan_quality      : {plan['scan_quality']!r}")
    print(f"    ocr_cer_estimate  : {plan['ocr_cer_estimate']!r} "
          f"(None -> SQL NULL, never -1.0/hardcoded)")
    print(f"    ocr_stats (jsonb) : mean_agreement={st['mean_agreement']} "
          f"median_agreement={st['median_agreement']} "
          f"high/med/low={st['high_count']}/{st['med_count']}/{st['low_count']} "
          f"engines={st['engines']} n_pages={st['n_pages']}")
    print(f"    ocr_stats.consensus_output_path: {st['consensus_output_path']!r}")

    # ---- WOULD-BANK: consensus_output.json (no write in dry-run) --------------
    payload = plan.get("consensus_output_payload")
    print("\n  --- consensus_output.json (Phase C substrate; WOULD bank, NOT written in dry-run) ---")
    if payload:
        n_low_pages = sum(
            1 for p in payload["pages"].values()
            if p["low_confidence_token_count"] > 0
        )
        total_low = sum(
            p["low_confidence_token_count"] for p in payload["pages"].values()
        )
        print(f"    path              : {plan['consensus_output_path']}")
        print(f"    pages             : {payload['n_pages']} "
              f"(low_conf_threshold={payload['low_confidence_threshold']})")
        print(f"    pages w/ low-conf : {n_low_pages}  total low-conf tokens: {total_low}")
        # show one sample low-confidence token (the crowd-correction unit)
        sample_low = None
        for p in payload["pages"].values():
            for t in p["tokens"]:
                if t["confidence"] < payload["low_confidence_threshold"]:
                    sample_low = t
                    break
            if sample_low:
                break
        if sample_low:
            print(f"    sample low-conf token: surface={sample_low['surface']!r} "
                  f"conf={sample_low['confidence']} "
                  f"n_agree/n_present={sample_low['n_agree']}/{sample_low['n_present']}")
            print(f"      disagreeing candidates: {sample_low['candidates']}")
    else:
        print("    (no consensus payload — no page_ocr_results.json / no tokens)")

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
        print(f"    change_event confident     : {act.confident}")
        print(f"    change_event confidence    : {act.confidence!r} "
              f"(real 0-1, None -> SQL NULL)")
        prov = act.ocr_provenance
        print(f"    change_event ocr_provenance: engines={prov['engines']} "
              f"method={prov['consensus_method']!r} agreement={prov['agreement']} "
              f"chapter_raw={prov['chapter_raw']!r} "
              f"chapter_ocr_substituted={prov['chapter_ocr_substituted']} "
              f"date_unknown={prov['date_unknown']} "
              f"n_agree/n_present={prov['n_agree']}/{prov['n_present']}")
        dis = prov["disagreement"]
        print(f"      disagreement: low_confidence_token_count="
              f"{dis['low_confidence_token_count']} "
              f"(inline list capped at 50; full stream in consensus_output.json)")

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

    Hans S2-B FIX: the ENTIRE volume is ONE transaction (all acts or none).
    The old code did `conn.commit()` per act, so a mid-volume failure left acts
    0..N-1 durably committed even though F6 requires "fail the whole volume" —
    a partial volume would then be silently half-present and (per F6) never
    revisited cleanly. Now: a single transaction spans every act; ANY error ->
    `conn.rollback()` discards the WHOLE volume + raise (volume FAILS, is NEVER
    marked done). UTF-8 preserved via parameter binding.

    Duplicate acts (already present by canonical key) are skipped WITHIN the same
    transaction (no per-act rollback that would discard prior inserts).
    """
    plan = plan_volume(session_label)
    # Bank the per-token consensus_output.json FIRST (no DB; the Phase C
    # substrate is durable even if the DB commit is later deferred/rolled back).
    bank_consensus_output(plan)

    from psycopg.types.json import Jsonb  # jsonb param wrapper (commit-path only)

    conn = _connect()
    conn.autocommit = False  # ONE explicit transaction for the whole volume
    inserted = skipped = 0
    try:
        with conn.cursor() as cur:
            src_doc_id = _resolve_source_document_id(cur, session_label)
            for act in plan["acts"]:
                cur.execute(EXISTS_SQL, (src_doc_id, act.in_act_order))
                if cur.fetchone():
                    skipped += 1
                    continue  # already present; do NOT re-insert, do NOT rollback
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
                    act.confident, act.confidence, Jsonb(act.ocr_provenance),
                ))
                # ON CONFLICT DO NOTHING -> RETURNING is empty on a concurrent dup;
                # that means the act was inserted by someone else after our EXISTS
                # check. Treat as skipped (do NOT roll back the volume).
                if cur.fetchone() is None:
                    skipped += 1
                else:
                    inserted += 1
            # ---- per-volume source_document signals (real, computed) ----------
            cur.execute(SOURCE_DOC_UPDATE_SQL, (
                plan["scan_quality"],
                plan["ocr_cer_estimate"],          # None -> SQL NULL (S2-C)
                Jsonb(plan["ocr_stats"]),
                src_doc_id,
            ))
        conn.commit()  # COMMIT ONCE — all acts or none (S2-B / F6)
        log("INGEST-COMMIT",
            f"{session_label}: inserted={inserted} skipped(dup)={skipped} | "
            f"scan_quality={plan['scan_quality']} cer={plan['ocr_cer_estimate']} | "
            f"volume committed atomically (single txn)",
            "OK")
    except Exception as e:
        conn.rollback()  # discard the ENTIRE volume — nothing durable on failure
        # FAIL THE VOLUME — never mark done on partial ingest (F6/S2-B)
        raise RuntimeError(
            f"{session_label}: volume FAILED ({str(e)[:200]}) — entire volume "
            f"rolled back (0 acts committed), NOT marked done."
        ) from e
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
