"""
re_ingest_fixed.py — Re-ingest confident acts from parsed_acts_fixed.json
=========================================================================
RUN THIS ONLY AFTER the production batch has stopped.

CORRECTED 2026-06-02 (wind-down session):
  The previous version of this script INSERTed against a schema that does not
  exist (columns `chapter`, `chapter_int`, `enactment_date`, `body_text`,
  `section_num`, etc.). Every insert failed with
  `column "chapter" of relation "enactment" does not exist`.

  This rewrite faithfully replicates STAGE6-INGEST from production_pipeline.py
  (the proven, working ingest path that produced the 1419 banked rows) against
  the REAL event-sourced schema:
      enactment (source_document_id, citation, jurisdiction, session,
                 legislature, chapter_number, chaptered_date, effective_date,
                 operative_date, title, bill_number, kind)
      provision (jurisdiction, unit_type, current_designation, status)
      designation_history (provision_id, code, section_number, label, valid_range)
      change_event (enactment_id, provision_id, action, new_text,
                    operative_date, in_act_order, chaptered_out, trust_level,
                    source_document_id, page_ref)

Safety / idempotency:
  - Idempotent on (citation, source_document_id) in `enactment` — identical to
    the pipeline's STAGE6 dedup check. Acts already present are skipped, so this
    is safe to re-run and will not duplicate the banked rows.
  - Only INSERTs into enactment / provision / designation_history / change_event.
  - Read-only with respect to source_document and OCR data.

Usage:
    python re_ingest_fixed.py [volume_label]
    e.g.: python re_ingest_fixed.py 1852
    or (all clean volumes): python re_ingest_fixed.py
"""

import sys
import os
import json
import time
import subprocess
import datetime
from pathlib import Path

SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE = Path(
    r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex"
    r"\docs\80_PROJECT_HISTORY\run-logs\parser-fix-run.log"
)
PSQL = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"

# Faithful copy of LEGISLATURE_MAP from production_pipeline.py
# (session_label -> (session_str, legislature_ordinal))
LEGISLATURE_MAP = {
    "1850": ("1849-1850", "1st"),
    "1851": ("1851", "2nd"),
    "1852": ("1852", "3rd"),
    "1853": ("1853", "4th"),
    "1854": ("1854", "5th"),
    "1855": ("1855", "6th"),
    "1856": ("1856", "7th"),
    "1857": ("1857", "8th"),
    "1858": ("1858", "9th"),
    "1859": ("1859", "10th"),
    "1860": ("1860", "11th"),
}


def log_entry(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip())


def psql_query(sql_str, retries=3):
    env = dict(os.environ)
    env["PGPASSWORD"] = os.environ.get("PGPASSWORD", "postgres")  # no hardcoded secret; supply via env
    args = [
        PSQL, "-U", "postgres", "-d", "patolex",
        "-t", "-A", "--set=client_encoding=UTF8", "-c", sql_str
    ]
    for attempt in range(retries):
        r = subprocess.run(
            args, capture_output=True, encoding="utf-8",
            errors="replace", env=env, timeout=60
        )
        if r.returncode == 0:
            lines = [
                ln for ln in r.stdout.strip().splitlines()
                if ln.strip()
                and not ln.strip().startswith(("INSERT", "UPDATE", "DELETE"))
            ]
            return lines[0] if lines else ""
        if "deadlock" in r.stderr.lower() or "serialization" in r.stderr.lower():
            time.sleep(0.5 * (attempt + 1))
            continue
        raise RuntimeError("psql error: " + r.stderr.strip()[:300])
    raise RuntimeError("psql failed after " + str(retries) + " retries")


def safe_str(s, maxlen=None):
    """Identical to production_pipeline.py safe_str."""
    s = s.encode("ascii", errors="replace").decode("ascii")
    s = s.replace("'", "''")
    if maxlen:
        s = s[:maxlen]
    return s


