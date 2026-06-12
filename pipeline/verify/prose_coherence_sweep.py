#!/usr/bin/env python3
"""
prose_coherence_sweep.py
------------------------
Overnight graded prose-coherence scan of pre-1930 California statute acts.

Reads parsed_acts_fixed.json for each pre-1930 volume, sends each act's text
to the local Ollama model (gemma3:27b) with a graded 1-5 coherence prompt,
and appends results to a JSONL output file. Fully resumable: already-scored
acts are skipped on restart.

USAGE
  python pipeline/prose_coherence_sweep.py [--dry-run] [--smoke N]

OPTIONS
  --dry-run    Enumerate acts and log volume stats, but do NOT call Ollama.
  --smoke N    Run only the first N acts then stop (used for smoke testing).

OUTPUT
  C:\\Users\\PatrickKolasinski\\PatoLex-scratch\\_coherence\\prose_coherence_sweep.jsonl
    One JSON object per line:
      {"label": "1850", "act_index": 0, "chapter": "2",
       "score": 4, "reason": "Mostly clear, minor OCR imperfections.", "elapsed_s": 0.97}

RUN LOG
  docs/80_PROJECT_HISTORY/run-logs/prose-coherence-sweep-run.log
    Progress line every 200 acts.

SCHEDULE
  Intended to run via Windows Task Scheduler: 2026-06-10 22:30 local time.
  Task name: PatolexProseCoherence
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://100.70.54.56:11434"   # 5090 Ollama over Tailscale
MODEL = "gemma3:27b"

SCRATCH_BASE = Path(config.path_for("data_root"))
OUTPUT_FILE = SCRATCH_BASE / "_coherence" / "prose_coherence_sweep.jsonl"
RUN_LOG = (
    Path(__file__).parent.parent
    / "docs" / "80_PROJECT_HISTORY" / "run-logs"
    / "prose-coherence-sweep-run.log"
)

# Pre-1930 volume labels (in rough chronological order)
PRE_1930_LABELS = [
    "1850", "1851", "1852", "1853", "1854", "1855", "1856", "1857", "1858",
    "1859", "1860", "1861", "1862", "1863", "1863-64", "1865-66", "1867-68",
    "1869-70", "1871-72", "1873-74", "1875-76", "1877-78", "1881",
    "1883-84", "1883-84-regular", "1885-86", "1887", "1889", "1891", "1893",
    "1895", "1897", "1899", "1900-01", "1903", "1905", "1906-07", "1907-09",
    "1910-11", "1913-statutes", "1915-vol1-chapters", "1917-vol1-chapters",
    "1919-vol1-chapters", "1921-vol1-chapters", "1923-vol1-chapters",
    "1925-vol1-chapters", "1927-vol1-26chapters", "1927-vol1-chapters",
    "1929-vol1-28chapters", "1929-vol1-29chapters",
]

# These 8 non-statute volumes are skipped (code compilations, not session laws)
SKIP_LABELS = {
    "1873-74-code", "1875-76-code", "1877-78-code", "1880-code",
    "1965-vol1-64chapters", "1971-vol3-chapters",
    "1987-vol4-chapters", "1988-vol4-chapters",
}

GRADED_PROMPT = """\
Below is OCR-extracted text from a 19th/early-20th-century California statute. \
Rate the PROSE coherence 1-5: 5 = clean and fully readable; \
4 = light OCR noise, meaning fully clear; \
3 = noticeable noise but meaning recoverable; \
2 = heavy corruption, meaning partly lost; \
1 = prose so corrupted the meaning is largely lost. \
IGNORE corrupted chapter/section NUMBERS (handled separately). \
Reply with ONLY a single digit 1-5, then a 6-word reason.

