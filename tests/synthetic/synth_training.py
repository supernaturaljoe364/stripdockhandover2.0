"""SYNTHETIC training set builder (software tests only; never written to data/)."""
from __future__ import annotations

import numpy as np
from synth import pad_lab, render, roi_dict

from app.features import capture_features, measure_frame
from app.roi import locate

STANDARDS = [0, 10, 25, 35, 45, 55, 100]


def synthetic_samples(cfg, strips_per_standard=3, seed0=100, standards=STANDARDS):
    ref = render(25, seed=1)
    roi = roi_dict()
    out = []
    k = 0
    rng = np.random.default_rng(seed0)
    for c in standards:
        for s in range(strips_per_standard):
            k += 1
            # strip-to-strip variation: small random exposure / cast change
            ex = 1.0 + 0.02 * ((k * 37) % 5 - 2)
            pl = pad_lab(c) + rng.normal(0, 0.8, 3)     # strip-to-strip chemistry spread
            ms = []
            for i in range(3):
                f = render(c, seed=seed0 + 10 * k + i, exposure=ex, pad_lab_override=pl)
                loc = locate(roi, ref, f)
                ms.append(measure_frame(f, loc.regions, cfg))
            fe = capture_features(ms)
            out.append({"sample_id": f"SYN_{c}_{s}", "conc": float(c),
                        "lab": [fe["pad_L"], fe["pad_a"], fe["pad_b"]], "session": "SYNTHETIC"})
    return out
