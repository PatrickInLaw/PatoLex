"""
review_adjudicate_local.py -- local-model adjudication of the Pass C review tier.

Reads _vocab/passC_review.tsv (the 2,655 tokens the deterministic scorer would NOT
confidently auto-correct) and asks a local Ollama model (gemma3:27b) to classify each:
  FIX     -> a misspelled real word; value = correction
  NAME    -> person/place proper name; value = best-guess name (or token)
  GARBAGE -> unrecoverable OCR noise; value = ""
  KEEP    -> actually a valid token as-is; value = token

Batches tokens per /api/chat call, temp 0, strict-JSON out. Heartbeat run log.
Writes _vocab/review_local_gemma3.json. CPU/GPU: uses the 5090 GPU via Ollama.
"""
import os, sys, re, json, time, urllib.request
from datetime import datetime, timezone, timedelta
import config

OUT_DIR  = config.path_for("vocab_dir")
TSV      = os.path.join(OUT_DIR, "passC_review.tsv")
OUT_JSON = os.path.join(OUT_DIR, "review_local_gemma3.json")
LOG_PATH = os.path.join(OUT_DIR, "review-adjudicate-run.log")
OLLAMA   = "http://127.0.0.1:11434/api/chat"
MODEL    = os.environ.get("ADJ_MODEL", "gemma3:27b")
BATCH    = int(os.environ.get("ADJ_BATCH", "25"))

def pt():
    try:
        z = timezone(timedelta(hours=-7))
        return datetime.now(timezone.utc).astimezone(z).strftime("%Y-%m-%d %H:%M PT")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

def rlog(phase, desc, status="OK"):
    line = f"[{pt()}] {phase} | {desc} | {status}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line); f.flush()
    print(line.rstrip()); sys.stdout.flush()

def parse_candidates(reason):
    # reason like ambiguous(right:50843/eight:27364) or weak_unique(lambda:0) or no_candidate
    cands = re.findall(r"([a-z]{2,})\s*:\s*\d+", reason or "")
    return cands

def load_rows():
    rows = []
    with open(TSV, encoding="utf-8") as f:
        next(f, None)  # header
        for ln in f:
            parts = ln.rstrip("\n").split("\t")
            if len(parts) >= 3:
                tok, fr, reason = parts[0], parts[1], parts[2]
                rows.append((tok, int(fr) if fr.isdigit() else 0, parse_candidates(reason)))
    return rows

PROMPT_HEAD = (
    "You correct OCR errors in California statute text (1850-2024). Each item is a "
    "garbled token a spell-checker could not confidently fix, with candidate guesses "
    "drawn from the corpus. For EACH item decide one verdict:\n"
    '  "FIX"     = misspelled real word -> value = the corrected word (lowercase)\n'
    '  "NAME"    = person or place proper name -> value = best-guess proper name (or the token)\n'
    '  "GARBAGE" = unrecoverable OCR noise -> value = ""\n'
    '  "KEEP"    = already a valid token -> value = the token\n'
    "Prefer a candidate when one is clearly right; otherwise use your own knowledge. "
    "Return ONLY a JSON array, one object per item, no prose:\n"
    '[{"n":1,"verdict":"FIX","value":"eight"}, ...]\n\nItems:\n'
)

def build_prompt(batch):
    lines = []
    for i, (tok, fr, cands) in enumerate(batch, 1):
        c = ("[" + ", ".join(cands) + "]") if cands else "[none]"
        lines.append(f'{i}. token="{tok}" candidates={c}')
    return PROMPT_HEAD + "\n".join(lines)

def call_model(prompt):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "stream": False, "options": {"temperature": 0}, "think": False}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("message", {}).get("content", "")

def extract_json(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def main():
    rlog("START", f"review adjudication model={MODEL} batch={BATCH}")
    rows = load_rows()
    total = len(rows)
    rlog("LOAD", f"{total} review tokens loaded from passC_review.tsv")
    results = {}
    t0 = time.time(); last = time.time(); done = 0
    for start in range(0, total, BATCH):
        batch = rows[start:start+BATCH]
        prompt = build_prompt(batch)
        verdicts = None
        for attempt in range(2):
            try:
                verdicts = extract_json(call_model(prompt))
                if verdicts:
                    break
            except Exception as e:
                if attempt == 1:
                    rlog("WARN", f"batch@{start} failed: {e}", "WARN")
        if verdicts:
            by_n = {int(v.get("n", -1)): v for v in verdicts if isinstance(v, dict)}
            for i, (tok, fr, cands) in enumerate(batch, 1):
                v = by_n.get(i, {})
                results[tok] = {"freq": fr, "candidates": cands,
                                "verdict": (v.get("verdict") or "ERR").upper(),
                                "value": v.get("value", "")}
        else:
            for (tok, fr, cands) in batch:
                results[tok] = {"freq": fr, "candidates": cands, "verdict": "ERR", "value": ""}
        done += len(batch)
        now = time.time()
        if now - last >= 15 or done >= total:
            rate = done / max(now - t0, 0.001)
            fixed = sum(1 for r in results.values() if r["verdict"] == "FIX")
            rlog("ADJ", f"{done}/{total} | FIX={fixed} | elapsed={now-t0:.0f}s | rate={rate:.1f}/s", "HEARTBEAT")
            last = now
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=0)
    tally = {}
    for r in results.values():
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    rlog("DONE", f"n={len(results)} tally={tally} out={OUT_JSON} wall={time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
