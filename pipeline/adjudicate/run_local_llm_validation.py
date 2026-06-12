"""
run_local_llm_validation.py
Runs a local Ollama model against the stratified validation sample and
computes agreement metrics vs the API (ground-truth) labels.

Usage:
    python run_local_llm_validation.py --model aya-expanse:8b
    python run_local_llm_validation.py --model "hf.co/bartowski/aya-expanse-32b-GGUF:Q4_K_M"
    python run_local_llm_validation.py --model gemma3:27b

Output:
    local_llm_results_<model_tag>.json   -- per-act results
    local_llm_metrics_<model_tag>.json   -- aggregated metrics
"""

import json
import time
import argparse
import pathlib
import urllib.request
import urllib.error
import re
import sys
import config

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
SAMPLE_PATH = pathlib.Path(config.path_for("data_root", "local_llm_validation_sample.json"))
OUT_DIR = pathlib.Path(config.path_for("data_root"))

# Few-shot system prompt with explicit garbage examples to prevent "noisy" collapse
SYSTEM_PROMPT = """You are a California legal text quality analyst for OCR validation.

TASK: Rate OCR-extracted text from historical California legislative acts (1850-1960).

DEFINITIONS:
- "clean": Minimal OCR noise, clearly readable California statutory English.
- "noisy_but_coherent": Has OCR errors (garbled words, stray characters, line artifacts) but legal meaning and structure are still legible. A researcher could understand what the law says.
- "garbage": Legal meaning is LOST due to OCR failure. The text is unrecoverable — mostly random or substituted characters, acts spliced together, or so corrupted that a researcher cannot determine what statute this was.

IMPORTANT: "garbage" is rare (~2%). Most OCR-degraded acts are noisy_but_coherent. Only call garbage when meaning is genuinely unrecoverable.

EXAMPLES OF GARBAGE (meaning completely lost):
- "Chap 8. J J J. Aooovod Mazo J5, J876. dv vo do J 1 thc act." — no recoverable meaning
- "§1. Tho oomm jiseal az. §2. Ths. Approvdd." — garbled beyond recovery

EXAMPLES OF NOISY_BUT_COHERENT (meaning recoverable despite noise):
- "inceurporated acesding to teh provesions of this act" — noisy but readable
- "Tho Poeple of teh State of California do enact: Any person who violtes this secton shal be fined" — clear meaning despite errors

Reply with ONLY one word: clean, noisy_but_coherent, or garbage. Nothing else."""


def truncate_text(text, max_chars=2500):
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...truncated]"


def call_ollama_chat(model: str, text: str, num_predict: int = 15, timeout: int = 180) -> tuple[str, float]:
    """Use /api/chat endpoint."""
    user_content = f"Rate: {truncate_text(text)}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": num_predict,
            "top_k": 1,
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        msg = body.get("message", {})
        content = msg.get("content", "").strip().lower() if isinstance(msg, dict) else ""
        # Also check thinking field for models that put answer there
        if not content:
            thinking = msg.get("thinking", "") if isinstance(msg, dict) else ""
            # If thinking models consumed all tokens, bump num_predict
            if thinking:
                return f"thinking_overflow:{thinking[:50]}", elapsed
        return content, elapsed
    except urllib.error.URLError as e:
        elapsed = time.time() - t0
        return f"error:{e}", elapsed


def parse_rating(raw: str) -> str:
    raw = raw.strip().lower()
    if raw.startswith("error") or raw.startswith("thinking_overflow"):
        return "error"
    if raw in ("clean", "noisy_but_coherent", "garbage"):
        return raw
    if "garbage" in raw:
        return "garbage"
    if "noisy" in raw or "coherent" in raw:
        return "noisy_but_coherent"
    if "clean" in raw:
        return "clean"
    return "unknown"


