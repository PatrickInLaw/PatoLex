"""
substitution_judge_local.py -- Path 2 step 2: estimate the real-word->real-word
substitution rate by having a local model (gemma3:27b via Ollama) flag, in each
sampled window, words that are VALID English but WRONG in context (OCR substituted
a similar-looking different word). This is the class vocab-diff cannot see.

Reads _vocab/substitution_sample.jsonl; writes _vocab/substitution_findings_local.json
+ a rate summary. Free (5090 GPU). Heartbeat run log.
"""
import os, sys, re, json, time, urllib.request
from datetime import datetime, timezone, timedelta
import config

OUT_DIR = config.path_for("vocab_dir")
SAMPLE  = os.path.join(OUT_DIR, "substitution_sample.jsonl")
OUT     = os.path.join(OUT_DIR, "substitution_findings_local.json")
LOG     = os.path.join(OUT_DIR, "substitution-judge-run.log")
OLLAMA  = "http://127.0.0.1:11434/api/chat"
MODEL   = os.environ.get("SUB_MODEL", "gemma3:27b")

PROMPT = (
    "You are reviewing OCR'd text from California statutes (1850s-1990s). You are hunting "
    "for ONE specific subtle error: a word that is a VALID English word but is WRONG in "
    "context because OCR mis-scanned it from a similar-looking different word "
    "(e.g. State->Slate, fight->light, shall->shell, public->publie is NOT this because "
    "publie is not a word; a wrong digit in a number also counts).\n"
    "Rules:\n"
    "- Flag ONLY valid-word-but-wrong-in-context substitutions.\n"
    "- Do NOT flag archaic/legal terms, proper names, garbage/misspelled non-words, or "
    "merely unusual-but-correct phrasing. If unsure, do NOT flag.\n"
    'Return ONLY JSON: {"subs":[{"word":"...","correction":"...","why":"..."}]} '
    "(empty list if none).\n\nPASSAGE:\n"
)

def rlog(msg, status="OK"):
    z = timezone(timedelta(hours=-7))
    line = f"[{datetime.now(timezone.utc).astimezone(z):%Y-%m-%d %H:%M PT}] {msg} | {status}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.rstrip()); sys.stdout.flush()

def call(text):
    body = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT + text}],
            "stream": False, "options": {"temperature": 0}, "think": False}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "")

def extract(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0)).get("subs", [])
    except Exception:
        return []

def main():
    rlog(f"START substitution judge model={MODEL}")
    rows = [json.loads(l) for l in open(SAMPLE, encoding="utf-8") if l.strip()]
    rlog(f"loaded {len(rows)} sample windows")
    findings = []
    total_words = 0; total_subs = 0
    t0 = time.time(); last = time.time()
    for i, row in enumerate(rows):
        total_words += row["nwords"]
        subs = []
        for attempt in range(2):
            try:
                subs = extract(call(row["text"]))
                break
            except Exception as e:
                if attempt == 1:
                    rlog(f"window {row['id']} failed: {e}", "WARN")
        total_subs += len(subs)
        if subs:
            findings.append({"id": row["id"], "vol": row["vol"], "era": row["era"],
                             "page": row["page"], "subs": subs, "text": row["text"]})
        now = time.time()
        if now - last >= 15 or i + 1 == len(rows):
            rate = (i + 1) / max(now - t0, 0.001)
            rlog(f"{i+1}/{len(rows)} windows | subs_so_far={total_subs} | words={total_words:,} | "
                 f"elapsed={now-t0:.0f}s | rate={rate:.1f}/s", "HEARTBEAT")
            last = now

    json.dump({"n_windows": len(rows), "total_words": total_words,
               "total_subs": total_subs, "findings": findings},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    per1k = 1000.0 * total_subs / max(total_words, 1)
    pct = 100.0 * total_subs / max(total_words, 1)
    rlog(f"DONE subs={total_subs} over {total_words:,} words = {per1k:.2f}/1000 words ({pct:.3f}%) "
         f"| windows_with_subs={len(findings)}/{len(rows)} | -> {OUT}")

if __name__ == "__main__":
    main()
