"""Per-frame measurement and per-capture features.

Per frame: re-locate regions, shrink by 20 %, take the per-channel median of each region
(8-bit sRGB), linearise, fit the reference-patch correction, convert to CIELAB D65.
Per capture: pad L*, a*, b* averaged over the read frames, plus hue angle and chroma.
"""
from __future__ import annotations

import numpy as np

from .colour import (apply_correction, fit_correction, lch, linear_rgb_to_lab, rgb8_to_lab,
                     srgb_to_linear)
from .quality import clip_fraction, glare_fraction, laplacian_var
from .roi import bbox, crop, shrink


def region_pixels(bgr, rect):
    return crop(bgr, rect)[..., ::-1].reshape(-1, 3)   # RGB


def measure_frame(bgr: np.ndarray, regions: dict, cfg: dict) -> dict:
    """regions: located (shifted, unshrunk) regions. Returns a JSON-friendly dict."""
    q = cfg["quality"]
    frac = cfg["roi"]["shrink_frac"]
    out = {"raw_rgb": {}, "raw_lab": {}, "corr_lab": {}}
    lin = {}
    pix = {}
    for name, rect in regions.items():
        if name == "anchor":
            continue
        px = region_pixels(bgr, shrink(rect, frac))
        pix[name] = px
        med = np.median(px, axis=0) if len(px) else np.zeros(3)
        out["raw_rgb"][name] = [round(float(v), 2) for v in med]
        out["raw_lab"][name] = [round(float(v), 3) for v in rgb8_to_lab(med)]
        lin[name] = srgb_to_linear(med / 255.0)
    corr = fit_correction(lin["black"], lin["grey"], lin["white"],
                          mode=cfg.get("correction_mode", "three_point"))
    out["correction"] = corr
    for name, l in lin.items():
        out["corr_lab"][name] = [round(float(v), 3) for v in linear_rgb_to_lab(apply_correction(l, corr))]
    out["white_clip_frac"] = clip_fraction(pix["white"], q["clip_level"])
    # Glare = specular highlight: brighter than the matte white reference patch (plus a margin),
    # never below glare_level, and anything at the clip level counts. A white 0 mg/L pad is
    # about as bright as the white patch, so it is not glare.
    white_max = float(np.max(np.median(pix["white"], axis=0))) if len(pix["white"]) else 255.0
    glare_lvl = min(float(q["clip_level"]), max(float(q["glare_level"]), white_max + float(q.get("glare_margin", 10))))
    out["glare_level_used"] = glare_lvl
    out["pad_glare_frac"] = glare_fraction(pix["nitrate_pad"], glare_lvl, q["glare_sat_max"])
    box = bbox([regions[k] for k in ("nitrate_pad", "white", "grey", "black")])
    out["sharpness"] = laplacian_var(crop(bgr, box))
    gC, _ = lch(np.array(out["corr_lab"]["grey"]))
    out["grey_chroma"] = float(gC)
    return out


def capture_features(read_measurements: list[dict]) -> dict:
    """Average the corrected pad Lab over the read frames."""
    pads = np.array([m["corr_lab"]["nitrate_pad"] for m in read_measurements], dtype=np.float64)
    lab = pads.mean(axis=0)
    C, h = lch(lab)
    f = {"pad_L": float(lab[0]), "pad_a": float(lab[1]), "pad_b": float(lab[2]),
         "pad_C": float(C), "pad_h": float(h), "n_frames": len(read_measurements)}
    if all("nitrite_pad" in m["corr_lab"] for m in read_measurements):
        n = np.array([m["corr_lab"]["nitrite_pad"] for m in read_measurements]).mean(axis=0)
        nC, nh = lch(n)
        f.update({"nitrite_L": float(n[0]), "nitrite_a": float(n[1]), "nitrite_b": float(n[2]),
                  "nitrite_C": float(nC), "nitrite_h": float(nh)})  # logged only
    return f
