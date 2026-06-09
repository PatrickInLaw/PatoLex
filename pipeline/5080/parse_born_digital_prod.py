r"""
parse_born_digital_prod.py -- PRODUCTION born-digital (1997-2008) extractor.
============================================================================
Standalone, self-contained, NO DATABASE. Designed to run on the 3060
workstation for the modern Chief Clerk PDFs (born-digital, clean text layer
via PyMuPDF `get_text()` -- no OCR needed).

Productionizes pipeline/5080/parse_born_digital.py (prototype validated on
2008_Vol1 -> 227 chapters) across the full 1997-2008 range and MULTI-VOLUME
years. The shared date/marker/chapter helpers from ingest_from_ocr.py are
INLINED here (byte-faithful copies) so this script has ZERO dependency on the
DB-bound ingest module and writes NOTHING to Postgres.

Per the format spec (docs/80_PROJECT_HISTORY/MODERN_STATUTE_FORMAT_2026-06-02.md):
  - Chapter headers are standalone `^CHAPTER \d+$` lines (Arabic).
  - Chapter numbers are CONTINUOUS across a year's Vol1..VolN.
  - Running-head footer `[ Ch.  N ]` is NOT a header and is never matched by the
    strict `^\s*CHAPTER\s+\d+\s*$` regex.
  - No bill markers in chaptered-statute sections (confirmed absent).

Output: one JSON per volume at <out_root>/production-<label>/born_digital_parsed.json
where <label> is e.g. "1997_Vol1". Also writes a per-run summary JSON.

Usage:
    # parse a set of volumes (each arg is a PDF path)
    python parse_born_digital_prod.py --out C:\\path\\out <vol1.pdf> <vol2.pdf> ...

    # OR point at a directory + year range and let it enumerate <year>_Vol*.pdf
    python parse_born_digital_prod.py --pdf-dir C:\\...\\pdfs \\
        --year-min 1997 --year-max 2008 --out C:\\...\\out \\
        --workers 3
"""

import sys
import os
import re
import json
import time
import argparse
import datetime
import traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# DATE REVIEW WORKLIST (same file as ingest_from_ocr.py uses)
# ---------------------------------------------------------------------------
DATE_REVIEW_WORKLIST = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\date-review-worklist.jsonl"
)


def _append_date_review(record: dict):
    """Append one JSON record to the date review worklist (JSONL, append-only).

    MUST only be called from the MAIN process — not from inside a
    ProcessPoolExecutor worker.  Worker subprocesses collect review records as
    part of their return value (see process_one / parse_born_digital_volume) and
    the main process calls this function once per record after collecting results.
    Calling it concurrently from multiple subprocesses is NOT safe on Windows
    (file appends are not atomic; writes interleave and corrupt the JSONL).
    """
    line = json.dumps(record, ensure_ascii=False) + "\n"
    DATE_REVIEW_WORKLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(str(DATE_REVIEW_WORKLIST), "a", encoding="utf-8") as fh:
        fh.write(line)

# ---------------------------------------------------------------------------
# INLINED helpers (byte-faithful copies of ingest_from_ocr.py definitions).
# Keeping them here makes this script self-contained and DB-free.
# ---------------------------------------------------------------------------
AN_ACT_RE = re.compile(r"\bAn?\s+A[CEO][TI]\b", re.IGNORECASE)
ENACT_MARKER_RE = re.compile(
    r"People\s+of\s+the\s+State\s+of\s+California"
    r"|do\s+enact\s+as\s+follow",
    re.I,
)
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?"
    r"|May|Mav"
    r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?"
    r"|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_KW = r"(?:A[Pp]{1,3}[Rr]{1,3}[Oo]?[Vv]\w{0,6}|Pass(?:ed)?)"
_YEAR = r"((?:18|19|20)\d\d)"
APPROVED_RE = re.compile(
    _KW + r"\s*[,.]?\s*" + r"(" + _MONTHS + r")"
    + r"\s+((?:[IilOo]?\d+|[IilOo])(?:st|nd|rd|th|d)?)"
    + r"[,.]?\s*" + _YEAR + r"\b",
    re.IGNORECASE,
)
APPROVED_MODERN_RE = re.compile(
    r"(?:Approved\s+by\s+(?:the\s+)?Governor"
    r"|Filed\s+with\s+Secretary\s+of\s+State)"
    r"\s+(" + _MONTHS + r")"
    r"\s+(\d{1,2})"
    r"\s*,?\s*" + _YEAR + r"\b",
    re.IGNORECASE | re.DOTALL,
)
_MONTH_NORM = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "mav": "May", "jun": "June", "jul": "July",
    "aug": "August", "sep": "September", "oct": "October",
    "nov": "November", "dec": "December",
}


