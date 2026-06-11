# PatoLex — Project Stats Snapshot

**A point-in-time archive of California statutory law (1850 → present).** Snapshot date: **2026-06-10.**
All figures below are from actual pipeline runs, not estimates. This is a living snapshot — numbers move as the build progresses.

---

## 📚 Corpus scale
| Metric | Value |
|---|---|
| Coverage target | **1850 → present** (point-in-time CA statutes) |
| OCR'd span | 1850–2024 |
| Acts (deterministic scan) | **75,340** across **195 volumes** |
| OCR consensus pages | **328,624** |
| Volume JSON files | 205 |
| **Total word-tokens** | **134,105,434** |
| Unique token types | 572,703 (pre-legal-dict) → 468,246 |
| DB enactments (live, local PG16) | **35,332** = 4,262 OCR (1850–75) + 22,780 official-XML (1991–2024) + 8,290 born-digital (2000–08) |

## 🔍 OCR engine stack
**3-engine consensus**, token-aligned majority vote (`pipeline/consensus.py`):
- **Tesseract 5** · **docTR** (deep-learning, GPU) · **Surya** (GPU detection + recognition)
- Per page: 3 engines → median-token "spine" → align other engines → **per-token majority vote** → real position-aware confidence
- Born-digital fast-path: **PyMuPDF** text-layer extract (skips OCR when a real text layer exists)

## 🖥️ Infrastructure
| Box | Specs | Role |
|---|---|---|
| 5090 | **24 logical cores, 64 GB RAM, 32 GB VRAM** | OCR/GPU + parallel compute; **Ollama, 22 models** |
| 5080 | 16 GB RAM | Local **PostgreSQL 16** (`localhost:5432/patolex`) + PatoAudio |
| Mesh | **Tailscale** + SSH; jobs launched via **WMI `Win32_Process.Create`** (survive SSH disconnect) |

## ⚡ Parallelism / throughput
**Correction pipeline — 134 M tokens, CPU-only, 12 workers on 24 cores:**

| | v5 (Pass B only parallel) | v7 (fully parallel) | Gain |
|---|---|---|---|
| Wall time | **1,468 s (24.5 min)** | **208 s (3.47 min)** | **7.06×** |
| Pass B de-merge | projected **2.7 hours** single-thread | **1.4 s** | **~6,400×** |

- Pass B decomposition (honest): **~600× algorithmic** (early-exit edit-distance vs. building+ranking the full candidate set) **× ~10× parallel** (12 workers) → peak **63,614 token-types/sec** (98,137 types in 1.4 s).
- Parallel file-scan: 205 files / 328 K pages in **~20 s**; workers read their *own* files → **no text crosses the process boundary** (no pickle, low memory).
- Dictionary: **327,947** static = pyspellchecker 160,572 ∪ nltk 234,377 (+167,372 new) ∪ legal supplement, plus `wordfreq` per-token Zipf scoring.

## 🧹 Correction quality (v7 — the honest run)
| Stage | Bad occ | % of corpus | Recovered |
|---|---|---|---|
| Baseline | 1,534,893 | **1.1445%** | — |
| After A (dehyphenate / rejoin) | 1,317,631 | 0.982% | 217,262 (~854K hyphen-joins + 15K rejoins) |
| After B (scored de-merge) | 1,289,685 | 0.961% | 27,946 |
| After C (corpus-freq spell) | 737,115 | **0.5568%** | 552,570 |

- **Residual:** 737,115 occ / 467,978 types — singletons (freq 1) = **385,131**; only **2,655 types** (84,901 occ) are freq≥10 ambiguous.
- **True OCR-error rate is well under 0.56%**, and ~16% of the residual is real legal vocabulary the dictionary simply lacked.
- Key design lesson: dictionary *membership* (`is_known`) is too blunt — replaced with frequency *scoring* (`is_common`, Zipf ≥ 2.5) + corpus-frequency-ranked corrections. See `docs/80_PROJECT_HISTORY/lessons/LESSON_dictionary_membership_too_blunt_for_correction.md`.

## 🤖 LLM adjudication head-to-head (2,655 ambiguous tokens)
| | Local **gemma3:27b** | **Sonnet** (5 parallel agents) |
|---|---|---|
| Runtime | 765 s, 3.5 tok/s, **free** | ~150 s, **~210K tokens** |
| FIX / KEEP / GARBAGE / NAME | 1,251 / 231 / 861 / 311 | 1,478 / 414 / 461 / 302 |

- **Verdict agreement: 62.2%** · both-FIX same correction **52.6%** (541 tokens)
- gemma3 over-discards: **545 tokens it called GARBAGE that Sonnet recovered** (361 fixable + 184 real terms)
- Sonnet wins disagreements ~27/30 (`pubhe→public`, `migden→Migden`, `islais→Islais`, `indorser` KEEP)
- Safe auto-apply floor = the **541 both-agree-FIX-same-value** tokens, applied as a **reversible** correction layer (OCR system-of-record never destructively overwritten).

## 🏁 Local model benchmark (13 models, OCR-garbage detection)
- **11 of 13 hit 100% recall.** Winners: **aya-expanse:32b** (95% R / **100% P**), **gemma3:27b** (100% R / 87% P), **phi4-mini** (2.5 GB, 100% R, **0.8 s/act**).
- Thinking models added nothing — same precision, up to **14× slower**.

## 🩺 Corpus health (coherence sample)
- Layer-1 deterministic scan: **75,340 acts, zero model cost**.
- Layer-2 worst-19% slice (4,410 acts): true garbage **2.3%**, citation-mangled **7.2%** → it is a *parser* fix, not re-OCR.

---

*Generated during session cc007 (Continuation 12). For methodology see the linked lesson + `docs/30_SYSTEM_DESIGN/LOCAL_MODEL_OCR_DETECTION_MATRIX.md`.*
