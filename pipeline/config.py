r"""
config.py -- the SINGLE source of truth for ALL PatoLex pipeline locations.

Design (Patrick 2026-06-12): ONE location root + a location REGISTRY + ONE resolver.
  - LOCATION_ROOT is the base for everything. Change this one line (or set PATOLEX_LOCATION_ROOT) to
    relocate the WHOLE project -- a local dir, an SMB share (\\host\share), etc.
  - _LOCATIONS maps a location NAME -> its relative default. Each is independently overridable via the
    env var PATOLEX_<NAME>. A value that is a fully-qualified path (absolute / UNC) AUTO-OVERRIDES the
    root and is used as-is; a relative value is joined to LOCATION_ROOT.
  - `path_for(name)` is the ONE self-contained resolver: it reads the registry + env and returns the full
    path. No caller ever writes the override logic -- they just ask `path_for("cascade_dir")` (or use the
    convenience constants below, which are thin wrappers over it).

So: move everything = change LOCATION_ROOT; move ONE folder elsewhere = set its PATOLEX_<NAME> (or its
registry default) to an absolute path. Add a location = add one registry line.

NOTE: `path_for` resolves filesystem paths (local + UNC/SMB). Non-filesystem protocols (ssh://, s3://, ...)
would need a small access layer keyed off the URL scheme -- a future extension; the registry shape already
accommodates pointing a location at such a URL.
"""
import os

# ---- THE root knob: change this one line (or set PATOLEX_LOCATION_ROOT) to move EVERYTHING -----------
LOCATION_ROOT = os.environ.get("PATOLEX_LOCATION_ROOT", r"C:\Users\patolex\PatoLex-scratch")

# ---- the location registry: NAME -> relative default (override per-location via PATOLEX_<NAME>) -------
_LOCATIONS = {
    "data_root":        "",                 # corpus production-* dirs; default == LOCATION_ROOT
    "cascade_dir":      "_cascade",         # correction cascade stage outputs
    "vocab_dir":        "_vocab",           # dict additions, run logs
    "parse_output_dir": "_parse_outputs",   # git-versionable parsed_acts
    "gazetteer":        "name_gazetteer.txt",
}

def _resolve(value):
    r"""Relative -> joined to LOCATION_ROOT; fully-qualified (absolute or UNC \\host\share) -> used as-is."""
    if not value:
        return LOCATION_ROOT
    if os.path.isabs(value) or value.startswith("\\\\"):
        return value
    return os.path.join(LOCATION_ROOT, value)

def path_for(name):
    """The ONE resolver. Given a registered location NAME, return its full path (env override or default,
    relative-to-root or absolute-override applied). Raises on an unknown name."""
    if name not in _LOCATIONS:
        raise KeyError(f"unknown location {name!r} (known: {sorted(_LOCATIONS)})")
    env = os.environ.get("PATOLEX_" + name.upper())
    return _resolve(env if env is not None else _LOCATIONS[name])

# ---- convenience constants (thin wrappers over path_for, so callers can import names) ----------------
DATA_ROOT        = path_for("data_root")
CASCADE_DIR      = path_for("cascade_dir")
VOCAB_DIR        = path_for("vocab_dir")
PARSE_OUTPUT_DIR = path_for("parse_output_dir")
GAZETTEER        = path_for("gazetteer")

# files within those locations (relocate the parent location to move them)
CORPUS_FREQ          = os.path.join(CASCADE_DIR, "corpus_freq.json")
PARSE_LOG            = os.path.join(VOCAB_DIR, "parse-stage.log")
DATE_REVIEW_WORKLIST = os.path.join(PARSE_OUTPUT_DIR, "date-review-worklist.jsonl")

# box-specific tool path (DB ingest only, not the parse step)
PSQL_BIN = os.environ.get("PATOLEX_PSQL", r"C:\Program Files\PostgreSQL\16\bin\psql.exe")

def production_dir(label):
    return os.path.join(DATA_ROOT, f"production-{label}")

def ensure_dirs():
    for d in (CASCADE_DIR, VOCAB_DIR, PARSE_OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
