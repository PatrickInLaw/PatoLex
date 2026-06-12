"""
snapshot_parse_baseline.py -- C3: snapshot the CURRENT parse outputs as the re-parse comparison baseline.

Patrick's design: don't bloat git with ~292MB of JSON. Instead:
  - archive the current parsed_acts into ONE compressed file (out of git -- the snapshot),
  - write a small HASH MANIFEST (sha256 per volume + the whole-archive hash) that DOES go in git.
After the full re-parse, re-hash and diff against the committed manifest -> the volumes whose hash CHANGED
are exactly the ones the stale 5080 parser had touched (the date-clamp fix). The rest are byte-identical.

Run:  python -m ingest.snapshot_parse_baseline      (PYTHONPATH=<root> so `import config` resolves)
Writes: <parse_output_dir>/parse_baseline_<stamp>.zip   (the snapshot, keep out of git)
        the manifest is printed + written to <parse_output_dir>/parse_baseline_manifest.json (commit this)
"""
import os, sys, json, glob, hashlib, zipfile, time
import config

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    out_dir = config.path_for("parse_output_dir")
    os.makedirs(out_dir, exist_ok=True)
    stamp = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    archive = os.path.join(out_dir, f"parse_{stamp}.zip")
    manifest_path = os.path.join(out_dir, "parse_baseline_manifest.json")

    files = sorted(glob.glob(config.path_for("data_root", "production-*", "parsed_acts_fixed.json")))
    print(f"hashing + archiving {len(files)} parse outputs...", flush=True)
    files_manifest = {}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            label = os.path.basename(os.path.dirname(p))[len("production-"):]
            files_manifest[label] = {"sha256": _sha256(p), "bytes": os.path.getsize(p)}
            z.write(p, f"parsed_acts_{label}.json")
    archive_hash = _sha256(archive)
    manifest = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "re-parse comparison baseline (current parse outputs, pre-full-reparse)",
        "count": len(files),
        "archive": os.path.basename(archive),
        "archive_bytes": os.path.getsize(archive),
        "archive_sha256": archive_hash,
        "files": files_manifest,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"DONE: {len(files)} files, archive {archive} ({os.path.getsize(archive)/1e6:.0f}MB) sha256={archive_hash[:16]}..")
    print(f"manifest -> {manifest_path}  (commit this to git)")

if __name__ == "__main__":
    main()
