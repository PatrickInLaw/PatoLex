"""
build_symspell_worklist.py -- heuristic-plan #2: generate + PERSIST the SymSpell candidate worklist
(the "lists") over the post-autocorrect corpus, WITHOUT applying anything.

This is the route-to-adjudication list: each still-flagged token that the corpus-aware SymSpell maps
to a confident candidate, deduped to a (token -> candidate, dist) TYPE with an occurrence count and a
few sample contexts, then frequency-tiered (freq>=10 / 2-9 / singleton) so adjudication can be scoped
by ROI. It is decoupled from the cascade on purpose: the cascade auto-applies the DETERMINISTIC passes;
this only EMITS candidates (SymSpell precision es1~83% / es2~75-80% is sub-legal-grade, so it must be
adjudicated, never auto-applied -- decision 2026-06-12).

Guards mirror the cascade so the worklist is genuine edit-2 typos, NOT noise: skip known words, garbage
shapes, roman numerals, and affix-of-a-common-word fragments (a fragment like 'urer' is reunify's job,
and SymSpell would mis-map it, e.g. 'urer'->'user'). Reads the cascade's persisted post-autocorrect
stage output (out_autocorrect/{vol}.json = {pk: [[tok,...], ...]}).

Supersedes size_candidates.py (which read the cascade audit -- only populated when SymSpell was applied).

Run from the repo:   python -m analysis.build_symspell_worklist
Writes: <cascade_dir>/symspell_worklist.tsv   (token  candidate  dist  occ  ctx1;ctx2;ctx3)
Prints: the freq-tier summary (types / occ / est Sonnet tokens).
"""
import os, re, json, glob, time
from collections import Counter, defaultdict
import multiprocessing as mp
import config

CASCADE     = config.path_for("cascade_dir")
STAGE_OUT   = os.path.join(CASCADE, "out_autocorrect")
CORPUS_FREQ = config.path_for("cascade_dir", "corpus_freq.json")
OUT_TSV     = os.path.join(CASCADE, "symspell_worklist.tsv")
LOG         = os.path.join(CASCADE, "symspell-worklist-run.log")
MAX_CTX     = 3                                   # sample contexts retained per (token->fix) type
_ROMAN      = re.compile(r"^[ivxlcdm]+$")

_WS = None; _HASWF = False; _WF = None; _ZIPF = None; _SORTED = None; _SORTED_REV = None; _SYM = None
def _init():
    global _WS, _HASWF, _WF, _ZIPF, _SORTED, _SORTED_REV, _SYM
    from ocrcorrect.dictionary import build_dictionary, build_sorted_common
    from ocrcorrect.symspell_e2 import SymSpellE2, load_target_freq
    from wordfreq import zipf_frequency
    ws, _s, has, wf = build_dictionary()
    _WS = frozenset(ws); _HASWF = has; _WF = wf; _ZIPF = zipf_frequency
    _SORTED, _SORTED_REV = build_sorted_common(_WS, _ZIPF)
    _SYM = SymSpellE2(load_target_freq(CORPUS_FREQ)) if os.path.exists(CORPUS_FREQ) else None

def known(t): return (t in _WS) or (_HASWF and _WF(t, "en") > 0)

from ocrcorrect.edits import affix_of_common as _affix
from ocrcorrect.symspell_e2 import _garbage_shaped

def _worklist(fp):
    """For one post-autocorrect volume: yield (token, cand, dist, prev, next) for each flagged token
    SymSpell can map to a confident candidate (after the cascade's guards)."""
    out = []
    if _SYM is None:
        return out
    try:
        d = json.load(open(fp, encoding="utf-8", errors="replace"))
    except Exception:
        return out
    for pk, lines in d.items():
        for toks in lines:
            for i, t in enumerate(toks):
                if len(t) < 5 or known(t):
                    continue
                if _ROMAN.match(t) or _garbage_shaped(t):
                    continue
                if _affix(t, _SORTED, _SORTED_REV):          # fragment -> reunify's job, skip
                    continue
                res = _SYM.lookup(t)                          # (word, 's1'|'s2') or None
                if res:
                    cand, dist = res
                    prev = toks[i - 1] if i > 0 else ""
                    nxt = toks[i + 1] if i + 1 < len(toks) else ""
                    out.append((t, cand, dist, prev, nxt))
    return out

def _rlog(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SYMSPELL-WORKLIST | {msg}\n"
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "a", encoding="utf-8").write(line)
    print(line.rstrip(), flush=True)

def main():
    files = sorted(glob.glob(os.path.join(STAGE_OUT, "*.json")))
    nw = max(2, min(8, (os.cpu_count() or 4) - 2))           # cap for RAM (each worker builds dict+symspell)
    _rlog(f"START worklist build over {len(files)} post-autocorrect volumes, {nw} workers")
    t0 = time.time()
    occ = Counter()                                          # (token, cand, dist) -> occurrences
    ctx = defaultdict(list)                                  # (token, cand, dist) -> [up to MAX_CTX contexts]
    pool_ctx = mp.get_context("spawn")
    done = 0; last = t0
    with pool_ctx.Pool(nw, initializer=_init) as pool:
        for rows in pool.imap_unordered(_worklist, files, chunksize=1):
            for (t, cand, dist, prev, nxt) in rows:
                k = (t, cand, dist)
                occ[k] += 1
                if len(ctx[k]) < MAX_CTX:
                    ctx[k].append(f"{prev}|{t}|{nxt}".strip("|"))
            done += 1
            now = time.time()
            if now - last >= 15 or done == len(files):
                _rlog(f"{done}/{len(files)} vols | {len(occ):,} types / {sum(occ.values()):,} occ | {now-t0:.0f}s")
                last = now

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", encoding="utf-8") as fh:
        fh.write("token\tcandidate\tdist\tocc\tcontexts\n")
        for (t, cand, dist), n in sorted(occ.items(), key=lambda kv: -kv[1]):
            fh.write(f"{t}\t{cand}\t{dist}\t{n}\t{';'.join(ctx[(t, cand, dist)])}\n")

    # freq-tier summary (by occurrence count of the token->fix pair)
    def tier(c): return "freq>=10" if c >= 10 else ("2-9" if c >= 2 else "singleton")
    tt = Counter(); to = Counter()
    s1 = s2 = 0
    for k, c in occ.items():
        tt[tier(c)] += 1; to[tier(c)] += c
        if k[2] == "s1": s1 += 1
        else: s2 += 1
    _rlog(f"DONE {len(occ):,} types / {sum(occ.values()):,} occ  ({s1:,} s1 / {s2:,} s2)  wall={time.time()-t0:.0f}s")
    print(f"\nSymSpell candidate worklist -> {OUT_TSV}")
    print(f"distinct (token->fix,dist) TYPES: {len(occ):,}   occurrences: {sum(occ.values()):,}")
    print("by pair-frequency tier (types / occ / ~Sonnet tokens @ ~75/type):")
    for t in ("freq>=10", "2-9", "singleton"):
        print(f"  {t:10s} {tt[t]:7,} types / {to[t]:8,} occ / ~{tt[t]*75/1000:.0f}K tok")
    cum = 0
    for label, n in (("freq>=10", tt["freq>=10"]), ("freq>=2", tt["freq>=10"]+tt["2-9"]), ("ALL", len(occ))):
        print(f"  adjudicate {label:9s}: {n:,} types  ~{n*75/1000:.0f}K Sonnet tokens")

if __name__ == "__main__":
    main()
