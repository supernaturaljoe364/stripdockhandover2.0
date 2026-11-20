"""Camera lock: freeze IP Webcam settings and check them later.

The phone (results/ipwebcam_status.json) reports no exposure_lock / whitebalance_lock
keys. It does report manual_sensor + exposure_ns + iso + frame_duration (a fixed manual
exposure is a stronger lock than AE-lock), whitebalance presets (a fixed preset = WB
lock), and focusmode=off + focus_distance (manual focus = focus lock). We use those.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

# Settings that make up the frozen camera state (only those the phone reports are used).
FROZEN_KEYS = ["video_size", "photo_size", "quality", "night_vision", "scenemode",
               "flashmode", "torch", "manual_sensor", "exposure_ns", "iso", "frame_duration",
               "whitebalance", "focusmode", "focus_distance", "zoom", "coloreffect",
               "orientation", "mirror_flip", "antibanding", "ffc"]
# Settings we never change, but record and check (a change means the geometry/colour moved).
OBSERVE_ONLY = {"zoom", "coloreffect", "orientation", "mirror_flip", "ffc", "antibanding"}


def _num_equal(a, b, rel=0.02):
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    return abs(fa - fb) <= rel * max(abs(fa), abs(fb), 1e-9)


def compare_settings(frozen: dict, current: dict, lighting_mode: str) -> list[str]:
    """Return a list of mismatch descriptions (empty = match)."""
    problems = []
    for k, v in frozen.get("settings", {}).items():
        cur = current.get(k)
        if cur is None:
            problems.append(f"{k}: not reported by phone now (frozen {v})")
        elif not _num_equal(cur, v):
            problems.append(f"{k}: now {cur}, frozen {v}")
    want_torch = "on" if lighting_mode == "phone_torch" else "off"
    if current.get("torch") is not None and current.get("torch") != want_torch:
        problems.append(f"torch: now {current.get('torch')}, lighting_mode {lighting_mode} needs {want_torch}")
    if frozen.get("lighting_mode") and frozen["lighting_mode"] != lighting_mode:
        problems.append(f"lighting_mode: config {lighting_mode}, frozen {frozen['lighting_mode']}")
    return problems


def load_frozen(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def settings_hash(frozen: dict) -> str:
    from .config import stable_hash
    return stable_hash({"settings": frozen.get("settings", {}),
                        "lighting_mode": frozen.get("lighting_mode")})


def check_camera(cam, cfg: dict, path: Path) -> tuple[bool, list[str], dict | None]:
    """(ok, problems, frozen). Used by the app, train.py and lock_camera.py --check."""
    frozen = load_frozen(path)
    if frozen is None:
        return False, [f"no frozen camera settings ({path.name}); run tools\\lock_camera.py"], None
    try:
        cur = cam.curvals()
    except Exception as e:
        return False, [f"phone unreachable: {e}"], frozen
    problems = compare_settings(frozen, cur, cfg.get("lighting_mode", "dock_leds"))
    ref = frozen.get("sharpness_ref")
    if not problems and ref and frozen.get("focus_method") == "single_af":
        # the lens position is not reported; check the fixed reference patches are still sharp
        try:
            import cv2
            from .roi import crop
            fr = cam.grab(cfg.get("frame_endpoint", "/shot.jpg"), timeout=5.0, check_fresh=False)
            now = sharpness(cv2.cvtColor(crop(fr.bgr, ref["rect"]), cv2.COLOR_BGR2GRAY))
            if now < 0.5 * ref["value"]:
                problems.append(f"focus lost: patch sharpness {now:.1f} vs {ref['value']:.1f} at lock; "
                                "run tools\\lock_camera.py to refocus")
        except Exception as e:
            problems.append(f"focus check failed: {e}")
    return (not problems), problems, frozen


def sharpness(gray: np.ndarray) -> float:
    import cv2
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def nearest_avail(avail: list[str], target: float) -> str:
    return min(avail, key=lambda v: abs(float(v) - target))


def closest_size(avail: list[str], w: int = 1920, h: int = 1080) -> str:
    if f"{w}x{h}" in avail:
        return f"{w}x{h}"

    def score(s):
        a, b = (int(x) for x in s.split("x"))
        return (abs(a * b - w * h), abs(a / b - w / h))
    return min(avail, key=score)


def wait_settle(seconds: float):
    time.sleep(seconds)
