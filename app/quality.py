"""Quality gate. Every check returns pass/fail plus the measured value and threshold.

Any failed check -> the decision is UNKNOWN (decision rule 2).
Thresholds come from config.yaml `quality:` and are frozen into the model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .colour import delta_e2000


@dataclass
class Check:
    name: str
    passed: bool
    value: float | None
    threshold: str
    reason: str = ""

    def to_dict(self):
        d = asdict(self)
        if isinstance(d["value"], (np.floating, np.integer)):
            d["value"] = float(d["value"])
        return d


# ---------------------------------------------------------------- pixel measures

def clip_fraction(px_rgb8: np.ndarray, clip_level: int) -> float:
    px = px_rgb8.reshape(-1, 3)
    if len(px) == 0:
        return 1.0
    return float(np.mean(np.any(px >= clip_level, axis=1)))


def glare_fraction(px_rgb8: np.ndarray, level: int, sat_max: float) -> float:
    """Fraction of near-saturated, low-chroma pixels (specular reflection off a wet pad)."""
    px = px_rgb8.reshape(-1, 3).astype(np.float64)
    if len(px) == 0:
        return 1.0
    mx = px.max(axis=1)
    mn = px.min(axis=1)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    return float(np.mean((mx >= level) & (sat <= sat_max)))


def laplacian_var(bgr: np.ndarray) -> float:
    if bgr.size == 0:
        return 0.0
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


# ---------------------------------------------------------------- checks

def check_light_leak(black_L: list[float], q: dict) -> Check:
    """black_L: raw black-patch L* of every monitored frame, in time order."""
    if not black_L:
        return Check("light_leak", False, None, "", "no frames to check")
    mx = float(max(black_L))
    jump = float(max(np.abs(np.diff(black_L)))) if len(black_L) > 1 else 0.0
    thr = f"black L* <= {q['black_L_max']}, jump <= {q['black_jump_max']}"
    if mx > q["black_L_max"]:
        return Check("light_leak", False, mx, thr, f"light leak: black patch L* {mx:.1f} > {q['black_L_max']}")
    if jump > q["black_jump_max"]:
        return Check("light_leak", False, jump, thr,
                     f"light leak: black patch jumped {jump:.1f} L* between frames (drawer/seam?)")
    return Check("light_leak", True, mx, thr)


def check_exposure(white_L: float, clip_frac: float, q: dict) -> Check:
    thr = f"{q['white_L_min']} <= white L* <= {q['white_L_max']}, clipped < {q['white_clip_frac_max']:.0%}"
    if not (q["white_L_min"] <= white_L <= q["white_L_max"]):
        return Check("exposure", False, white_L, thr, f"exposure: white patch L* {white_L:.1f} out of range")
    if clip_frac >= q["white_clip_frac_max"]:
        return Check("exposure", False, clip_frac, thr, f"exposure: {clip_frac:.1%} of white patch clipped")
    return Check("exposure", True, white_L, thr)


def check_glare(glare_frac: float, q: dict) -> Check:
    thr = f"glare fraction <= {q['glare_frac_max']}"
    if glare_frac > q["glare_frac_max"]:
        return Check("glare", False, glare_frac, thr, f"glare on pad: {glare_frac:.1%} of pixels")
    return Check("glare", True, glare_frac, thr)


def check_blur(lapvar: float, q: dict) -> Check:
    thr = f"Laplacian variance >= {q['blur_min']}"
    if lapvar < q["blur_min"]:
        return Check("blur", False, lapvar, thr, f"blurred image (sharpness {lapvar:.1f})")
    return Check("blur", True, lapvar, thr)


def check_timing(first_read_elapsed: float, read_time_s: float) -> Check:
    thr = f"read at >= {read_time_s} s"
    if first_read_elapsed + 1e-6 < read_time_s:
        return Check("timing", False, first_read_elapsed, thr,
                     f"read too early ({first_read_elapsed:.1f} s < {read_time_s} s)")
    return Check("timing", True, first_read_elapsed, thr)


def check_drift(pad_labs: list, q: dict) -> Check:
    """Max pairwise dE00 of the corrected pad colour across the read frames."""
    thr = f"pad drift <= {q['drift_max_dE']} dE00"
    if len(pad_labs) < 2:
        return Check("drift", False, None, thr, "fewer than 2 read frames")
    labs = np.asarray(pad_labs)
    d = max(float(delta_e2000(labs[i], labs[j])) for i in range(len(labs)) for j in range(i + 1, len(labs)))
    if d > q["drift_max_dE"]:
        return Check("drift", False, d, thr, f"still developing: pad colour drifted {d:.1f} dE00")
    return Check("drift", True, d, thr)


def check_strip_present(dE_vs_empty: float | None, absdiff: float | None, q: dict) -> Check:
    thr = f"dE00 vs empty tray >= {q['strip_min_dE']} or abs diff >= {q['strip_min_absdiff']}"
    if dE_vs_empty is None:
        return Check("strip_present", False, None, thr, "no empty-tray reference; recalibrate ROI")
    if dE_vs_empty >= q["strip_min_dE"] or (absdiff is not None and absdiff >= q["strip_min_absdiff"]):
        return Check("strip_present", True, dE_vs_empty, thr)
    return Check("strip_present", False, dE_vs_empty, thr, "no strip in the tray (pad looks like the empty tray)")


def check_phone(errors: list[str], latencies: list[float], q: dict) -> Check:
    thr = f"no HTTP errors, frame age <= {q['max_frame_age_s']} s"
    if errors:
        return Check("phone", False, len(errors), thr, f"phone unreachable / stale frame: {errors[0]}")
    if not latencies:
        return Check("phone", False, None, thr, "no frames received")
    mx = float(max(latencies))
    if mx > q["max_frame_age_s"]:
        return Check("phone", False, mx, thr, f"frame too old ({mx:.1f} s)")
    return Check("phone", True, mx, thr)


def check_seated(located_ok: list[bool], reasons: list[str]) -> Check:
    if all(located_ok) and located_ok:
        return Check("seated", True, 1.0, "regions re-located within tolerance")
    r = next((x for x in reasons if x), "re-location failed")
    return Check("seated", False, 0.0, "regions re-located within tolerance", r)


def check_reference(grey_chroma: float, q: dict) -> Check:
    thr = f"grey patch chroma after correction <= {q['grey_chroma_max']}"
    if grey_chroma > q["grey_chroma_max"]:
        return Check("reference", False, grey_chroma, thr,
                     f"reference patches inconsistent (grey chroma {grey_chroma:.1f}); patches dirty or covered?")
    return Check("reference", True, grey_chroma, thr)


def gate(checks: list[Check]) -> tuple[bool, list[str]]:
    failed = [c.reason or c.name for c in checks if not c.passed]
    return (not failed), failed
