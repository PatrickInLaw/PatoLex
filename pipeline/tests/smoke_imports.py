"""
smoke_imports.py -- STATIC import-resolution net for the pipeline reorg.

A reorg can only break IMPORTS (a moved file that something imported as a sibling can no longer be found);
it never changes logic. So this verifies, WITHOUT executing any code or importing any heavy deps, that
every INTERNAL import in every pipeline/*.py resolves to a real module file under the current tree.

- Parses each file's imports via AST (no execution -> no torch/doctr/tesseract/DB side effects).
- "Internal" = the import's top-level name matches a pipeline module basename OR a pipeline subpackage dir.
  External deps (torch, wordfreq, nltk, fitz, cv2, psycopg2, ...) are IGNORED.
- An internal import resolves if the target exists relative to (a) the importing file's own directory
  [flat sibling model], or (b) any SOURCE_ROOT [package model: pipeline/ on sys.path].
- Run BEFORE the reorg (baseline = 0 violations) and AFTER every move. Any violation = a broken link.

Usage:  python pipeline/tests/smoke_imports.py    ->  exit 0 = OK, 1 = broken internal imports
"""
import ast, os, sys

PIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # pipeline/
SOURCE_ROOTS = [PIPELINE]   # dirs that will be on sys.path at runtime (pipeline/ as the package root)
SKIP_DIRS = {"__pycache__", "tests", ".git"}

def _walk_py(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f.endswith(".py"):
                yield os.path.join(dp, f)

def _internal_top_names(root):
    """Top-level names that are pipeline's own: every module basename + every subdir (package) name."""
    names = set()
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for d in dn:
            names.add(d)
        for f in fn:
            if f.endswith(".py"):
                names.add(f[:-3])
    return names

def _imports(path):
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
    except SyntaxError as e:
        return None, e
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:        # absolute import only (level>0 = relative, always local)
                out.append((node.module, node.lineno))
    return out, None

def _self_added_roots(src):
    """Extra sys.path roots a file adds for ITSELF, as pipeline-relative subdirs.

    cc019 FALSE-POSITIVE FIX. The original resolver modelled only two cases:
    (a) flat sibling, (b) pipeline/ on sys.path. There is a third, used
    legitimately across analysis/: a script does

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))
        import recover_early

    recover_early DOES exist at pipeline/ingest/recover_early.py, so the import
    resolves fine at runtime -- but the checker reported it BROKEN. Two such
    false positives (analysis/_diag_early5.py, analysis/_diag_fp.py) sat in the
    output long enough to become "known failures", which is how a real one would
    have been missed.

    Scoped deliberately: only quoted names that are real pipeline subdirectories
    are honoured, and only for the file that declares them -- so this cannot mask
    a genuine sibling break elsewhere.
    """
    roots = []
    for line in src.splitlines():
        if "sys.path.insert" not in line and "sys.path.append" not in line:
            continue
        for quote in ('"', "'"):
            parts = line.split(quote)
            for tok in parts[1::2]:
                cand = os.path.join(PIPELINE, tok)
                if tok and os.path.isdir(cand):
                    roots.append(cand)
    return roots


def _resolves(dotted, importer_dir, extra_roots=()):
    """Does dotted module path resolve to a .py file or package under importer_dir,
    a SOURCE_ROOT, or a root the importing file adds to sys.path itself?"""
    parts = dotted.split(".")
    for base in [importer_dir] + SOURCE_ROOTS + list(extra_roots):
        p = os.path.join(base, *parts)
        if os.path.isfile(p + ".py") or os.path.isfile(os.path.join(p, "__init__.py")):
            return True
    return False

def main():
    internal = _internal_top_names(PIPELINE)
    violations = []; syntax_errs = []
    for path in _walk_py(PIPELINE):
        imps, serr = _imports(path)
        if serr is not None:
            syntax_errs.append((os.path.relpath(path, PIPELINE), serr.lineno, serr.msg)); continue
        d = os.path.dirname(path)
        # Honour sys.path roots this file adds for itself (see _self_added_roots).
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                extra = _self_added_roots(fh.read())
        except Exception:
            extra = []
        for dotted, ln in imps:
            top = dotted.split(".")[0]
            if top in internal and not _resolves(dotted, d, extra):
                violations.append((os.path.relpath(path, PIPELINE), ln, dotted))
    if syntax_errs:
        print(f"SYNTAX ERRORS ({len(syntax_errs)}):")
        for p, ln, m in syntax_errs: print(f"  {p}:{ln}  {m}")
    if violations:
        print(f"BROKEN INTERNAL IMPORTS ({len(violations)}):")
        for p, ln, m in sorted(violations): print(f"  {p}:{ln}  imports '{m}' -> not found as sibling or under pipeline/")
    if syntax_errs or violations:
        return 1
    print(f"SMOKE-IMPORTS OK -- every internal import resolves ({len(internal)} internal names checked)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
