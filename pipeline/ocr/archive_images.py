#!/usr/bin/env python3
r"""
archive_images.py -- PatoLex "rolling archiver"
================================================
Moves COMPLETED volumes' bulk page-image directories off an OCR box's hot
scratch to the 3060 cold-storage box, freeing scratch during the long
1850-forward OCR campaign.

WHAT MOVES (the BULK / regenerable cache):
    production-<label>/pages_raw/
    production-<label>/pages_prep_*/        (e.g. pages_prep_gray, pages_prep_sauvola)

WHAT STAYS LOCAL (NEVER moved or deleted -- the precious OCR product):
    production-<label>/ocr_consensus/        (page_ocr_results.json text+confidence)
    production-<label>/sha256.txt
    production-<label>/OCR_COMPLETE.marker
    (and anything else in the volume dir that is not an image dir)

ELIGIBILITY (a volume is archivable only if ALL hold):
    1. production-<label>/OCR_COMPLETE.marker EXISTS, AND
    2. the volume is NOT 'in_progress' (nor any non-done active state) in the
       queue (production_queue_state.json) -- never touch an in-flight volume, AND
    3. it has at least one image dir present locally, AND
    4. it is not already recorded in the archive manifest (idempotent).

DESTINATION:
    3060 box (default patolex@100.113.254.6), path:
        D:\PatoLex-archive\production-<label>\<label>_images.tar.gz
    We STORE THE COMPRESSED TAR (.tar.gz) on D: -- we do NOT extract it.
    Rationale: these are a regenerable cache; compressed storage saves space and
    a single artifact per volume is trivially fetchable by the future
    crowd-correction tool. The tar's internal layout preserves the
    pages_raw/ and pages_prep_*/ subtrees so it can be expanded 1:1 later.

SAFETY (this script DELETES source files -- treat with care):
    Default mode is DRY-RUN: it lists eligible volumes + sizes + what WOULD move
    and transfers/deletes NOTHING. Only `--commit` performs real work, and even
    then a local image dir is deleted ONLY after a 3-part verification PASSES:
        (a) the local tar's SHA-256 matches the SHA-256 computed remotely on D:
            (proves the bytes arrived intact), AND
        (b) the tar's member count == the source image-file count, AND
        (c) the sum of member sizes inside the tar == the source total bytes.
    Any failure => fail loud, leave locals untouched, mark FAIL in the log.

THROTTLE:
    scp is invoked with `-l <kbit/s>` (default 80000 = 80 Mbit/s) so the
    transfer does not saturate the workstation link. Override with --limit.

PER-BOX / IDEMPOTENT:
    --scratch sets the scratch root. Defaults are auto-detected:
        5080-role box (user PatrickKolasinski): C:\Users\PatrickKolasinski\PatoLex-scratch
        5090 box (user patolex):                C:\Users\patolex\PatoLex-scratch
    Run the script ON each OCR box (it archives that box's local scratch).
    Already-archived volumes (present in the manifest) are skipped.

MANIFEST:
    Appended (one row per archived volume) to BOTH:
        <scratch>\archive_manifest.csv   (local copy)
        D:\PatoLex-archive\archive_manifest.csv  (canonical, on the 3060)
    Columns: label, source_box, files, bytes, dest_path, verify_status,
             sha256, archived_at

USAGE:
    # Dry-run on the box you are sitting on (auto scratch):
    python archive_images.py

    # Dry-run on the 5080-role box explicitly:
    python archive_images.py --scratch "C:\Users\PatrickKolasinski\PatoLex-scratch"

    # Dry-run on the 5090 (run this ON the 5090, user patolex):
    python archive_images.py --scratch "C:\Users\patolex\PatoLex-scratch"

    # REAL move (DELETES locals after verify) -- requires Hans review first:
    python archive_images.py --commit

    Optional:
      --dest-host patolex@100.113.254.6   (3060)
      --dest-root "D:\PatoLex-archive"
      --ssh-key  C:/Users/PatrickKolasinski/.ssh/patolex_5090
      --limit 80000        (scp bandwidth cap, kbit/s)
      --only 1862,1863     (restrict to specific labels)
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import getpass
import hashlib
import json
import os
import socket
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
import config

# --- box defaults --------------------------------------------------------

DEFAULT_DEST_HOST = "patolex@100.113.254.6"          # the 3060 cold-storage box
DEFAULT_DEST_ROOT = r"D:\PatoLex-archive"
DEFAULT_SSH_KEY   = r"C:/Users/PatrickKolasinski/.ssh/patolex_5090"
DEFAULT_LIMIT_KBIT = 80000                            # scp -l, ~80 Mbit/s

# Repo run-log (relative to this file: pipeline/ -> repo root)
REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_LOG = REPO_ROOT / "docs" / "80_PROJECT_HISTORY" / "run-logs" / "rolling-archiver-run.log"

MANIFEST_HEADER = [
    "label", "source_box", "files", "bytes",
    "dest_path", "verify_status", "sha256", "archived_at",
]


def now_log_ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M PT")


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def log(phase: str, desc: str, status: str = "OK") -> None:
    """Append to the repo run-log AND echo to stdout (no bash echo)."""
    line = f"[{now_log_ts()}] {phase} | {desc} | {status}"
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


# --- scratch auto-detect -------------------------------------------------

def autodetect_scratch() -> Path:
    user = getpass.getuser()
    candidates = [
        Path(config.path_for("data_root")),
        Path(rf"C:\Users\{user}\PatoLex-scratch"),
        Path(r"C:\Users\patolex\PatoLex-scratch"),
        Path(r"C:\Users\PatrickKolasinski\PatoLex-scratch"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def source_box_label() -> str:
    return f"{socket.gethostname()}/{getpass.getuser()}"


# --- image dirs ----------------------------------------------------------

def image_dirs(vol_dir: Path) -> list[Path]:
    """The bulk image dirs in a volume: pages_raw and pages_prep_*."""
    out: list[Path] = []
    for d in sorted(vol_dir.iterdir()):
        if not d.is_dir():
            continue
        if d.name == "pages_raw" or d.name.startswith("pages_prep_"):
            out.append(d)
    return out


def dir_stats(dirs: list[Path]) -> tuple[int, int]:
    """(file_count, total_bytes) across the given dirs, recursive."""
    files = 0
    total = 0
    for d in dirs:
        for root, _subdirs, names in os.walk(d):
            for n in names:
                p = Path(root) / n
                try:
                    total += p.stat().st_size
                    files += 1
                except OSError:
                    pass
    return files, total


def gb(n: int) -> float:
    return round(n / (1024 ** 3), 2)


# --- queue ---------------------------------------------------------------

def load_queue_status(scratch: Path) -> dict[str, str]:
    """Map label -> status from production_queue_state.json (best effort)."""
    qf = scratch / "production_queue_state.json"
    out: dict[str, str] = {}
    if not qf.is_file():
        return out
    try:
        data = json.loads(qf.read_text(encoding="utf-8"))
        for v in data.get("volumes", []):
            out[str(v.get("label"))] = str(v.get("status", ""))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return out


# --- manifest ------------------------------------------------------------

def read_manifest_labels(scratch: Path) -> set[str]:
    """Labels already archived, per the LOCAL manifest copy."""
    mf = scratch / "archive_manifest.csv"
    done: set[str] = set()
    if not mf.is_file():
        return done
    try:
        with open(mf, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("verify_status") == "PASS":
                    done.add(row["label"])
    except (OSError, csv.Error):
        pass
    return done


def append_manifest_local(scratch: Path, row: dict) -> None:
    mf = scratch / "archive_manifest.csv"
    new = not mf.is_file()
    with open(mf, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_HEADER)
        if new:
            w.writeheader()
        w.writerow(row)


# --- remote (3060) helpers via SSH ---------------------------------------

def ssh_base(args) -> list[str]:
    return [
        # -n: never read stdin (don't let the nested ssh attach to a parent pipe).
        "ssh", "-n", "-i", args.ssh_key,
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        args.dest_host,
    ]


class _RemoteResult:
    """Minimal stand-in for CompletedProcess (returncode/stdout/stderr)."""
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_remote_ps(args, ps_script: str, timeout: int = 600) -> _RemoteResult:
    """Run a PowerShell script on the 3060 via EncodedCommand (no quoting hell).

    IMPORTANT: we redirect the child's stdout/stderr to TEMP FILES instead of
    capture_output=True (PIPE). The 3060's default ssh shell is PowerShell, which
    emits a large CLIXML progress blob on stderr and can leave a grandchild
    holding the pipe write-end open -- so subprocess.run(capture_output=True)
    deadlocks on communicate() waiting for an EOF that never comes, hanging the
    whole archiver after "START". File redirection sidesteps the pipe entirely.
    """
    enc = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
    cmd = ssh_base(args) + [f"powershell -NoProfile -EncodedCommand {enc}"]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".out") as _o:
        out_path = _o.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".err") as _e:
        err_path = _e.name
    try:
        with open(out_path, "wb") as o, open(err_path, "wb") as e:
            rc = subprocess.call(cmd, stdout=o, stderr=e,
                                 stdin=subprocess.DEVNULL, timeout=timeout)
        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            out = f.read()
        with open(err_path, "r", encoding="utf-8", errors="replace") as f:
            err = f.read()
        return _RemoteResult(rc, out, err)
    finally:
        for p in (out_path, err_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def remote_sha256(args, dest_file_win: str) -> str | None:
    ps = (
        f"$h=Get-FileHash -Algorithm SHA256 -LiteralPath '{dest_file_win}' "
        f"-ErrorAction SilentlyContinue; if($h){{$h.Hash.ToLower()}}"
    )
    cp = run_remote_ps(args, ps)
    if cp.returncode != 0:
        return None
    out = cp.stdout.strip().lower()
    return out or None


def remote_mkdir(args, dest_dir_win: str) -> bool:
    ps = f"New-Item -ItemType Directory -Force -Path '{dest_dir_win}' | Out-Null; 'OK'"
    cp = run_remote_ps(args, ps)
    return cp.returncode == 0 and "OK" in cp.stdout


def remote_append_manifest(args, row: dict) -> bool:
    """Append one CSV row to D:\\PatoLex-archive\\archive_manifest.csv, with header if new."""
    dest_csv = f"{args.dest_root}\\archive_manifest.csv"
    header = ",".join(MANIFEST_HEADER)
    vals = ",".join(str(row[k]) for k in MANIFEST_HEADER)
    ps = (
        f"$p='{dest_csv}'; "
        f"if(-not (Test-Path $p)){{ Set-Content -LiteralPath $p -Value '{header}' -Encoding utf8 }}; "
        f"Add-Content -LiteralPath $p -Value '{vals}' -Encoding utf8; 'OK'"
    )
    cp = run_remote_ps(args, ps)
    return cp.returncode == 0 and "OK" in cp.stdout


# --- local hashing / tar -------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_tar(vol_dir: Path, dirs: list[Path], tar_path: Path) -> tuple[int, int]:
    """Create tar_path (gzip) containing the image dirs, members rooted at the
    dir name (e.g. 'pages_raw/0001.png'). Returns (member_files, member_bytes)."""
    member_files = 0
    member_bytes = 0
    with tarfile.open(tar_path, "w:gz") as tf:
        for d in dirs:
            for root, _subdirs, names in os.walk(d):
                for n in names:
                    p = Path(root) / n
                    arc = p.relative_to(vol_dir).as_posix()
                    try:
                        tf.add(str(p), arcname=arc, recursive=False)
                        member_files += 1
                        member_bytes += p.stat().st_size
                    except OSError:
                        pass
    return member_files, member_bytes


# --- core ----------------------------------------------------------------

def gather_eligible(args, scratch: Path):
    """Return list of dicts describing each eligible volume."""
    qstatus = load_queue_status(scratch)
    already = read_manifest_labels(scratch)
    only = set(x.strip() for x in args.only.split(",")) if args.only else None

    eligible = []
    skipped = []
    for vol_dir in sorted(scratch.glob("production-*")):
        if not vol_dir.is_dir():
            continue
        label = vol_dir.name[len("production-"):]
        if only and label not in only:
            continue

        marker = (vol_dir / "OCR_COMPLETE.marker").exists()
        status = qstatus.get(label, "")
        # "active" = anything claimed/working that is not done. Be conservative:
        # only 'done' is safe (absent/pending lack a marker and are caught above).
        # Includes the decoupled-pipeline statuses so the archiver never removes
        # the raw/prep images of a volume still being prepped or OCR'd.
        in_flight = status in ("in_progress", "failed", "prepping", "prepped", "ocring", "ocr_failed")
        dirs = image_dirs(vol_dir)

        reason = None
        if label in already:
            reason = "already-archived (manifest)"
        elif not marker:
            reason = "no OCR_COMPLETE.marker"
        elif in_flight:
            reason = f"queue status '{status}' (in-flight)"
        elif not dirs:
            reason = "no image dirs present"

        if reason:
            skipped.append({"label": label, "reason": reason, "status": status})
            continue

        files, total = dir_stats(dirs)
        eligible.append({
            "label": label,
            "vol_dir": vol_dir,
            "dirs": dirs,
            "files": files,
            "bytes": total,
            "status": status or "(not in queue)",
        })
    return eligible, skipped


def archive_one(args, scratch: Path, e: dict) -> bool:
    """COMMIT path: tar -> scp -> verify -> delete locals -> manifest."""
    label = e["label"]
    vol_dir: Path = e["vol_dir"]
    dirs: list[Path] = e["dirs"]
    src_files = e["files"]
    src_bytes = e["bytes"]
    box = source_box_label()
    dest_dir_win = f"{args.dest_root}\\production-{label}"
    dest_file_win = f"{dest_dir_win}\\{label}_images.tar.gz"

    log("ARCHIVE", f"{label}: START ({src_files} files, {gb(src_bytes)} GB)", "OK")

    # 1. ensure remote dir
    if not remote_mkdir(args, dest_dir_win):
        log("ARCHIVE", f"{label}: remote mkdir FAILED", "FAIL")
        return False

    # 2. build tar locally (temp, on same drive as scratch to avoid cross-vol copy)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"patolex_arch_{label}_", dir=str(scratch)))
    tar_path = tmp_dir / f"{label}_images.tar.gz"
    try:
        member_files, member_bytes = build_tar(vol_dir, dirs, tar_path)
        # (b) member count check
        if member_files != src_files:
            log("ARCHIVE", f"{label}: tar member count {member_files} != source {src_files}", "FAIL")
            return False
        # (c) member bytes check
        if member_bytes != src_bytes:
            log("ARCHIVE", f"{label}: tar member bytes {member_bytes} != source {src_bytes}", "FAIL")
            return False
        local_sha = sha256_file(tar_path)
        log("ARCHIVE", f"{label}: tar built {gb(tar_path.stat().st_size)} GB sha={local_sha[:12]}", "OK")

        # 3. scp with bandwidth throttle.
        # -O forces the legacy SCP protocol. The 3060's default ssh shell is
        # PowerShell, which mangles the modern SFTP-subsystem stream so the
        # default scp stalls with a 0-byte file at the dest. -O transfers fine.
        scp_target = f"{args.dest_host}:{dest_file_win}"
        scp_cmd = [
            "scp", "-O", "-i", args.ssh_key,
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-l", str(args.limit),
            str(tar_path), scp_target,
        ]
        cp = subprocess.run(scp_cmd, capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
        if cp.returncode != 0:
            log("ARCHIVE", f"{label}: scp FAILED rc={cp.returncode} {cp.stderr.strip()[:200]}", "FAIL")
            return False

        # 4. (a) remote SHA-256 verify
        rsha = remote_sha256(args, dest_file_win)
        if rsha != local_sha:
            log("ARCHIVE", f"{label}: remote sha {rsha} != local {local_sha} -- NOT deleting", "FAIL")
            return False
        log("ARCHIVE", f"{label}: VERIFY PASS (sha match, {member_files} files, {gb(member_bytes)} GB)", "OK")

        # 5. delete local image dirs (ONLY now)
        deleted = 0
        for d in dirs:
            try:
                _rmtree(d)
                deleted += 1
            except OSError as ex:
                log("ARCHIVE", f"{label}: delete WARN on {d.name}: {ex}", "WARN")
        log("ARCHIVE", f"{label}: deleted {deleted}/{len(dirs)} local image dirs, freed {gb(src_bytes)} GB", "OK")

        # 6. manifest (local + remote)
        row = {
            "label": label,
            "source_box": box,
            "files": src_files,
            "bytes": src_bytes,
            "dest_path": dest_file_win,
            "verify_status": "PASS",
            "sha256": local_sha,
            "archived_at": now_iso(),
        }
        append_manifest_local(scratch, row)
        if not remote_append_manifest(args, row):
            log("ARCHIVE", f"{label}: remote manifest append WARN (local recorded)", "WARN")
        log("ARCHIVE", f"{label}: DONE", "OK")
        return True
    finally:
        # always clean up the local temp tar
        try:
            if tar_path.exists():
                tar_path.unlink()
            tmp_dir.rmdir()
        except OSError:
            pass


def _rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(str(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="PatoLex rolling archiver (DRY-RUN by default).")
    ap.add_argument("--scratch", default=None, help="scratch root (auto-detected if omitted)")
    ap.add_argument("--commit", action="store_true", help="REAL move (tar+scp+verify+DELETE). Default is dry-run.")
    ap.add_argument("--dest-host", default=DEFAULT_DEST_HOST)
    ap.add_argument("--dest-root", default=DEFAULT_DEST_ROOT)
    ap.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT_KBIT, help="scp bandwidth cap, kbit/s")
    ap.add_argument("--only", default=None, help="comma-separated labels to restrict to")
    args = ap.parse_args()

    scratch = Path(args.scratch) if args.scratch else autodetect_scratch()
    box = source_box_label()
    mode = "COMMIT" if args.commit else "DRY-RUN"

    if not scratch.is_dir():
        log("INIT", f"scratch not found: {scratch}", "FAIL")
        return 2

    log("INIT", f"mode={mode} box={box} scratch={scratch} dest={args.dest_host}:{args.dest_root}", "OK")

    eligible, skipped = gather_eligible(args, scratch)

    # report
    print()
    print(f"=== PatoLex rolling archiver -- {mode} ===")
    print(f"box:     {box}")
    print(f"scratch: {scratch}")
    print(f"dest:    {args.dest_host}:{args.dest_root}")
    print()
    if not eligible:
        print("ELIGIBLE volumes: NONE")
    else:
        print(f"ELIGIBLE volumes ({len(eligible)}):")
        print(f"  {'label':<16} {'queue':<14} {'files':>7} {'GB':>8}")
        total_bytes = 0
        total_files = 0
        for e in eligible:
            print(f"  {e['label']:<16} {e['status']:<14} {e['files']:>7} {gb(e['bytes']):>8}")
            total_bytes += e["bytes"]
            total_files += e["files"]
        print(f"  {'-'*48}")
        print(f"  {'TOTAL':<16} {'':<14} {total_files:>7} {gb(total_bytes):>8}")
        print()
        print(f"  >>> {gb(total_bytes)} GB reclaimable on this box ({box}) <<<")
        log("REPORT", f"{len(eligible)} eligible, {gb(total_bytes)} GB reclaimable on {box}", "OK")

    if skipped:
        print()
        print(f"SKIPPED volumes ({len(skipped)}):")
        for s in skipped:
            print(f"  {s['label']:<16} -- {s['reason']}")

    print()
    if not args.commit:
        print("DRY-RUN: nothing was transferred or deleted. Re-run with --commit to archive.")
        print("WARNING: --commit DELETES local image dirs after verify. Requires a Hans review of the delete/verify path first.")
        log("DONE", f"DRY-RUN complete ({len(eligible)} eligible)", "OK")
        return 0

    # COMMIT path
    log("COMMIT", f"Starting real archive of {len(eligible)} volume(s)", "WARN")
    ok = 0
    for e in eligible:
        if archive_one(args, scratch, e):
            ok += 1
    log("DONE", f"COMMIT complete: {ok}/{len(eligible)} archived", "OK" if ok == len(eligible) else "WARN")
    print(f"\nCOMMIT complete: {ok}/{len(eligible)} volumes archived.")
    return 0 if ok == len(eligible) else 1


if __name__ == "__main__":
    sys.exit(main())
