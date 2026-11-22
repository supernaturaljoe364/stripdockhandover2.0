r"""Live alignment aid: put the phone back exactly where it was at calibration.

Shows the live camera picture with the calibration picture's outlines drawn in RED on top,
plus the measured offset (px) and rotation (degrees) of the reference patches. Slide or turn
the phone until the red outlines sit on the real edges and the banner turns GREEN.
Close the app first is NOT needed (it only reads /shot.jpg). Press Q or Esc to quit.

  .venv\Scripts\python tools\align_phone.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_config, phone_base, rpath  # noqa: E402
from app.roi import load_roi  # noqa: E402

GOOD_PX, GOOD_DEG = 10, 0.5


def estimate(ref_g, cur_g):
    """Similarity transform ref -> cur from ORB features (downscaled 2x). Returns dx, dy, deg, inliers."""
    a = cv2.resize(ref_g, None, fx=0.5, fy=0.5)
    b = cv2.resize(cur_g, None, fx=0.5, fy=0.5)
    orb = cv2.ORB_create(3000)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return None
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
    if len(m) < 10:
        return None
    pa = np.float32([ka[x.queryIdx].pt for x in m])
    pb = np.float32([kb[x.trainIdx].pt for x in m])
    M, inl = cv2.estimateAffinePartial2D(pa, pb, ransacReprojThreshold=3.0)
    if M is None:
        return None
    deg = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    # displacement of the image centre, in full-resolution px
    c = np.array([a.shape[1] / 2, a.shape[0] / 2, 1.0])
    d = M @ c - c[:2]
    return float(d[0] * 2), float(d[1] * 2), deg, int(inl.sum()), M


def main():
    cfg = load_config()
    roi = load_roi(rpath(cfg["roi_file"]))
    ref = cv2.imread(str(ROOT / roi["reference_frame"]))
    ref_g = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(ref_g, (5, 5), 0), 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    url = phone_base(cfg) + "/shot.jpg"
    win = "StripDock: align the phone (Q to quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 1280, 760)
    t_end = time.time() + 1800
    while time.time() < t_end:
        try:
            cur = cv2.imdecode(np.frombuffer(requests.get(url, timeout=3).content, np.uint8), 1)
        except Exception:
            cur = None
        if cur is None:
            time.sleep(0.3)
            continue
        cur_g = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
        view = cur.copy()
        view[edges > 0] = (0, 0, 255)          # calibration outlines in red
        est = estimate(ref_g, cur_g)
        if est is None:
            msg, col = "cannot see the patches - is the tray in and the torch on?", (0, 0, 200)
        else:
            dx, dy, deg, n, _ = est
            ok = abs(dx) <= GOOD_PX and abs(dy) <= GOOD_PX and abs(deg) <= GOOD_DEG
            msg = (f"{'GOOD - stop moving' if ok else 'MOVE PHONE'}   offset x {dx:+.0f}px  y {dy:+.0f}px"
                   f"   turn {deg:+.2f} deg   (need |x|,|y| <= {GOOD_PX}, turn <= {GOOD_DEG})")
            col = (0, 160, 0) if ok else (0, 0, 200)
            print(time.strftime("%H:%M:%S"), msg, f"[{n} pts]", flush=True)
        cv2.rectangle(view, (0, 0), (view.shape[1], 70), col, -1)
        cv2.putText(view, msg, (20, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 3)
        cv2.imshow(win, view)
        k = cv2.waitKey(300) & 0xFF
        if k in (ord("q"), 27):
            break
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