def normalize_day(day_str):
    s = day_str.strip()
    s = re.sub(r"(?i)(st|nd|rd|th|d)$", "", s)
    if s.upper() in ("I", "L"):
        return "1"
    if s.upper() == "O":
        return "0"
    s = re.sub(r"^[Il](?=\d)", "1", s)
    s = re.sub(r"^O(?=\d)", "0", s)
    return s if s else "1"


def normalize_month(month_str):
    return _MONTH_NORM.get(month_str.lower()[:3], month_str.capitalize())


def parse_act_date(text, volume_year=None, _rejected_out=None):
    """Return (iso_date_str, raw_match_str) or (None, "").

    volume_year -- the nominal calendar year of the source PDF (e.g. 1997 for
    "1997_Vol3.pdf").  When supplied, any parsed year outside the window
        [volume_year - YEAR_CLAMP_WINDOW, volume_year + YEAR_CLAMP_WINDOW]
    is rejected rather than being committed as the act's approval date.

    YEAR_CLAMP_WINDOW = 3  (same constant as in ingest_from_ocr.py).

    _rejected_out -- optional list.  When provided AND volume_year is set, each
    out-of-window match (a date that was FOUND by a regex but whose year is
    implausible) is appended as a dict {"raw": str, "parsed_year": int}.
    "No match at all" is NOT appended — only implausible matches are.

    Distinguishing "no date found" vs "date found but implausible":
      * Return (None, "") with empty _rejected_out -> genuinely no date present.
      * Return (None, "") with non-empty _rejected_out -> date(s) found but all
        out-of-window; OCR-error suspect, not a legitimately dateless act.

    Order of attempt for born-digital volumes:
      1. APPROVED_MODERN_RE first ("Approved by Governor …" / "Filed with
         Secretary of State …") — the authoritative approval-date format in
         all Chief Clerk chaptered-statute PDFs.  By trying this BEFORE the
         permissive APPROVED_RE we prevent the Cluster-B "date poisoning" bug
         where APPROVED_RE's finditer() grabs the FIRST match, which on
         boilerplate-heavy acts (e.g. B&P §473.15) was a historical date
         embedded in the act body (e.g. "initiative measure approved June 2,
         1913") rather than the real approval date in the header bracket.
      2. APPROVED_RE with year clamp as defence-in-depth fallback (handles
         volumes with older formatting or where APPROVED_MODERN_RE finds nothing).
    """
    YEAR_CLAMP_WINDOW = 3

    def _year_ok(year_int):
        if volume_year is None:
            return True
        return abs(year_int - volume_year) <= YEAR_CLAMP_WINDOW

    def _record_rejected(raw_str, year_int):
        if _rejected_out is not None:
            _rejected_out.append({"raw": raw_str, "parsed_year": year_int})

    # --- 1. Modern structured format first (Cluster-B fix) -------------------
    for m in APPROVED_MODERN_RE.finditer(text):
        month_str = normalize_month(m.group(1))
        day_str = m.group(2)
        year_raw = m.group(3)
        try:
            d = datetime.datetime.strptime(
                month_str + " " + day_str + " " + year_raw, "%B %d %Y")
            if not _year_ok(d.year):
                _record_rejected(re.sub(r"\s+", " ", m.group(0)).strip(), d.year)
                continue
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            return d.strftime("%Y-%m-%d"), raw
        except Exception:
            continue

    # --- 2. Permissive OCR-fuzzy fallback with year clamp (Cluster-A / B defence)
    for m in APPROVED_RE.finditer(text):
        month_str = normalize_month(m.group(1))
        day_str = normalize_day(m.group(2))
        year_raw = m.group(3)
        try:
            d = datetime.datetime.strptime(
                month_str + " " + day_str + " " + year_raw, "%B %d %Y")
            if not _year_ok(d.year):
                _record_rejected(re.sub(r"\s+", " ", m.group(0)).strip(), d.year)
                continue
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            return d.strftime("%Y-%m-%d"), raw
        except Exception:
            continue

    return None, ""


