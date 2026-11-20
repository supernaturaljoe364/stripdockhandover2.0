"""Colour maths: sRGB <-> linear, CIELAB (D65), CIEDE2000, reference-patch correction.

All functions take RGB order (not OpenCV's BGR). Values are floats in 0..1 unless noted.
"""
from __future__ import annotations

import numpy as np

D65_WHITE = np.array([0.95047, 1.0, 1.08883])
_M_RGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])

WHITE_TARGET = 0.85  # linear value the white patch is normalised to


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def linear_rgb_to_lab(rgb_lin):
    """Linear sRGB (..., 3) -> CIELAB D65 (..., 3)."""
    rgb_lin = np.clip(np.asarray(rgb_lin, dtype=np.float64), 0.0, None)
    xyz = rgb_lin @ _M_RGB2XYZ.T
    t = xyz / D65_WHITE
    eps = (6 / 29) ** 3
    f = np.where(t > eps, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def rgb8_to_lab(rgb8):
    """8-bit sRGB (..., 3) -> Lab, with no correction."""
    return linear_rgb_to_lab(srgb_to_linear(np.asarray(rgb8, dtype=np.float64) / 255.0))


def lch(lab):
    lab = np.asarray(lab, dtype=np.float64)
    C = np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    return C, h


def delta_e2000(lab1, lab2, kL=1.0, kC=1.0, kH=1.0):
    """CIEDE2000 colour difference (Sharma et al. 2005). Broadcasts over leading dims."""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    h1p = np.where((a1p == 0) & (b1 == 0), 0.0, h1p)
    h2p = np.where((a2p == 0) & (b2 == 0), 0.0, h2p)

    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2)

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) > 180,
                   np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2),
                   hsum / 2)
    hbp = np.where(C1p * C2p == 0, hsum, hbp)

    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / (kL * Sl)) ** 2 + (dCp / (kC * Sc)) ** 2 + (dHp / (kH * Sh)) ** 2
                   + Rt * (dCp / (kC * Sc)) * (dHp / (kH * Sh)))


# ---------------------------------------------------------------- correction

def fit_correction(black_lin, grey_lin, white_lin, min_span=0.05, max_resid=0.03, mode="three_point"):
    """Fit the per-channel correction from the three reference patches.

    Step 1: per-channel gain from the white patch so white -> WHITE_TARGET (neutral).
    Step 2: if stable, a per-channel affine fit (gain + offset) through black, grey and
    white, mapping each patch to its own achromatic level after step 1. This makes all
    three patches neutral, which also corrects a colour cast in the darker tones (e.g.
    tinted stray light). Stable = for every channel white > grey > black,
    white - black >= min_span, and the fit residual <= max_resid.
    Returns a dict that apply_correction() understands.
    """
    k = np.asarray(black_lin, dtype=np.float64)
    g = np.asarray(grey_lin, dtype=np.float64)
    w = np.asarray(white_lin, dtype=np.float64)
    if np.any(w <= 1e-4):
        return {"method": "invalid", "reason": "white patch too dark", "gain": [1, 1, 1],
                "offset": [0, 0, 0]}
    gain = WHITE_TARGET / w
    corr = {"method": "white_gain", "gain": gain.tolist(), "offset": [0.0, 0.0, 0.0],
            "reason": ""}
    if mode == "white_gain":
        corr["reason"] = "white gain only (config correction_mode)"
        return corr

    ordered = bool(np.all(w > g) and np.all(g > k) and np.all(w - k >= min_span))
    if not ordered:
        corr["reason"] = "3-point fit skipped: patches not ordered/separated in every channel"
        return corr

    # achromatic targets: mean over channels of the white-gained patch values
    targets = np.array([np.mean(k * gain), np.mean(g * gain), WHITE_TARGET])
    X = np.stack([k, g, w])  # rows: black, grey, white; cols: channels
    gains3, offs3, resid = [], [], []
    for c in range(3):
        A = np.stack([X[:, c], np.ones(3)], axis=1)
        sol, *_ = np.linalg.lstsq(A, targets, rcond=None)
        pred = A @ sol
        gains3.append(sol[0])
        offs3.append(sol[1])
        resid.append(float(np.max(np.abs(pred - targets))))
    if max(resid) > max_resid or min(gains3) <= 0:
        corr["reason"] = f"3-point fit unstable (residual {max(resid):.3f}); white gain used"
        return corr
    return {"method": "three_point", "gain": [float(x) for x in gains3],
            "offset": [float(x) for x in offs3], "reason": "",
            "fit_residual": max(resid), "targets": targets.tolist()}


def apply_correction(rgb_lin, corr):
    rgb_lin = np.asarray(rgb_lin, dtype=np.float64)
    return np.clip(rgb_lin * np.asarray(corr["gain"]) + np.asarray(corr["offset"]), 0.0, None)