TEXT:
{text}"""

# Truncate act text at this length before sending (keeps prompt manageable)
TEXT_MAX_CHARS = 1500

# Progress log interval
LOG_EVERY_N = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M PT")


def _log(msg: str, status: str = "OK") -> None:
    """Append a line to the run log."""
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = f"[{_now_str()}] prose-coherence-sweep | {msg} | {status}\n"
        with RUN_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[WARN] run-log write failed: {e}", file=sys.stderr)


def _load_done_set(output_path: Path) -> set:
    """Return set of (label, act_index) already present in the output file."""
    done = set()
    if not output_path.exists():
        return done
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done.add((rec["label"], rec["act_index"]))
            except Exception:
                pass
    return done


def _score_act(label: str, act_index: int, chapter: str, text: str,
               dry_run: bool = False) -> Optional[dict]:
    """
    Call Ollama with the graded prompt. Returns a result dict or None on error.
    In dry_run mode returns a stub without calling the API.
    """
    truncated = text[:TEXT_MAX_CHARS]
    prompt = GRADED_PROMPT.format(text=truncated)

    if dry_run:
        return {"label": label, "act_index": act_index, "chapter": chapter,
                "score": 0, "reason": "DRY-RUN", "elapsed_s": 0.0}

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 50},
    }

    t0 = time.time()
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
        elapsed = time.time() - t0
    except Exception as e:
        print(f"  [WARN] Ollama request failed for {label}/act{act_index}: {e}",
              file=sys.stderr)
        return None

    if r.status_code != 200:
        print(f"  [WARN] Ollama HTTP {r.status_code} for {label}/act{act_index}",
              file=sys.stderr)
        return None

    resp_text = r.json().get("response", "").strip()

    # Parse: first char should be 1-5, rest is the reason
    m = re.match(r'^([1-5])\s*(.*)', resp_text, re.DOTALL)
    if not m:
        print(f"  [WARN] Unparseable response for {label}/act{act_index}: {repr(resp_text[:80])}",
              file=sys.stderr)
        return None

    score = int(m.group(1))
    reason = m.group(2).strip().split("\n")[0].strip()  # first line only

    return {
        "label": label,
        "act_index": act_index,
        "chapter": chapter,
        "score": score,
        "reason": reason,
        "elapsed_s": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def _enumerate_acts():
    """Yield (label, act_index, chapter, text) for all pre-1930 statute acts."""
    for label in PRE_1930_LABELS:
        if label in SKIP_LABELS:
            continue
        path = SCRATCH_BASE / f"production-{label}" / "parsed_acts_fixed.json"
        if not path.exists():
            print(f"[WARN] Missing: {path}", file=sys.stderr)
            continue
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        acts = data.get("confident_acts", [])
        for idx, act in enumerate(acts):
            yield label, idx, str(act.get("chapter", "")), act.get("text", "")


def _summarize(output_path: Path) -> None:
    """Print and log a per-volume score summary from the output file."""
    if not output_path.exists():
        print("No output file to summarize.", file=sys.stderr)
        return

    from collections import defaultdict
    vol_scores: dict = defaultdict(list)
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("score", 0) > 0:
                    vol_scores[rec["label"]].append(rec["score"])
            except Exception:
                pass

    print("\n=== Per-Volume Score Summary ===")
    _log("=== Per-Volume Score Summary ===", "OK")
    for label in PRE_1930_LABELS:
        if label in SKIP_LABELS:
            continue
        scores = vol_scores.get(label, [])
        if not scores:
            print(f"  {label}: no data")
            continue
        avg = sum(scores) / len(scores)
        dist = {i: scores.count(i) for i in range(1, 6)}
        dist_str = " ".join(f"{k}:{v}" for k, v in sorted(dist.items()) if v)
        line = f"  {label}: n={len(scores)} avg={avg:.2f} [{dist_str}]"
        print(line)
        _log(line, "OK")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    smoke_n: Optional[int] = None
    if "--smoke" in sys.argv:
        idx = sys.argv.index("--smoke")
        smoke_n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 10

    mode_label = "DRY-RUN" if dry_run else ("SMOKE" if smoke_n else "FULL")
    _log(f"Sweep started [{mode_label}] model={MODEL} ollama={OLLAMA_URL}", "OK")
    print(f"[{_now_str()}] prose-coherence-sweep START [{mode_label}] "
          f"model={MODEL} ollama={OLLAMA_URL}")

    if not dry_run:
        # Verify Ollama reachable
        try:
            check = requests.get(f"{OLLAMA_URL}/api/tags", timeout=15)
            if check.status_code != 200:
                _log("Ollama unreachable", "FAIL")
                print("[FAIL] Ollama not reachable at", OLLAMA_URL, file=sys.stderr)
                sys.exit(1)
            # Confirm model present
            model_names = [m["name"] for m in check.json().get("models", [])]
            if MODEL not in model_names:
                _log(f"Model {MODEL} not found on Ollama", "FAIL")
                print(f"[FAIL] Model {MODEL} not found. Available: {model_names}",
                      file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            _log(f"Ollama connectivity check failed: {e}", "FAIL")
            print(f"[FAIL] Ollama connectivity error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Ollama reachable, model {MODEL} confirmed present.")

    # Load already-done set for resumability
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    done_set = _load_done_set(OUTPUT_FILE)
    print(f"Resuming: {len(done_set)} acts already scored.")

    total_done = 0
    total_errors = 0
    t_run_start = time.time()
    recent_times: list = []

    with OUTPUT_FILE.open("a", encoding="utf-8") as out_f:
        for label, act_index, chapter, text in _enumerate_acts():
            key = (label, act_index)
            if key in done_set:
                continue

            result = _score_act(label, act_index, chapter, text, dry_run=dry_run)

            if result is None:
                total_errors += 1
                continue

            # Write result immediately (append to JSONL)
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            out_f.flush()
            done_set.add(key)
            total_done += 1

            if not dry_run:
                recent_times.append(result["elapsed_s"])
                if len(recent_times) > 50:
                    recent_times.pop(0)

            # Progress log every LOG_EVERY_N acts
            if total_done % LOG_EVERY_N == 0:
                elapsed_total = time.time() - t_run_start
                rate = (sum(recent_times) / len(recent_times)) if recent_times else 0
                msg = (f"Progress: {total_done} acts done, {total_errors} errors, "
                       f"rate={rate:.2f}s/act, elapsed={elapsed_total/60:.1f}min")
                _log(msg, "OK")
                print(f"[{_now_str()}] {msg}")

            # Stop early if smoke mode
            if smoke_n is not None and total_done >= smoke_n:
                _log(f"Smoke test complete: {total_done} acts done", "OK")
                break

    elapsed_total = time.time() - t_run_start
    _log(f"Sweep complete: {total_done} acts scored, {total_errors} errors, "
         f"wall={elapsed_total/3600:.2f}h", "OK")
    print(f"\n[{_now_str()}] DONE: {total_done} acts scored, "
          f"{total_errors} errors, wall={elapsed_total/3600:.2f}h")

    if not dry_run:
        _summarize(OUTPUT_FILE)


if __name__ == "__main__":
    main()
