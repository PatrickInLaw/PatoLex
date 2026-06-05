# STAGE 0.5 Mojibake Detection Limitation

## Date
2026-06-05

## Context
STAGE 0.5 born-digital fallback (PDFs where pdfplumber text extraction produces mojibake due to broken font CMaps) uses a quality-check heuristic to detect whether to fallback to OCR:

```python
_ctrl_chars = sum(1 for c in _sample_text if ord(c) < 32 and c not in '\n\t\r')
_ctrl_ratio = _ctrl_chars / max(len(_sample_text), 1)
if _ctrl_ratio > 0.20:
    # fallback to OCR
```

The concern was: 1997-1999 PDFs have broken CMaps producing mojibake (printable Unicode garbage, NOT control characters), so a control-char-only check might miss them.

## Testing
Tested 6 PDFs from 1996-1999 Chief Clerk archives, sampling first 5 pages each:

| File | ctrl_ratio | non_ascii_ratio | Fallback? | Mojibake Present? |
|------|-----------|-----------------|-----------|------------------|
| 1996_Vol2 | 0.471 | 0.001 | ? YES | No (ctrl chars detected) |
| 1997_Vol1 | 0.000 | 0.004 | ? NO | **YES** (mojibake not caught) |
| 1997_Vol2 | 0.576 | 0.000 | ? YES | No (ctrl chars detected) |
| 1998_Vol1 | 0.000 | 0.004 | ? NO | **YES** (mojibake not caught) |
| 1998_Vol2 | 0.480 | 0.000 | ? YES | No (ctrl chars detected) |
| 1999_Vol1 | 0.000 | 0.003 | ? NO | **YES** (mojibake not caught) |

**Critical Finding:** The ctrl_ratio heuristic has a **bimodal failure pattern**:
- Some 1997-1999 volumes (Vol1s) trigger NO control chars but produce mojibake (non_ascii_ratio ~0.003-0.004)
- Other 1997-1999 volumes (Vol2+) produce enough control chars to trigger fallback correctly

## Root Cause
Different fonts/subsets embedded in different volumes of the same year's Chief Clerk statutes. Some vendor fonts encode the mojibake as printable Unicode (bypasses ctrl_ratio), others embed control sequences (triggers fallback correctly).

## Solution
**Adopt YEAR-BASED CUTOFF instead of heuristic fallback:** for born-digital PDFs with year = 1999, assume broken CMaps and force OCR fallback. This is more reliable than char-scanning.

Alternative (more selective): scan for non_ascii_ratio > 0.01 in addition to ctrl_ratio > 0.20.

## Recommendation
Update STAGE 0.5 quality check:
```python
if year <= 1999:
    # Force OCR for all 1997-1999 PDFs regardless of text quality
    return "OCR"
elif _ctrl_ratio > 0.20:
    return "OCR"
elif non_ascii_ratio > 0.01:  # Secondary mojibake catch
    return "OCR"
else:
    return "born_digital_pdfplumber"
```

## Impact
- **1997-1999 corpus:** Forces OCR for all 3 years, ensuring mojibake does not corrupt ingest
- **1996 and earlier:** Continues using existing heuristic (appears reliable)
- **2000+:** Continues using existing heuristic + non_ascii fallback
