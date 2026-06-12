"""
config.py -- the SINGLE source of truth for PatoLex pipeline data paths.

The whole point: when the data moves to the 3060 SMB share, the cutover is ONE line -- set
PATOLEX_DATA_ROOT (env) and move the files. Nothing else in the pipeline hardcodes a data path.
Default = serve LOCALLY (current per-box scratch).

Usage:  from config import DATA_ROOT, CASCADE_DIR, PARSE_OUTPUT_DIR, ...
Env overrides (the cutover knobs):
  PATOLEX_DATA_ROOT          -> the data root (e.g. \\3060\PatoLex when ready). default below.
  PATOLEX_PARSE_OUTPUT_DIR   -> where parsed_acts*.json are written (git-versionable). default under DATA_ROOT.
"""
import os

# ---- THE cutover knob ----------------------------------------------------------------------------
# Set PATOLEX_DATA_ROOT to relocate the entire corpus/scratch (the 3060 SMB share, eventually).
# Default serves locally; the 5080 sets its own env, the 5090/patolex defaults here.
DATA_ROOT = os.environ.get("PATOLEX_DATA_ROOT", r"C:\Users\patolex\PatoLex-scratch")

# ---- derived data locations (never hardcode these elsewhere) -------------------------------------
CASCADE_DIR = os.path.join(DATA_ROOT, "_cascade")
VOCAB_DIR   = os.path.join(DATA_ROOT, "_vocab")
CORPUS_FREQ = os.path.join(CASCADE_DIR, "corpus_freq.json")
GAZETTEER   = os.path.join(DATA_ROOT, "name_gazetteer.txt")

# Parse outputs: a config'd location so re-parses are diffable (git-versionable). Default under DATA_ROOT;
# point this at a repo folder (or the share) to version the parse outputs.
PARSE_OUTPUT_DIR = os.environ.get("PATOLEX_PARSE_OUTPUT_DIR", os.path.join(DATA_ROOT, "_parse_outputs"))

# Box-specific tool path (DB ingest only, not the parse step). Override via env if it moves.
PSQL_BIN = os.environ.get("PATOLEX_PSQL", r"C:\Program Files\PostgreSQL\16\bin\psql.exe")

# Parse-stage artifacts (de-hardcoded from ingest_from_ocr's old repo-run-log paths)
PARSE_LOG          = os.path.join(VOCAB_DIR, "parse-stage.log")
DATE_REVIEW_WORKLIST = os.path.join(PARSE_OUTPUT_DIR, "date-review-worklist.jsonl")

# Per-volume OCR consensus input lives at  <DATA_ROOT>/production-<label>/ocr_consensus/page_ocr_results.json
def production_dir(label):
    return os.path.join(DATA_ROOT, f"production-{label}")

def ensure_dirs():
    for d in (CASCADE_DIR, VOCAB_DIR, PARSE_OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