CHAP_HDR_RE = re.compile(r"^\s*CHAPTER\s+(\d+)\s*$")


# ---------------------------------------------------------------------------
# Core per-volume extraction (faithful to prototype parse_born_digital_volume).
# ---------------------------------------------------------------------------
def parse_born_digital_volume(pdf_path):
    """Extract chaptered statutes from one born-digital Statutes volume.

    Returns (acts, meta, review_records) where:
      - acts        list of act dicts (one per CHAPTER header found)
      - meta        dict with page_count, total_text_chars, has_text_layer
      - review_records  list of date-review worklist dicts for acts whose
                        parsed date year was implausible (date_needs_review=True).

    IMPORTANT: review_records are RETURNED to the caller rather than written
    directly to the JSONL worklist file here.  This function runs inside a
    ProcessPoolExecutor worker subprocess; concurrent file appends from multiple
    workers are NOT atomic on Windows and corrupt the JSONL.  The main process
    is responsible for calling _append_date_review() once per record after
    collecting results from all futures.

    NOTE on DB ingest: acts with date_needs_review=True are placed in the
    acts_flagged bucket (confident=False) and EXCLUDED from DB ingest.  They
    are retained in the JSON stage file under the act list so the parse output
    is complete.  Whether flagged acts should instead be ingested with a flag
    is a pending design decision (see DECISION PENDING comment in process_one).
    """
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    lines = []
    total_chars = 0
    for pi in range(page_count):
        txt = doc[pi].get_text()
        total_chars += len(txt)
        for ln in txt.split("\n"):
            lines.append((pi, ln))
    doc.close()

    # born-digital sanity: a real text layer yields plenty of chars.
    has_text_layer = total_chars > 1000

    # Derive the nominal volume year from the PDF filename for the year-sanity
    # clamp passed to parse_act_date().  e.g. "1997_Vol3.pdf" -> 1997.
    volume_year = year_of(pdf_path)

    starts = [i for i, (pi, ln) in enumerate(lines) if CHAP_HDR_RE.match(ln)]
    acts = []
    review_records = []  # collected here; written by main process (concurrency fix)
    for k, si in enumerate(starts):
        ei = starts[k + 1] if k + 1 < len(starts) else len(lines)
        chap_num = int(CHAP_HDR_RE.match(lines[si][1]).group(1))
        start_page = lines[si][0]
        block_lines = [ln for (pi, ln) in lines[si:ei]]
        full = "\n".join(block_lines).strip()

        title = ""
        for j, ln in enumerate(block_lines):
            if AN_ACT_RE.search(ln):
                tparts = [ln]
                for nxt in block_lines[j + 1:j + 6]:
                    if nxt.lstrip().startswith("[") or ENACT_MARKER_RE.search(nxt):
                        break
                    tparts.append(nxt)
                title = re.sub(r"\s+", " ", " ".join(tparts)).strip()[:500]
                break

        # Parse the date ONCE; result is reused for both the confidence gate and
        # the act record — avoids the double-parse that existed when is_confident_act
        # re-ran parse_act_date independently.
        rejected = []
        iso_date, approved_str = parse_act_date(
            full, volume_year=volume_year, _rejected_out=rejected)

        # If a date was FOUND by a regex but the year is implausible, flag it.
        # DECISION PENDING: flagged acts are currently excluded from DB ingest
        # (confident=False); whether they should instead be ingested with a flag
        # is an open product decision.  Do NOT change this routing until that
        # decision is made.
        date_needs_review = False
        if iso_date is None and rejected:
            date_needs_review = True
            label = label_for(pdf_path)
            citation = label + " ch." + str(chap_num)
            for rej in rejected:
                review_rec = {
                    "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
                    "session_label": label,
                    "volume_year": volume_year,
                    "raw_match": rej["raw"],
                    "parsed_year": rej["parsed_year"],
                    "year_delta": (
                        abs(rej["parsed_year"] - volume_year) if volume_year else None
                    ),
                    "citation": citation,
                    "source_page": start_page + 1,
                    "in_act_order": k,
                    "reason": "year_out_of_window",
                }
                # Collect for main-process write — do NOT call _append_date_review
                # here (subprocess concurrency hazard on Windows).
                review_records.append(review_rec)
            # Do NOT print from the worker subprocess — output interleaves
            # unpredictably under multiprocessing.  The main process prints a
            # summary line for each flagged act after collecting results.

        # Use iso_date / date_needs_review already computed above (no re-parse).
        confident = (
            chap_num > 0
            and bool(AN_ACT_RE.search(full))
            and bool(ENACT_MARKER_RE.search(full))
            and iso_date is not None
            and not date_needs_review  # implausible-date acts are NOT confident
            and len(full) >= 100
        )
        acts.append({
            "chapter": str(chap_num),
            "chapter_int": chap_num,
            "chapter_raw": str(chap_num),
            "title": title,
            "approved_date": approved_str,
            "iso_date": iso_date,
            "date_needs_review": date_needs_review,
            "text": re.sub(r"[ \t]+", " ", full)[:6000],
            "source_page": start_page + 1,
            "confident": confident,
        })
    meta = {
        "page_count": page_count,
        "total_text_chars": total_chars,
        "has_text_layer": has_text_layer,
    }
    return acts, meta, review_records


