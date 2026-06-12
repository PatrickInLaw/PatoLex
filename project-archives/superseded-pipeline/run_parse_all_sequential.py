"""
run_parse_all.py -- Drive parse_volume() across all 1850-1999 in-scope volumes.
================================================================================
Calls parse_volume() from ingest_from_ocr.py directly (bypassing the __main__
LEGISLATURE_MAP gate, which guards ingest_volume -- not needed for parse-only).
Writes parsed_acts_fixed.json per volume.  Does NOT call ingest_volume; no DB
writes of any kind.

Skip list (non-statute volumes -- resolutions, digests, code compilations):
  - *-code dirs (Civil Code compilations, not session statutes)
  - 1965-vol1-64chapters  (1964 Concurrent/Joint Resolutions)
  - 1971-vol3-chapters    (1971 Concurrent Resolutions)
  - 1987-vol4-chapters    (1987 digest volume)
  - 1988-vol4-chapters    (1988 digest volume)

Memory guard: checks available RAM between volumes; pauses and exits if free
RAM drops below RAM_FLOOR_MB.

Usage:
    python run_parse_all.py

2026-06-09  cc007  Initial version.
"""

import sys
import os
import datetime
import ctypes
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(r"C:\Users\PatrickKolasinski\Documents\GitHub\patolex")
PIPELINE_DIR = REPO / "pipeline" / "5080"
SCRATCH_ROOT = Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch")
LOG_FILE = REPO / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "parse-all-run.log"

# Memory floor: pause/exit if free RAM drops below this (MB)
RAM_FLOOR_MB = 1024

# ---------------------------------------------------------------------------
# Non-statute volumes to skip (parse would produce junk)
# ---------------------------------------------------------------------------
SKIP_LABELS = {
    "1873-74-code",        # Civil Code compilation
    "1875-76-code",        # Civil Code compilation
    "1877-78-code",        # Code compilation
    "1880-code",           # Code compilation
    "1965-vol1-64chapters",  # 1964 Concurrent/Joint Resolutions only
    "1971-vol3-chapters",  # 1971 Concurrent Resolutions only
    "1987-vol4-chapters",  # Digest volume (bill summaries, not statute text)
    "1988-vol4-chapters",  # Digest volume (bill summaries, not statute text)
    # Smoke/test dirs -- not production volumes
    "smoke-1996-vol2",
    "smoke-real-1997-vol1",
    "smoke-real-1998-vol1",
}

# Also skip dirs with Underscore-cap labels (2000_Vol* etc.) -- those are 2000+
# and already parsed; handled by the year filter below.


def log_run(phase, description, status="OK"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")
    entry = "[" + ts + "] " + phase + " | " + description + " | " + status + "\n"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(str(LOG_FILE), "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip(), flush=True)


def free_ram_mb():
    """Return available physical RAM in MB (Windows GlobalMemoryStatusEx)."""
    try:
        class MEMSTATUS(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        ms = MEMSTATUS()
        ms.dwLength = ctypes.sizeof(ms)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.ullAvailPhys // (1024 * 1024)
    except Exception:
        return 9999  # unknown -- proceed


def collect_in_scope_labels():
    """
    Return sorted list of session labels to parse, from production-* dirs
    that have ocr_consensus/page_ocr_results.json, are in the 1850-1999 range
    (by leading 4-digit year), and are not in SKIP_LABELS.
    Caps pattern dirs (e.g. 1997_Vol1) are excluded by year filter.
    """
    labels = []
    for d in sorted(SCRATCH_ROOT.iterdir()):
        if not d.is_dir():
            continue
        if not d.name.startswith("production-"):
            continue
        label = d.name[len("production-"):]
        # Skip explicitly
        if label in SKIP_LABELS:
            continue
        # Must start with a 4-digit year 1850-1999
        import re
        m = re.match(r'^(\d{4})', label)
        if not m:
            continue
        yr = int(m.group(1))
        if yr < 1850 or yr > 1999:
            continue
        # Must have OCR consensus
        ocr_path = d / "ocr_consensus" / "page_ocr_results.json"
        if not ocr_path.exists():
            continue
        labels.append(label)
    return labels


def main():
    # Import parse_volume from ingest_from_ocr (parse-only, no ingest)
    sys.path.insert(0, str(PIPELINE_DIR))
    from ingest_from_ocr import parse_volume  # noqa: E402

    labels = collect_in_scope_labels()
    log_run("PARSE-ALL", "=== run_parse_all.py start: " + str(len(labels)) + " volumes ===", "OK")

    total_confident = 0
    total_flagged = 0
    parsed_ok = []
    parse_fail = []
    parse_skip_ram = []

    for i, label in enumerate(labels):
        ram = free_ram_mb()
        if ram < RAM_FLOOR_MB:
            msg = ("RAM low: " + str(ram) + " MB free < " + str(RAM_FLOOR_MB)
                   + " MB floor -- pausing after " + str(i) + " volumes")
            log_run("PARSE-ALL", msg, "WARN")
            parse_skip_ram = labels[i:]
            break

        out_path = SCRATCH_ROOT / ("production-" + label) / "parsed_acts_fixed.json"
        already = out_path.exists()
        log_run("PARSE-ALL", label + " [" + str(i + 1) + "/" + str(len(labels)) + "]"
                + (" (REPARSE -- overwriting existing)" if already else "")
                + " | RAM=" + str(ram) + " MB", "OK")

        try:
            result = parse_volume(label)
            if result is None:
                log_run("PARSE-ALL", label + ": parse_volume returned None (OCR missing or label error)", "FAIL")
                parse_fail.append((label, "parse_volume returned None"))
            else:
                c = len(result["confident"])
                f = len(result["flagged"])
                total_confident += c
                total_flagged += f
                parsed_ok.append((label, c, f))
                log_run("PARSE-ALL", label + ": confident=" + str(c) + " flagged=" + str(f), "OK")
        except Exception as e:
            log_run("PARSE-ALL", label + ": EXCEPTION: " + str(e)[:200], "FAIL")
            parse_fail.append((label, str(e)[:200]))

    # Summary
    log_run("PARSE-ALL", "=== DONE: parsed_ok=" + str(len(parsed_ok))
            + " fail=" + str(len(parse_fail))
            + " skipped_ram=" + str(len(parse_skip_ram))
            + " total_confident=" + str(total_confident)
            + " total_flagged=" + str(total_flagged)
            + " | final_ram=" + str(free_ram_mb()) + " MB ===", "OK")

    if parse_fail:
        log_run("PARSE-ALL", "FAILED volumes: " + str([l for l, _ in parse_fail]), "WARN")
    if parse_skip_ram:
        log_run("PARSE-ALL", "RAM-skipped volumes: " + str(parse_skip_ram), "WARN")

    print("\n=== SUMMARY ===")
    print("Volumes parsed OK:   ", len(parsed_ok))
    print("Volumes failed:      ", len(parse_fail))
    print("Volumes RAM-skipped: ", len(parse_skip_ram))
    print("Total confident acts:", total_confident)
    print("Total flagged acts:  ", total_flagged)
    print("Final free RAM (MB): ", free_ram_mb())
    if parse_fail:
        print("\nFailed volumes:")
        for lbl, err in parse_fail:
            print("  ", lbl, ":", err)
    if parse_skip_ram:
        print("\nRAM-skipped (resume from here):", parse_skip_ram[0])


if __name__ == "__main__":
    main()
