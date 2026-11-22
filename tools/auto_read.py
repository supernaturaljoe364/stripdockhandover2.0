r"""Start a read through the running app (http://localhost:5000) AUTOMATICALLY when the strip
arrives in the tray, so the operator only handles the strip (DECISIONS D-42).

The operator dips, blots, puts the strip in the tray and slides the tray in. This script
watches the phone (/shot.jpg) and presses START as soon as the reference patches AND the
strip tip (ROI 'anchor') are both found and have stayed still for `--settle` seconds,
after having seen the tray without a strip (or away) first. The 60 s read timer starts at
that START, about 1-2 s after the tray is closed: the same moment an operator pressing
START "at once" would give (rule 1, D-26).

  .venv\Scripts\python tools\auto_read.py S25-A --conc 25            wait for the strip, then read
  .venv\Scripts\python tools\auto_read.py E1 --note empty --now      start immediately (empty tray)
  .venv\Scripts\python tools\auto_read.py G01 --degradation blur

A strip that is found but sits outside the +-15 px tolerance still starts the read; the
quality gate then records "strip not seated" (UNKNOWN). Nothing here changes a verdict.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app.config import load_config, phone_base, rpath  # noqa: E402
from app.roi import load_roi, locate_cfg  # noqa: E402
import guided_read  # noqa: E402


def strip_seen(loc, min_score: float) -> bool:
    """Patches found and the strip tip found (score only; the tolerance is judged by the read)."""
    return loc.patch_score >= min_score and loc.strip_score is not None and loc.strip_score >= min_score


def wait_for_strip(cfg, timeout: float, settle: float, need_away: bool = True) -> dict:
    roi = load_roi(rpath(cfg["roi_file"]))
    if roi is None or "anchor" not in roi["regions"]:
        raise SystemExit("ROI with an 'anchor' region is needed for auto start")
    ref = cv2.imread(str(ROOT / roi["reference_frame"]))
    rc = cfg["roi"]
    url = phone_base(cfg) + cfg.get("frame_endpoint", "/shot.jpg")
    t_end = time.time() + timeout
    seen_away = not need_away
    stable_since, last = None, None
    print("Waiting for the strip: dip, blot, tip into place, slide the tray fully in ...", flush=True)
    while time.time() < t_end:
        try:
            b = requests.get(url, timeout=3).content
            img = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
            loc = locate_cfg(roi, ref, img, rc)
        except Exception as e:  # phone hiccup: keep waiting
            print("  (frame failed:", e, ")", flush=True)
            time.sleep(0.5)
            continue
        if not strip_seen(loc, rc["min_match_score"]):
            if not seen_away:
                print("  tray empty/away seen", flush=True)
            seen_away, stable_since, last = True, None, None
        elif seen_away:
            pos = (tuple(loc.patch_shift), tuple(loc.strip_shift))
            if last is not None and all(abs(a - b) <= 2 for p, q in zip(pos, last) for a, b in zip(p, q)):
                if time.time() - stable_since >= settle:
                    return {"patch_shift": loc.patch_shift, "strip_shift": loc.strip_shift,
                            "patch_score": round(loc.patch_score, 3), "strip_score": round(loc.strip_score, 3),
                            "seated_now": loc.ok}
            else:
                stable_since = time.time()
            last = pos
        time.sleep(0.25)
    raise SystemExit("timeout: no strip arrived")


def wait_for_empty(cfg, timeout: float, settle: float) -> dict:
    """Wait until the tray is in (patches found) with NO strip (tip not found), still for `settle` s."""
    roi = load_roi(rpath(cfg["roi_file"]))
    ref = cv2.imread(str(ROOT / roi["reference_frame"]))
    rc = cfg["roi"]
    url = phone_base(cfg) + cfg.get("frame_endpoint", "/shot.jpg")
    t_end = time.time() + timeout
    since, last = None, None
    print("Waiting for an EMPTY tray (strip out, tray fully in) ...", flush=True)
    while time.time() < t_end:
        try:
            b = requests.get(url, timeout=3).content
            img = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
            loc = locate_cfg(roi, ref, img, rc)
        except Exception:
            time.sleep(0.5)
            continue
        empty = loc.patch_score >= rc["min_match_score"] and not strip_seen(loc, rc["min_match_score"])
        if empty:
            if last is not None and all(abs(a - b) <= 2 for a, b in zip(loc.patch_shift, last)):
                if time.time() - since >= settle:
                    return {"patch_shift": loc.patch_shift, "patch_score": round(loc.patch_score, 3)}
            else:
                since = time.time()
            last = tuple(loc.patch_shift)
        else:
            last = None
        time.sleep(0.25)
    raise SystemExit("timeout: tray never empty")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sample_id")
    ap.add_argument("--conc", type=float)
    ap.add_argument("--note", default="")
    ap.add_argument("--degradation", default="")
    ap.add_argument("--now", action="store_true", help="start immediately (empty-tray reads)")
    ap.add_argument("--wait-empty", action="store_true", help="start when the tray is in with no strip")
    ap.add_argument("--no-away", action="store_true", help="do not require seeing the tray without a strip first")
    ap.add_argument("--settle", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--no-panel", action="store_true", help="do not send the verdict to the panel")
    a = ap.parse_args()
    cfg = load_config()
    s = guided_read.call("/api/state")
    if s.get("session") is None:
        print("No session open in the app.")
        return 1
    if a.wait_empty:
        info = wait_for_empty(cfg, a.timeout, 3.0)
        print(f"Empty tray {time.strftime('%H:%M:%S')}: {info}", flush=True)
    elif not a.now:
        info = wait_for_strip(cfg, a.timeout, a.settle, need_away=not a.no_away)
        print(f"Strip in place {time.strftime('%H:%M:%S')}: {info}", flush=True)
    body = {"sample_id": a.sample_id, "concentration": a.conc, "note": a.note,
            "degradation": a.degradation, "send_to_panel": not a.no_panel}
    r = guided_read.call("/api/read/start", body)
    if not r.get("ok") and "Camera locked" in str(r.get("error")):
        # The app's periodic camera check may have caught the tray moving (sharpness dip).
        # Ask for a fresh check once; START only proceeds if the camera really is locked.
        print("START blocked by the camera check; re-checking once:", r.get("error"), flush=True)
        c = guided_read.call("/api/camcheck", {})
        print("  camera re-check:", c, flush=True)
        r = guided_read.call("/api/read/start", body)
    if not r.get("ok"):
        print("NOT STARTED:", r.get("error"))
        return 1
    print(f"START {time.strftime('%H:%M:%S')}: read running (60 s timer + 6 s window). Don't touch the dock.",
          flush=True)
    return guided_read.wait_and_summarise(a.sample_id)


if __name__ == "__main__":
    sys.exit(main())