def label_for(pdf_path):
    """e.g. C:\\...\\1997_Vol3.pdf -> 1997_Vol3"""
    return Path(pdf_path).stem


def year_of(pdf_path):
    m = re.match(r"(\d{4})", Path(pdf_path).stem)
    return int(m.group(1)) if m else 0


def vol_of(pdf_path):
    m = re.search(r"Vol(\d+)", Path(pdf_path).stem, re.I)
    return int(m.group(1)) if m else 0


def process_one(args):
    """Worker: parse one volume, write its per-volume JSON, return a summary.

    IMPORTANT — date-review worklist writes are NOT performed here.
    parse_born_digital_volume() returns review records as part of its result;
    they are included in this dict under the key "review_records" and written
    to the JSONL worklist by the MAIN process after collecting all futures.
    This avoids concurrent file appends from multiple worker subprocesses, which
    are NOT atomic on Windows and would corrupt the JSONL.

    DECISION PENDING: acts with date_needs_review=True are excluded from DB
    ingest (confident=False).  Whether they should be ingested-with-a-flag
    instead is an open product decision.
    """
    pdf_path, out_root = args
    label = label_for(pdf_path)
    t0 = time.time()
    rec = {
        "label": label,
        "pdf": str(pdf_path),
        "year": year_of(pdf_path),
        "vol": vol_of(pdf_path),
        "ok": False,
        "error": None,
        "review_records": [],  # populated on success; written by main process
    }
    try:
        acts, meta, review_records = parse_born_digital_volume(pdf_path)
        out_dir = Path(out_root) / ("production-" + label)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "born_digital_parsed.json"
        payload = {
            "label": label,
            "source_pdf": str(pdf_path),
            "year": rec["year"],
            "vol": rec["vol"],
            "page_count": meta["page_count"],
            "has_text_layer": meta["has_text_layer"],
            "chapter_count": len(acts),
            "confident_count": sum(1 for a in acts if a["confident"]),
            "chapter_min": min((a["chapter_int"] for a in acts), default=0),
            "chapter_max": max((a["chapter_int"] for a in acts), default=0),
            "acts": acts,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        rec.update({
            "ok": True,
            "out": str(out_path),
            "page_count": meta["page_count"],
            "has_text_layer": meta["has_text_layer"],
            "chapter_count": len(acts),
            "confident_count": payload["confident_count"],
            "chapter_min": payload["chapter_min"],
            "chapter_max": payload["chapter_max"],
            "no_text_layer": not meta["has_text_layer"],
            "secs": round(time.time() - t0, 1),
            "review_records": review_records,
        })
    except Exception as e:
        rec["error"] = repr(e) + "\n" + traceback.format_exc()
        rec["secs"] = round(time.time() - t0, 1)
    return rec


def enumerate_pdfs(pdf_dir, year_min, year_max):
    out = []
    for p in sorted(Path(pdf_dir).glob("*.pdf")):
        y = year_of(p)
        if year_min <= y <= year_max and re.search(r"Vol\d+", p.stem, re.I):
            out.append(str(p))
    out.sort(key=lambda p: (year_of(p), vol_of(p)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="*", help="explicit PDF paths")
    ap.add_argument("--pdf-dir", default=None)
    ap.add_argument("--year-min", type=int, default=1997)
    ap.add_argument("--year-max", type=int, default=2008)
    ap.add_argument("--out", required=True, help="output root dir")
    ap.add_argument("--workers", type=int, default=3,
                    help="GENTLE cap (default 3); this is a workstation.")
    args = ap.parse_args()

    if args.pdf_dir:
        pdfs = enumerate_pdfs(args.pdf_dir, args.year_min, args.year_max)
    else:
        pdfs = sorted(args.pdfs, key=lambda p: (year_of(p), vol_of(p)))
    if not pdfs:
        print("No PDFs to process.")
        sys.exit(1)

    workers = max(1, min(args.workers, 4))  # hard ceiling: gentle on workstation
    print("Volumes: %d | workers: %d | out: %s" % (len(pdfs), workers, args.out),
          flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_one, (p, args.out)): p for p in pdfs}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            if r["ok"]:
                print("OK   %-14s pages=%-5s chapters=%-4s confident=%-4s "
                      "range=%s..%s text_layer=%s %ss" % (
                          r["label"], r["page_count"], r["chapter_count"],
                          r["confident_count"], r["chapter_min"],
                          r["chapter_max"], r["has_text_layer"], r["secs"]),
                      flush=True)
            else:
                print("FAIL %-14s %s" % (r["label"], r["error"]), flush=True)

    # Write date-review records from the MAIN process (concurrency fix: worker
    # subprocesses returned records via their result dict; we write them here
    # in a single-threaded context so file appends are safe and non-interleaving).
    # Print DATE-REVIEW-FLAG summary lines here too (moved from worker to avoid
    # interleaved output under multiprocessing).
    for r in results:
        for rev in r.get("review_records", []):
            _append_date_review(rev)
            print(
                "DATE-REVIEW-FLAG  " + rev["citation"]
                + "  page=" + str(rev["source_page"])
                + "  implausible_year=" + str(rev["parsed_year"])
                + "  volume_year=" + str(rev["volume_year"])
                + "  -- worklist updated",
                flush=True,
            )

    results.sort(key=lambda r: (r.get("year", 0), r.get("vol", 0)))

    # Year-level continuity report (chapters run continuous across a year's vols).
    years = {}
    for r in results:
        if r["ok"]:
            years.setdefault(r["year"], []).append(r)
    year_report = {}
    for y, recs in sorted(years.items()):
        recs.sort(key=lambda r: r["vol"])
        spans = [(r["vol"], r["chapter_min"], r["chapter_max"]) for r in recs]
        total_ch = sum(r["chapter_count"] for r in recs)
        ymax = max((r["chapter_max"] for r in recs), default=0)
        ymin = min((r["chapter_min"] for r in recs if r["chapter_min"] > 0),
                   default=0)
        year_report[str(y)] = {
            "volumes": len(recs),
            "total_chapters": total_ch,
            "year_chapter_min": ymin,
            "year_chapter_max": ymax,
            "vol_spans": spans,
        }

    summary = {
        "generated": datetime.datetime.now().isoformat(),
        "volumes_total": len(results),
        "volumes_ok": sum(1 for r in results if r["ok"]),
        "volumes_failed": sum(1 for r in results if not r["ok"]),
        "volumes_no_text_layer": [r["label"] for r in results
                                  if r.get("no_text_layer")],
        "total_chapters": sum(r.get("chapter_count", 0) for r in results
                              if r["ok"]),
        "total_confident": sum(r.get("confident_count", 0) for r in results
                               if r["ok"]),
        "failures": [{"label": r["label"], "error": r["error"]}
                     for r in results if not r["ok"]],
        "per_year": year_report,
        "per_volume": [{k: r[k] for k in (
            "label", "year", "vol", "ok", "page_count", "chapter_count",
            "confident_count", "chapter_min", "chapter_max", "has_text_layer",
            "out", "secs") if k in r} for r in results],
    }
    summary_path = Path(args.out) / "born_digital_summary.json"
    Path(args.out).mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("\n=== SUMMARY ===", flush=True)
    print("volumes ok/total : %d/%d  failed=%d" % (
        summary["volumes_ok"], summary["volumes_total"],
        summary["volumes_failed"]), flush=True)
    print("total chapters   : %d  (confident %d)" % (
        summary["total_chapters"], summary["total_confident"]), flush=True)
    if summary["volumes_no_text_layer"]:
        print("NO TEXT LAYER (born-digital assumption FAILED): %s" % (
            ", ".join(summary["volumes_no_text_layer"])), flush=True)
    print("summary -> %s" % summary_path, flush=True)


if __name__ == "__main__":
    main()