def compute_metrics(results: list[dict]) -> dict:
    valid = [r for r in results if r["local_rating"] not in ("error", "unknown")]
    if not valid:
        return {
            "n_valid": 0,
            "n_errors": len(results),
            "error": "no valid results",
        }

    total = len(valid)
    exact_match = sum(1 for r in valid if r["local_rating"] == r["api_rating"])
    overall_agreement = exact_match / total

    true_garbage = [r for r in valid if r["api_rating"] == "garbage"]
    tp = sum(1 for r in true_garbage if r["local_rating"] == "garbage")
    fn = len(true_garbage) - tp

    pred_garbage = [r for r in valid if r["local_rating"] == "garbage"]
    fp = sum(1 for r in pred_garbage if r["api_rating"] != "garbage")

    recall = tp / len(true_garbage) if true_garbage else 0.0
    precision = tp / len(pred_garbage) if pred_garbage else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    classes = ["clean", "noisy_but_coherent", "garbage"]
    conf = {}
    for true_cls in classes:
        for pred_cls in classes:
            n = sum(1 for r in valid if r["api_rating"] == true_cls and r["local_rating"] == pred_cls)
            conf[f"{true_cls}->{pred_cls}"] = n

    elapsed_times = [r["elapsed_sec"] for r in valid]
    avg_sec = sum(elapsed_times) / len(elapsed_times)
    total_elapsed = sum(elapsed_times)
    total_corpus = 75340
    sweep_hours = (total_corpus * avg_sec) / 3600

    errors = [r for r in results if r["local_rating"] in ("error", "unknown")]

    return {
        "n_valid": total,
        "n_errors": len(errors),
        "n_garbage_true": len(true_garbage),
        "overall_3way_agreement": round(overall_agreement, 4),
        "garbage_recall": round(recall, 4),
        "garbage_precision": round(precision, 4),
        "garbage_f1": round(f1, 4),
        "garbage_tp": tp,
        "garbage_fp": fp,
        "garbage_fn": fn,
        "garbage_pred_total": len(pred_garbage),
        "confusion_matrix": conf,
        "avg_sec_per_act": round(avg_sec, 3),
        "total_elapsed_sec": round(total_elapsed, 1),
        "estimated_full_sweep_hours": round(sweep_hours, 1),
        "estimated_full_sweep_hours_note": f"{total_corpus} acts at {avg_sec:.2f}s/act",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="aya-expanse:8b",
                        help="Ollama model name to test")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to first N items (0 = all 300)")
    parser.add_argument("--num-predict", type=int, default=15,
                        help="Max tokens to generate (use 600+ for thinking models like qwen3)")
    args = parser.parse_args()

    model = args.model
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    if args.limit > 0:
        sample = sample[:args.limit]

    tag = re.sub(r"[^a-zA-Z0-9_-]", "_", model)[:60]
    results_path = OUT_DIR / f"local_llm_results_{tag}.json"
    metrics_path = OUT_DIR / f"local_llm_metrics_{tag}.json"

    print(f"Model: {model}")
    print(f"Sample size: {len(sample)}")
    print(f"num_predict: {args.num_predict}")
    print()

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            pass
        print("Ollama: reachable OK")
    except Exception as e:
        print(f"Ollama not reachable: {e}")
        sys.exit(1)

    results = []
    milestone_log = []
    t_run_start = time.time()

    for i, item in enumerate(sample):
        api_rating = item["api_rating"]
        text = item.get("text", "")

        raw, elapsed = call_ollama_chat(model, text, num_predict=args.num_predict)
        local_rating = parse_rating(raw)

        results.append({
            "label": item["label"],
            "act_index": item["act_index"],
            "api_rating": api_rating,
            "local_rating": local_rating,
            "raw_response": raw[:120],
            "elapsed_sec": round(elapsed, 3),
        })

        if (i + 1) % 10 == 0 or i == 0:
            elapsed_run = time.time() - t_run_start
            rate = (i + 1) / elapsed_run if elapsed_run > 0 else 0
            print(f"  [{i+1:3d}/{len(sample)}] last={elapsed:.1f}s  rate={rate:.2f}/s  "
                  f"api={api_rating} local={local_rating}  raw='{raw[:60]}'")
            milestone_log.append({
                "i": i + 1,
                "elapsed_run": round(elapsed_run, 1),
                "rate_acts_per_sec": round(rate, 3),
            })

        if (i + 1) % 20 == 0:
            results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = compute_metrics(results)
    metrics["model"] = model
    metrics["milestone_log"] = milestone_log
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=" * 60)
    print(f"RESULTS for {model}")
    print("=" * 60)
    print(f"  Valid responses:          {metrics['n_valid']} / {len(sample)}")
    if metrics.get("error"):
        print(f"  ERROR: {metrics['error']}")
    else:
        print(f"  Overall 3-way agreement:  {metrics['overall_3way_agreement']:.1%}")
        print()
        print(f"  Garbage recall:           {metrics['garbage_recall']:.1%}  (TP={metrics['garbage_tp']}, FN={metrics['garbage_fn']})")
        print(f"  Garbage precision:        {metrics['garbage_precision']:.1%}  (TP={metrics['garbage_tp']}, FP={metrics['garbage_fp']})")
        print(f"  Garbage F1:               {metrics['garbage_f1']:.3f}")
        print()
        print(f"  Avg sec/act:              {metrics['avg_sec_per_act']:.2f}s")
        print(f"  Estimated full sweep:     {metrics['estimated_full_sweep_hours']:.1f} hours")
        print()
        print("  Confusion matrix (api->local):")
        for true_cls in ["clean", "noisy_but_coherent", "garbage"]:
            row = f"    {true_cls}:"
            for pred_cls in ["clean", "noisy_but_coherent", "garbage"]:
                row += f"  {pred_cls}={metrics['confusion_matrix'][f'{true_cls}->{pred_cls}']}"
            print(row)
    print()
    print(f"Results: {results_path}")
    print(f"Metrics: {metrics_path}")


if __name__ == "__main__":
    main()
