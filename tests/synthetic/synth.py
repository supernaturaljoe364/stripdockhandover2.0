"""SYNTHETIC test images for software tests ONLY.

Nothing generated here may be copied into data/ or reported as a result. The pad colour
model below is invented (white -> magenta in log concentration) purely to exercise the
code paths; it is not the eSHa strip's real response.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

SYNTHETIC_MARK = "SYNTHETIC - software test only"

_M_XYZ2RGB = np.linalg.inv(np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
]))
D65 = np.array([0.95047, 1.0, 1.08883])

# layout (1920x1080)
REGIONS = {
    "white": [300, 420, 160, 160],
    "grey": [500, 420, 160, 160],
    "black": [700, 420, 160, 160],
    "nitrate_pad": [1010, 260, 110, 110],
    "nitrite_pad": [1010, 400, 110, 110],
    "anchor": [985, 190, 160, 60],
}
STRIP = [1000, 220, 130, 760]

PAD_WHITE = np.array([92.0, 2.0, 3.0])
PAD_MAGENTA = np.array([55.0, 48.0, -14.0])


def lab_to_linear(lab):
    lab = np.asarray(lab, dtype=np.float64)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    d = 6 / 29

    def finv(f):
        return np.where(f > d, f ** 3, 3 * d * d * (f - 4 / 29))
    xyz = np.stack([finv(fx), finv(fy), finv(fz)], axis=-1) * D65
    return np.clip(xyz @ _M_XYZ2RGB.T, 0, None)


def lin_to_srgb8(lin):
    lin = np.clip(lin, 0, 1)
    s = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(np.round(s * 255), 0, 255).astype(np.uint8)


def pad_lab(conc: float) -> np.ndarray:
    """Invented monotonic pad response: 0 -> white, 500 -> magenta (log scale)."""
    t = min(1.0, math.log(conc + 1) / math.log(501))
    return PAD_WHITE + t * (PAD_MAGENTA - PAD_WHITE)


def render(conc: float | None = 25.0, *, cast=(1.0, 1.0, 1.0), exposure=1.0, stray=0.0,
           noise=2.0, blur=0.0, glare=0.0, shift=(0, 0), strip_shift=(0, 0), seed=0,
           pad_lab_override=None, size=(1920, 1080)) -> np.ndarray:
    """Return a BGR uint8 synthetic dock frame.

    conc None = empty tray. cast = per-channel illuminant gain. exposure = global gain.
    stray = added linear light (light leak). glare = fraction of the pad covered by a
    specular highlight. shift = whole-scene shift (phone moved); strip_shift = strip only.
    """
    rng = np.random.default_rng(seed)
    W, H = size
    lin = np.zeros((H, W, 3))
    lin[:] = lab_to_linear([6.0, 0.0, 0.0])          # black foam tray
    ref = {"white": [95.0, 0, 0], "grey": [55.0, 0, 0], "black": [18.0, 0, 0]}
    for k, lab in ref.items():
        x, y, w, h = REGIONS[k]
        lin[y:y + h, x:x + w] = lab_to_linear(lab)
    if conc is not None:
        dx, dy = strip_shift
        x, y, w, h = STRIP
        lin[y + dy:y + h + dy, x + dx:x + w + dx] = lab_to_linear([96.0, 0.0, 1.0])
        x, y, w, h = REGIONS["nitrate_pad"]
        pl = pad_lab_override if pad_lab_override is not None else pad_lab(conc)
        lin[y + dy:y + h + dy, x + dx:x + w + dx] = lab_to_linear(pl)
        x, y, w, h = REGIONS["nitrite_pad"]
        lin[y + dy:y + h + dy, x + dx:x + w + dx] = lab_to_linear([93.0, 1.0, 2.0])
        if glare > 0:
            x, y, w, h = REGIONS["nitrate_pad"]
            gh = int(h * math.sqrt(glare))
            gw = int(w * math.sqrt(glare))
            lin[y + dy + 30:y + dy + 30 + gh, x + dx + 30:x + dx + 30 + gw] = 1.5
    lin = lin * np.asarray(cast)[None, None, :] * exposure + stray
    # felt texture / sensor noise in linear space
    lin = lin * (1 + rng.normal(0, 0.02, size=(H, W, 1)))
    img = lin_to_srgb8(lin)[..., ::-1].astype(np.float64)    # BGR
    img += rng.normal(0, noise, size=img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    if shift != (0, 0):
        M = np.float32([[1, 0, shift[0]], [0, 1, shift[1]]])
        img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
    return img


def roi_dict():
    return {"created": "synthetic", "frame_size": [1920, 1080], "reference_frame": None,
            "regions": {k: list(v) for k, v in REGIONS.items()}}
