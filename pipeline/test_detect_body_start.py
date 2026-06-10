"""
test_detect_body_start.py -- Unit tests for the short-volume fix in detect_body_start().
=========================================================================================
Tests the classifier bug fix: detect_body_start() previously returned a hardcoded
fallback of 30 when the mid-range density window was empty (which happens for any
volume shorter than ~10 pages).  For a 4-6 page volume, body_start=30 exceeds
total_pages, yielding an empty body list and silently skipping all OCR.

Fix: volumes with <=12 pages return body_start=0 immediately (short-volume fast path).
Fallback when mid is empty but total_pages > 12: clamp to min(30, total_pages-1).

These tests are self-contained: they create minimal 1x1 PNG images in a temp dir
so cv2.imread/ink_density work without any real PDF or OCR infrastructure.

Run:  python -m pytest pipeline/test_detect_body_start.py -v
"""

import sys
import os
import tempfile
import datetime
from pathlib import Path

import numpy as np
import cv2
import pytest


# ---------------------------------------------------------------------------
# Inline implementations (copied from the fixed scripts so the test does not
# import the scripts directly -- they have top-level side effects on import:
# env vars, sys.argv checks, GPU model loads, etc.)
# ---------------------------------------------------------------------------

def _ink_density(img_path):
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    return float((img < 128).sum()) / (img.shape[0] * img.shape[1])


def _make_fake_log():
    """Return a log function that collects messages for inspection."""
    calls = []
    def log(phase, description, status="OK"):
        calls.append((phase, description, status))
    return log, calls


def _detect_body_start(total_pages, prep_dir, log_fn):
    """
    Faithful copy of the FIXED detect_body_start() from both ocr_only scripts.
    Uses log_fn instead of the module-level log() so we can capture output.
    """
    SHORT_VOLUME_THRESHOLD = 12
    if total_pages <= SHORT_VOLUME_THRESHOLD:
        log_fn("STAGE3-CLASSIFY",
               f"Short volume detected ({total_pages} pages <= {SHORT_VOLUME_THRESHOLD}) "
               f"-- treating all pages as body (body_start=0)", "WARN")
        return 0

    densities = []
    for pidx in range(min(80, total_pages)):
        p = prep_dir / f"page_{pidx:04d}.png"
        densities.append(_ink_density(p) if p.exists() else 0.0)
    mid = [densities[i] for i in range(min(10, len(densities)), min(40, len(densities)))
           if densities[i] > 0.005]
    if not mid:
        fallback = min(30, max(0, total_pages - 1))
        log_fn("STAGE3-CLASSIFY",
               f"No mid-range density signal (mid empty) -- using clamped fallback body_start={fallback} "
               f"(total_pages={total_pages})", "WARN")
        return fallback
    med_d = float(np.median(mid))
    threshold = med_d * 0.30
    consecutive = 0
    for pidx in range(total_pages):
        d = densities[pidx] if pidx < len(densities) else 0.05
        if d >= threshold:
            consecutive += 1
            if consecutive >= 4:
                return max(0, pidx - 3)
        else:
            consecutive = 0
    return 0


# ---------------------------------------------------------------------------
# Helpers to create fake PNG pages in a temp directory
# ---------------------------------------------------------------------------

def _write_page(prep_dir: Path, pidx: int, ink_fraction: float):
    """
    Write a 10x10 grayscale PNG where ink_fraction of pixels are black (0)
    and the rest are white (255).  cv2.imread in GRAYSCALE + (img < 128).sum()
    will return exactly ink_fraction as ink_density.
    """
    total_pixels = 100  # 10*10
    n_dark = int(round(ink_fraction * total_pixels))
    pixels = np.array([0] * n_dark + [255] * (total_pixels - n_dark), dtype=np.uint8)
    np.random.shuffle(pixels)
    img = pixels.reshape(10, 10)
    path = prep_dir / f"page_{pidx:04d}.png"
    cv2.imwrite(str(path), img)
    return path


