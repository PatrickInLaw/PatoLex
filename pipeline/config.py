r"""
config.py -- the SINGLE source of truth for ALL PatoLex pipeline locations.

Design (Patrick 2026-06-12): ONE location root + a location REGISTRY + ONE resolver function.
  - LOCATION_ROOT is the base for everything. Change this one line (or set PATOLEX_LOCATION_ROOT) to
    relocate the WHOLE project -- a local dir, an SMB share (\\host\share), etc.
  - _LOCATIONS maps a location NAME -> its relative default. Each is independently overridable via the
    env var PATOLEX_<NAME>. A value that is a fully-qualified path (absolute / UNC) AUTO-OVERRIDES the
    root and is used as-is; a relative value is joined to LOCATION_ROOT.
  - `path_for(name, *subpath)` is THE single accessor: give it a registered location name (and optional
    sub-path parts) and it returns the full resolved path. The override logic lives ONLY here; no caller
    writes it. There are deliberately NO convenience constants -- one function, used everywhere.

So: move everything = change LOCATION_ROOT; move ONE folder elsewhere = set its PATOLEX_<NAME> (or its
registry default) to an absolute path; add a location = add one registry line.

NOTE: `path_for` resolves filesystem paths (local + UNC/SMB). Non-filesystem protocols (ssh://, s3://, ...)
would need a small access layer keyed off the URL scheme -- a future extension the registry shape allows.
"""
import os

# ---- THE root knob: change this one line (or set PATOLEX_LOCATION_ROOT) to move EVERYTHING -----------
LOCATION_ROOT = os.environ.get("PATOLEX_LOCATION_ROOT", r"C:\Users\patolex\PatoLex-scratch")

# ---- the location registry: NAME -> relative default (override per-location via PATOLEX_<NAME>) -------
_LOCATIONS = {
    "data_root":        "",                  # corpus production-* dirs; default == LOCATION_ROOT
    "cascade_dir":      "_cascade",          # correction cascade stage outputs
    "vocab_dir":        "_vocab",            # dict additions, run logs
    "parse_output_dir": "_parse_outputs",    # git-versionable parsed_acts
    "gazetteer":        "name_gazetteer.txt",
}

# box-specific tool binary (DB ingest only, not a data location)
PSQL_BIN = os.environ.get("PATOLEX_PSQL", r"C:\Program Files\PostgreSQL\16\bin\psql.exe")

def _resolve(value):
    r"""Relative -> joined to LOCATION_ROOT; fully-qualified (absolute or UNC \\host\share) -> used as-is."""
    if not value:
        return LOCATION_ROOT
    if os.path.isabs(value) or value.startswith("\\\\"):
        return value
    return os.path.join(LOCATION_ROOT, value)

def path_for(name, *subpath):
    """THE accessor. Given a registered location NAME (+ optional sub-path parts), return the full path,
    with env override + relative-to-root / absolute-override applied. Raises on an unknown name.
    e.g. path_for("cascade_dir")  /  path_for("cascade_dir", "corpus_freq.json")
         path_for("data_root", f"production-{label}", "ocr_consensus", "page_ocr_results.json")"""
    if name not in _LOCATIONS:
        raise KeyError(f"unknown location {name!r} (known: {sorted(_LOCATIONS)})")
    env = os.environ.get("PATOLEX_" + name.upper())
    base = _resolve(env if env is not None else _LOCATIONS[name])
    return os.path.join(base, *subpath) if subpath else base

def ensure_dirs():
    for n in ("cascade_dir", "vocab_dir", "parse_output_dir"):
        os.makedirs(path_for(n), exist_ok=True)
