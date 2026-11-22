"""Regions of interest: load/save, re-location with small-shift tolerance, shrink."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import ROOT, file_hash, stable_hash

REQUIRED = ["nitrate_pad", "white", "grey", "black"]
OPTIONAL = ["nitrite_pad", "anchor"]
PATCHES = ["white", "grey", "black"]


def shrink(rect, frac: float):
    x, y, w, h = rect
    dx, dy = w * frac, h * frac
    return [int(round(x + dx)), int(round(y + dy)),
            max(1, int(round(w - 2 * dx))), max(1, int(round(h - 2 * dy)))]


def crop(img, rect):
    x, y, w, h = (int(v) for v in rect)
    H, W = img.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return img[0:0, 0:0]
    return img[y0:y1, x0:x1]


def bbox(rects):
    xs = [r[0] for r in rects] + [r[0] + r[2] for r in rects]
    ys = [r[1] for r in rects] + [r[1] + r[3] for r in rects]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def offset(rect, dx, dy):
    return [rect[0] + dx, rect[1] + dy, rect[2], rect[3]]


def load_roi(path: Path) -> dict | None:
    if not path.exists():
        return None
    roi = json.loads(path.read_text())
    for k in REQUIRED:
        if k not in roi.get("regions", {}):
            raise ValueError(f"roi.json is missing region {k!r}")
    return roi


def roi_hash(roi: dict) -> str:
    ref = roi.get("reference_frame")
    ref_h = ""
    if ref and (ROOT / ref).exists():
        ref_h = file_hash(ROOT / ref)[:16]
    return stable_hash({"regions": roi["regions"], "frame_size": roi.get("frame_size"),
                        "ref": ref_h})


def save_roi(path: Path, regions: dict, frame_bgr: np.ndarray, empty_bgr: np.ndarray | None = None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    ref_name = "roi_reference.jpg"
    cv2.imwrite(str(path.parent / ref_name), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    roi = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "frame_size": [int(frame_bgr.shape[1]), int(frame_bgr.shape[0])],
        "reference_frame": str((path.parent / ref_name).relative_to(ROOT)).replace("\\", "/"),
        "regions": {k: [int(v) for v in r] for k, r in regions.items()},
    }
    if empty_bgr is not None:
        cv2.imwrite(str(path.parent / "empty_tray.jpg"), empty_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        roi["empty_tray_frame"] = str((path.parent / "empty_tray.jpg").relative_to(ROOT)).replace("\\", "/")
    path.write_text(json.dumps(roi, indent=1))
    return roi


@dataclass
class Located:
    ok: bool
    regions: dict            # shifted (not shrunk) regions
    patch_shift: tuple
    strip_shift: tuple
    patch_score: float
    strip_score: float | None
    reason: str


def _match(ref_gray, cur_gray, rect, search):
    """Find rect's template from ref in cur, searching +-search px. Returns (dx, dy, score)."""
    tmpl = crop(ref_gray, rect)
    if tmpl.size == 0:
        return 0, 0, 0.0
    x, y, w, h = rect
    win = [x - search, y - search, w + 2 * search, h + 2 * search]
    H, W = cur_gray.shape[:2]
    wx0, wy0 = max(0, win[0]), max(0, win[1])
    area = crop(cur_gray, win)
    if area.shape[0] < h or area.shape[1] < w:
        return 0, 0, 0.0
    if float(tmpl.std()) < 1e-3:
        return 0, 0, 0.0
    res = cv2.matchTemplate(area, tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    dx = wx0 + loc[0] - x
    dy = wy0 + loc[1] - y
    return int(dx), int(dy), float(score)


def locate(roi: dict, ref_bgr: np.ndarray, cur_bgr: np.ndarray, tol: int = 15, search: int = 30,
           min_score: float = 0.6, strip_tol: int | None = None, strip_min_score: float = 0.75) -> Located:
    """Re-locate the regions. Patch row (tray/camera) must move <= tol. The strip tip (anchor) may
    move <= tol with score >= min_score, or up to strip_tol when its match is strong
    (score >= strip_min_score), D-39/D-44. strip_tol None = same as tol (original behaviour)."""
    regs = roi["regions"]
    ref_g = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    cur_g = cv2.cvtColor(cur_bgr, cv2.COLOR_BGR2GRAY)
    if ref_g.shape != cur_g.shape:
        return Located(False, regs, (0, 0), (0, 0), 0.0, None,
                       f"frame size {cur_g.shape[::-1]} differs from calibration {ref_g.shape[::-1]}")
    prow = bbox([regs[k] for k in PATCHES])
    pdx, pdy, pscore = _match(ref_g, cur_g, prow, search)
    out = {k: offset(r, pdx, pdy) for k, r in regs.items()}
    sdx, sdy, sscore = pdx, pdy, None
    reasons = []
    if pscore < min_score:
        reasons.append(f"reference patches not found (match {pscore:.2f}); camera or dock moved, or light changed")
    elif max(abs(pdx), abs(pdy)) > tol:
        reasons.append(f"camera/dock moved {max(abs(pdx), abs(pdy))} px (> {tol}); strip not seated")
    if "anchor" in regs:
        sdx, sdy, sscore = _match(ref_g, cur_g, regs["anchor"], search)
        smax = max(abs(sdx), abs(sdy))
        wide = tol if strip_tol is None else max(tol, int(strip_tol))
        if sscore < min_score:
            reasons.append(f"strip anchor not found (match {sscore:.2f}); strip not seated")
        elif smax > wide:
            reasons.append(f"strip moved {smax} px (> {wide}); strip not seated")
        elif smax > tol and sscore < strip_min_score:
            reasons.append(f"strip moved {smax} px (> {tol}) with a weak tip match "
                           f"({sscore:.2f} < {strip_min_score}); strip not seated")
        for k in ("nitrate_pad", "nitrite_pad", "anchor"):
            if k in regs:
                out[k] = offset(regs[k], sdx, sdy)
    return Located(not reasons, out, (pdx, pdy), (sdx, sdy), pscore, sscore, "; ".join(reasons))


def locate_cfg(roi: dict, ref_bgr: np.ndarray, cur_bgr: np.ndarray, rc: dict) -> Located:
    """locate() with the tolerances from config.yaml's `roi:` section."""
    return locate(roi, ref_bgr, cur_bgr, int(rc["shift_tol_px"]), int(rc["search_px"]),
                  float(rc["min_match_score"]), rc.get("strip_tol_px"), float(rc.get("strip_min_score", 0.75)))