def _write_normal_volume_pages(prep_dir: Path, total_pages: int):
    """
    Simulate a normal full volume: pages 0-9 = low density (0.01, front matter),
    pages 10+ = high density (0.10, body text).
    The density-scan logic should detect body start at page 10.
    """
    for pidx in range(min(80, total_pages)):
        density = 0.01 if pidx < 10 else 0.10
        _write_page(prep_dir, pidx, density)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestShortVolumeFixBug:
    """
    Regression tests for the bug: detect_body_start() returned 30 for short
    volumes, causing body_pages=[] and silent OCR skip.
    """

    def test_4_page_volume_returns_zero(self, tmp_path):
        """
        BUG REPRODUCTION (1926 extra session): 4-page volume previously returned 30.
        Fixed: short-volume path returns 0.
        """
        # No PNGs needed -- the short-volume fast path fires before any file I/O.
        log_fn, calls = _make_fake_log()
        result = _detect_body_start(4, tmp_path, log_fn)
        assert result == 0, f"Expected body_start=0 for 4-page volume, got {result}"
        # Confirm warning was logged
        assert any("Short volume" in desc for _, desc, _ in calls), \
            "Expected 'Short volume' warning in log"
        assert any(status == "WARN" for _, _, status in calls), \
            "Expected WARN status for short-volume path"

    def test_6_page_volume_returns_zero(self, tmp_path):
        """
        BUG REPRODUCTION (1928 extra session): 6-page volume previously returned 30.
        Fixed: short-volume path returns 0.
        """
        log_fn, calls = _make_fake_log()
        result = _detect_body_start(6, tmp_path, log_fn)
        assert result == 0
        assert any("Short volume" in desc for _, desc, _ in calls)

    def test_12_page_volume_returns_zero(self, tmp_path):
        """Boundary: exactly at the threshold still takes the short-volume path."""
        log_fn, _ = _make_fake_log()
        result = _detect_body_start(12, tmp_path, log_fn)
        assert result == 0

    def test_4_page_body_list_nonempty(self, tmp_path):
        """
        End-to-end: for a 4-page volume with body_start=0, the body_candidates
        list is range(0, 4) = [0,1,2,3], which is non-empty.
        (Verifies the fix resolves the original empty-body symptom.)
        """
        log_fn, _ = _make_fake_log()
        body_start = _detect_body_start(4, tmp_path, log_fn)
        total_pages = 4
        body_candidates = list(range(body_start, total_pages))
        assert len(body_candidates) > 0, "body_candidates must be non-empty after fix"
        assert body_candidates == [0, 1, 2, 3]


class TestNormalVolumeUnchanged:
    """
    Confirm the fix does NOT affect normal full volumes (hundreds of pages).
    """

    def test_13_page_volume_uses_density_scan(self, tmp_path):
        """
        Just above the threshold (13 pages): should use density scan, not short-volume path.
        With no PNG files present, mid will be empty -> falls to clamped fallback (12).
        Key: does NOT return 30 (unclamped old behavior) or 0 (short-volume path).
        """
        log_fn, calls = _make_fake_log()
        result = _detect_body_start(13, tmp_path, log_fn)
        # No PNGs -> densities all 0.0 -> mid empty -> clamped fallback = min(30, 12) = 12
        assert result == 12
        assert not any("Short volume" in desc for _, desc, _ in calls), \
            "Short-volume path must NOT fire for 13-page volume"

    def test_normal_volume_body_start_detected_by_density(self, tmp_path):
        """
        A 100-page volume with realistic front-matter + body density pattern:
        pages 0-9 low density, pages 10+ high density.
        detect_body_start should return 10 (or close -- consecutive logic
        fires when 4 consecutive high pages seen, so pidx=13 -> return pidx-3=10).
        """
        total_pages = 100
        _write_normal_volume_pages(tmp_path, total_pages)
        log_fn, calls = _make_fake_log()
        result = _detect_body_start(total_pages, tmp_path, log_fn)
        assert result == 10, f"Expected body_start=10, got {result}"
        assert not any("Short volume" in desc for _, desc, _ in calls)
        assert not any("WARN" == status for _, _, status in calls)

    def test_large_volume_body_start_within_page_count(self, tmp_path):
        """
        body_start must always be < total_pages for any volume >= 13 pages.
        Smoke test with 200 pages, all low density (degenerate case).
        Clamped fallback fires; result must be < 200.
        """
        log_fn, _ = _make_fake_log()
        # No PNGs: all densities 0 -> mid empty -> fallback = min(30, 199) = 30
        result = _detect_body_start(200, tmp_path, log_fn)
        assert result < 200, f"body_start={result} must be < 200"
        assert result == 30  # clamped fallback for large page count


class TestFallbackClamping:
    """
    Verify the secondary defense: even for volumes > 12 pages with an empty
    mid-density list, the fallback is clamped to total_pages-1, not hardcoded 30.
    """

    def test_fallback_clamped_for_midsize_volume(self, tmp_path):
        """
        A 20-page volume with no PNGs: mid empty, fallback = min(30, 19) = 19.
        Old code returned 30 (exceeds 20 pages, body_candidates empty).
        """
        log_fn, _ = _make_fake_log()
        result = _detect_body_start(20, tmp_path, log_fn)
        assert result == 19, f"Expected clamped fallback 19 for 20-page volume, got {result}"
        assert result < 20

    def test_fallback_clamped_for_large_volume(self, tmp_path):
        """
        200-page volume, no PNGs: fallback = min(30, 199) = 30.
        Old and new behavior identical for large volumes -- this is unchanged.
        """
        log_fn, _ = _make_fake_log()
        result = _detect_body_start(200, tmp_path, log_fn)
        assert result == 30


if __name__ == "__main__":
    # Allow running directly: python pipeline/test_detect_body_start.py
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))
