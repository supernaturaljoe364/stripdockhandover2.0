r"""Phone check: probe IP Webcam endpoints, measure latency and colour stability.

For each still endpoint (/shot.jpg, /photo.jpg) grab N frames and report resolution,
latency, and colour stability = mean CIEDE2000 of a fixed central patch (raw sRGB ->
Lab) relative to the mean of the N frames. /photoaf.jpg is listed but never grabbed:
autofocus must not run once focus is locked.

Writes results/ipwebcam_status.json and results/phone_check.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.colour import delta_e2000, rgb8_to_lab  # noqa: E402
from app.config import ROOT, load_config, phone_base  # noqa: E402
from app.phone import PhoneCam, PhoneError  # noqa: E402

ENDPOINTS = ["/shot.jpg", "/photo.jpg"]


def central_lab(bgr, size=120):
    h, w = bgr.shape[:2]
    y0, x0 = h // 2 - size // 2, w // 2 - size // 2
    patch = bgr[y0:y0 + size, x0:x0 + size, ::-1].reshape(-1, 3)
    return rgb8_to_lab(np.median(patch, axis=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--max-latency", type=float, default=1.0)
    ap.add_argument("--max-dE", type=float, default=1.0)
    args = ap.parse_args()
    cfg = load_config()
    cam = PhoneCam(phone_base(cfg), timeout=10.0)

    st = cam.status(avail=True)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "ipwebcam_status.json").write_text(json.dumps(st, indent=1))
    cur = st.get("curvals", {})
    print(f"Phone {cam.base}: video_size={cur.get('video_size')} photo_size={cur.get('photo_size')} "
          f"quality={cur.get('quality')} torch={cur.get('torch')}")

    report = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "phone": cam.base, "n": args.n,
              "curvals_at_test": cur, "endpoints": {},
              "not_tested": {"/photoaf.jpg": "autofocus: never used (would break the focus lock)"}}
    for ep in ENDPOINTS:
        labs, lats, shapes, errs = [], [], set(), []
        for _ in range(args.n):
            try:
                fr = cam.grab(ep, timeout=10.0, check_fresh=False)
            except PhoneError as e:
                errs.append(str(e))
                continue
            labs.append(central_lab(fr.bgr))
            lats.append(fr.latency)
            shapes.add(f"{fr.bgr.shape[1]}x{fr.bgr.shape[0]}")
            time.sleep(0.2)
        if not labs:
            report["endpoints"][ep] = {"available": False, "errors": errs[:3]}
            print(f"{ep}: NOT available ({errs[:1]})")
            continue
        labs = np.array(labs)
        mean_lab = labs.mean(axis=0)
        dE = delta_e2000(labs, mean_lab)
        r = {"available": True, "resolution": sorted(shapes), "frames": len(labs),
             "latency_mean_s": float(np.mean(lats)), "latency_max_s": float(np.max(lats)),
             "dE00_mean": float(dE.mean()), "dE00_max": float(dE.max()),
             "central_Lab_mean": mean_lab.round(2).tolist(), "errors": errs}
        report["endpoints"][ep] = r
        print(f"{ep}: {r['resolution']} latency mean {r['latency_mean_s']:.3f} s max "
              f"{r['latency_max_s']:.3f} s | central patch dE00 mean {r['dE00_mean']:.2f} "
              f"max {r['dE00_max']:.2f} | Lab {r['central_Lab_mean']}")

    ok = [(ep, r) for ep, r in report["endpoints"].items()
          if r.get("available") and r["latency_max_s"] <= args.max_latency and r["dE00_mean"] <= args.max_dE]
    if ok:
        choice = min(ok, key=lambda x: (x[1]["dE00_mean"] > 0.5, x[1]["latency_mean_s"]))[0]
        why = "stable colour and acceptable latency"
    else:
        avail = [(ep, r) for ep, r in report["endpoints"].items() if r.get("available")]
        choice = min(avail, key=lambda x: x[1]["dE00_mean"])[0] if avail else None
        why = "no endpoint met both limits; picked the most stable (re-run with the camera locked)"
    report["choice"] = choice
    report["choice_reason"] = why
    (ROOT / "results" / "phone_check.json").write_text(json.dumps(report, indent=1))
    print(f"\nChoice: {choice} ({why}). Saved results/phone_check.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
