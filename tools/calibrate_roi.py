r"""Region calibration without the web app (OpenCV windows). The web page
http://localhost:5000/calibrate does the same thing and is easier; use this if the app
cannot run.

Steps: 1) empty tray in -> press a key; 2) strip in the tray -> press a key;
3) drag a rectangle for each region, ENTER to accept, C to skip an optional one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config, phone_base, rpath  # noqa: E402
from app.model import load_frozen  # noqa: E402
from app.phone import PhoneCam  # noqa: E402
from app.roi import OPTIONAL, REQUIRED, roi_hash, save_roi  # noqa: E402


def show_until_key(cam, endpoint, title):
    print(title)
    while True:
        fr = cam.grab(endpoint, timeout=5.0, check_fresh=False)
        small = cv2.resize(fr.bgr, (960, int(960 * fr.bgr.shape[0] / fr.bgr.shape[1])))
        cv2.putText(small, title + "  (press any key)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("StripDock calibration", small)
        if cv2.waitKey(300) != -1:
            return fr.bgr


def main():
    cfg = load_config()
    if load_frozen() is not None:
        ans = input("A frozen model exists; a new ROI invalidates it. Type YES to continue: ")
        if ans.strip() != "YES":
            return 1
    cam = PhoneCam(phone_base(cfg), 5.0)
    empty = show_until_key(cam, cfg["frame_endpoint"], "1/2 EMPTY tray slid in")
    frame = show_until_key(cam, cfg["frame_endpoint"], "2/2 strip in the tray, against the end-stop")
    cv2.destroyAllWindows()
    regions = {}
    scale = 960 / frame.shape[1]
    small = cv2.resize(frame, (960, int(frame.shape[0] * scale)))
    for name in REQUIRED + OPTIONAL:
        opt = name in OPTIONAL
        r = cv2.selectROI(f"Drag: {name}{' (optional, C to skip)' if opt else ''}", small, showCrosshair=True)
        cv2.destroyAllWindows()
        if r[2] == 0 or r[3] == 0:
            if opt:
                continue
            print(f"{name} is required")
            return 1
        regions[name] = [int(round(v / scale)) for v in r]
    roi = save_roi(rpath(cfg["roi_file"]), regions, frame, empty)
    print(f"Saved {rpath(cfg['roi_file'])} (hash {roi_hash(roi)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