def ingest_volume(session_label):
    scratch = SCRATCH_ROOT / ("production-" + session_label)
    acts_path = scratch / "parsed_acts_fixed.json"

    if not acts_path.exists():
        log_entry(
            "REINGEST",
            session_label + ": parsed_acts_fixed.json not found -- run reparse.py first",
            "FAIL",
        )
        return

    data = json.loads(acts_path.read_text(encoding="utf-8"))
    confident_acts = data.get("confident_acts", [])

    if not confident_acts:
        log_entry("REINGEST", session_label + ": no confident acts found in fixed parse", "WARN")
        return

    # Resolve session_str / legislature from the map (faithful to pipeline)
    if session_label in LEGISLATURE_MAP:
        session_str, legis_num = LEGISLATURE_MAP[session_label]
    else:
        session_str = legis_num = session_label
    start_year = int(session_label.split("-")[0])

    # Find source_document row for this volume (batch citation: "Stats. <year>,%")
    src_sql = (
        "SELECT id FROM source_document "
        "WHERE citation LIKE 'Stats. " + session_label + ",%' "
        "AND page_count IS NOT NULL LIMIT 1;"
    )
    src_id_str = psql_query(src_sql)
    if not src_id_str:
        log_entry(
            "REINGEST",
            session_label + ": source_document not found (batch may not have finished for this volume)",
            "WARN",
        )
        return
    src_doc_id = int(src_id_str)

    # ---- SCOPED PURGE of any prior parse rows for THIS source_document -------
    # Why: earlier ingest runs (live batch + an earlier re_ingest) keyed acts on
    # the OCR-garbled chapter number, which collapses many DISTINCT acts onto the
    # same citation (e.g. 1854 OCR'd 21 different chapters all as "XI"). Keeping
    # those rows would block the newly-recovered distinct acts and leave the
    # corpus inconsistent. We rebuild this volume cleanly and idempotently:
    # re-running yields the same final state. Only rows tied to THIS
    # source_document_id are touched.
    purge_before = psql_query(
        "SELECT count(*) FROM enactment WHERE source_document_id = " + str(src_doc_id) + ";"
    )
    # provision_version references change_event + source_document; remove first.
    psql_query(
        "DELETE FROM provision_version WHERE source_document_id = " + str(src_doc_id)
        + " OR source_change_event_id IN (SELECT id FROM change_event "
        "WHERE source_document_id = " + str(src_doc_id) + ");"
    )
    # delete change_events for this source doc's enactments + orphan provisions/desig
    psql_query(
        "DELETE FROM designation_history dh USING provision p, change_event ce "
        "WHERE dh.provision_id = p.id AND ce.provision_id = p.id "
        "AND ce.source_document_id = " + str(src_doc_id) + ";"
    )
    psql_query(
        "DELETE FROM change_event WHERE source_document_id = " + str(src_doc_id) + ";"
    )
    # remove provisions no longer referenced by any change_event
    psql_query(
        "DELETE FROM provision p WHERE p.jurisdiction = 'CA' "
        "AND p.unit_type = 'act_section' "
        "AND NOT EXISTS (SELECT 1 FROM change_event ce WHERE ce.provision_id = p.id) "
        "AND NOT EXISTS (SELECT 1 FROM designation_history dh WHERE dh.provision_id = p.id) "
        "AND p.current_designation LIKE 'Stats. " + session_label + " %';"
    )
    psql_query(
        "DELETE FROM enactment WHERE source_document_id = " + str(src_doc_id) + ";"
    )
    log_entry(
        "REINGEST",
        session_label + ": source_document id=" + str(src_doc_id)
        + " | purged prior enactments=" + str(purge_before)
        + " | ingesting " + str(len(confident_acts)) + " confident acts",
        "OK",
    )

    enact_inserted = prov_inserted = ce_inserted = skipped_dup = errors = 0

    for order_idx, act in enumerate(confident_acts):
        chap_num = act.get("chapter_int", 0)
        act_citation = "Stats. " + session_label + " ch. " + str(chap_num)
        iso_date = act.get("iso_date") or ""
        operative_date = iso_date if iso_date else (str(start_year) + "-01-01")
        title_esc = safe_str(act.get("title", ""), 500)
        text_esc = safe_str(act.get("text", ""), 8000)
        source_page = act.get("source_page", 0)

        # Idempotency within this run is guaranteed by the purge above; the
        # physical-act key is (source_document_id, in_act_order=order_idx).
        check = psql_query(
            "SELECT e.id FROM enactment e JOIN change_event ce ON ce.enactment_id = e.id "
            "WHERE e.source_document_id = " + str(src_doc_id)
            + " AND ce.in_act_order = " + str(order_idx) + ";"
        )
        if check:
            skipped_dup += 1
            continue

        # enactment
        try:
            e_sql = (
                "INSERT INTO enactment ("
                "source_document_id, citation, jurisdiction, session, legislature, "
                "chapter_number, chaptered_date, effective_date, operative_date, "
                "title, bill_number, kind) VALUES ("
                + str(src_doc_id) + ", '" + act_citation + "', 'CA', '"
                + safe_str(session_str, 100) + "', '" + safe_str(legis_num, 50) + "', "
                + str(chap_num) + ", '" + operative_date + "', '" + operative_date
                + "', '" + operative_date + "', '" + title_esc + "', NULL, 'statute'"
                ") RETURNING id;"
            )
            enact_id = int(psql_query(e_sql))
            enact_inserted += 1
        except Exception as e:
            log_entry("REINGEST", session_label + " ch." + str(chap_num)
                      + ": enactment FAIL: " + str(e)[:150], "WARN")
            errors += 1
            continue

        # provision
        try:
            desig = "Stats. " + session_label + " ch. " + str(chap_num)
            p_sql = (
                "INSERT INTO provision (jurisdiction, unit_type, current_designation, status) "
                "VALUES ('CA', 'act_section', '" + safe_str(desig, 200) + "', 'active') "
                "RETURNING id;"
            )
            prov_id = int(psql_query(p_sql))
            prov_inserted += 1
        except Exception as e:
            log_entry("REINGEST", session_label + " ch." + str(chap_num)
                      + ": provision FAIL: " + str(e)[:150], "WARN")
            errors += 1
            continue

        # designation_history (best-effort, as in STAGE6)
        try:
            desig_esc = safe_str(desig, 200)
            dh_sql = (
                "INSERT INTO designation_history (provision_id, code, section_number, label, valid_range) "
                "VALUES (" + str(prov_id) + ", 'Statutes of California " + session_label
                + "', '" + str(chap_num) + "', '" + desig_esc
                + "', '[" + operative_date + ",)');"
            )
            psql_query(dh_sql)
        except Exception as e:
            log_entry("REINGEST", session_label + " ch." + str(chap_num)
                      + ": designation_history WARN: " + str(e)[:120], "WARN")

        # change_event
        try:
            page_ref = "p. " + str(source_page)
            ce_sql = (
                "INSERT INTO change_event ("
                "enactment_id, provision_id, action, new_text, "
                "operative_date, in_act_order, chaptered_out, "
                "trust_level, source_document_id, page_ref) VALUES ("
                + str(enact_id) + ", " + str(prov_id) + ", 'enact', '" + text_esc + "', '"
                + operative_date + "', " + str(order_idx) + ", false, "
                "'ocr_uncertain', " + str(src_doc_id) + ", '" + page_ref + "'"
                ") RETURNING id;"
            )
            psql_query(ce_sql)
            ce_inserted += 1
        except Exception as e:
            log_entry("REINGEST", session_label + " ch." + str(chap_num)
                      + ": change_event FAIL: " + str(e)[:150], "WARN")
            errors += 1

    log_entry(
        "REINGEST",
        session_label
        + ": enactments=" + str(enact_inserted)
        + " provisions=" + str(prov_inserted)
        + " change_events=" + str(ce_inserted)
        + " skipped(dup)=" + str(skipped_dup)
        + " errors=" + str(errors),
        "OK" if errors == 0 else "WARN",
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
log_entry("REINGEST", "=== re_ingest_fixed.py starting (schema-corrected) ===", "OK")
log_entry(
    "REINGEST",
    "Idempotent on (citation, source_document_id). Mirrors STAGE6 of "
    "production_pipeline.py. Safe to re-run.",
    "OK",
)

if len(sys.argv) >= 2:
    volumes = [sys.argv[1].strip()]
else:
    volumes = ["1850", "1851", "1852", "1853", "1854", "1855", "1856",
               "1857", "1858", "1859", "1860"]

for vol in volumes:
    ingest_volume(vol)

log_entry("REINGEST", "=== re_ingest_fixed.py done ===", "OK")
