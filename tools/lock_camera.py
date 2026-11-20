r"""Lock the phone camera (IP Webcam) and freeze the settings.

  python tools\\lock_camera.py --new     search focus/WB/exposure, freeze to camera_settings.json
  python tools\\lock_camera.py           re-apply the frozen settings (after an app restart), then verify
  python tools\\lock_camera.py --check   only check the phone matches the frozen settings (exit 0/1)

Only settings the phone reports in /status.json are touched. Order (master prompt,
Phase 2): resolution 1920x1080, JPEG quality high, night vision off, HDR off, flash off,
torch on for phone_torch mode (kept on all session), settle 3 s, then lock focus,
white balance and exposure, then verify colour stability over 10 frames (< 1.0 dE00 on
the white patch, or a central bright region if no ROI exists yet).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.camlock import (FROZEN_KEYS, OBSERVE_ONLY, check_camera, closest_size,  # noqa: E402
                         compare_settings, load_frozen, settings_hash, sharpness)
from app.colour import delta_e2000, lch, rgb8_to_lab  # noqa: E402
from app.config import ROOT, load_config, phone_base, rpath  # noqa: E402
from app.phone import PhoneCam, PhoneError  # noqa: E402
from app.roi import bbox, crop, load_roi, shrink  # noqa: E402

JPEG_QUALITY = 90
MANUAL_STEPS = {
    "exposure": "IP Webcam -> Video preferences -> turn on 'Manual sensor' and set a fixed exposure/ISO",
    "whitebalance": "IP Webcam -> Video preferences -> White balance -> pick a fixed preset (e.g. Daylight), or turn on White balance lock",
    "focus": "IP Webcam -> Video preferences -> Focus mode -> Off/Fixed (or enable Focus lock)",
    "torch": "Swipe down on the phone, or IP Webcam -> Torch / LED flash -> On",
}


def white_region(cfg, frame):
    """White patch region (shrunk) if ROI exists, else the central 40% of the frame."""
    roi = load_roi(rpath(cfg["roi_file"]))
    if roi:
        return shrink(roi["regions"]["white"], cfg["roi"]["shrink_frac"]), "white patch (roi.json)"
    h, w = frame.shape[:2]
    return [int(w * 0.3), int(h * 0.3), int(w * 0.4), int(h * 0.4)], "central 40% (no ROI yet)"


def sharp_region(cfg, frame):
    roi = load_roi(rpath(cfg["roi_file"]))
    if roi:
        r = roi["regions"]
        return bbox([r["nitrate_pad"], r["white"], r["grey"], r["black"]]), "pad + patches (roi.json)"
    h, w = frame.shape[:2]
    return [int(w * 0.25), int(h * 0.25), int(w * 0.5), int(h * 0.5)], "central 50% (no ROI yet)"


def patch_region(cfg):
    """Bounding box of the reference patches (fixed to the dock) if an ROI exists."""
    roi = load_roi(rpath(cfg["roi_file"]))
    if not roi:
        return None
    r = roi["regions"]
    return bbox([r["white"], r["grey"], r["black"]])


def level_of(frame, rect, roi_mode):
    """8-bit brightness measure. With an ROI: the brightest channel's median on the white
    patch (so no channel clips under a tinted white-balance preset). Without: the 99th
    percentile of the brightest channel in the centre."""
    px = crop(frame, rect).reshape(-1, 3)
    if roi_mode:
        return float(np.max(np.median(px, axis=0)))
    return float(np.percentile(px.max(axis=1), 99))


def grab(cam, n_skip=2, settle=0.6):
    """Wait for settings to take effect, drop a couple of frames, return a fresh one."""
    time.sleep(settle)
    fr = None
    for _ in range(n_skip + 1):
        fr = grab_retry(cam)
        time.sleep(0.08)
    return fr.bgr


def grab_retry(cam, tries=4):
    """Setup-time grab that tolerates Wi-Fi blips (never used for reads)."""
    for k in range(tries):
        try:
            return cam.grab("/shot.jpg", timeout=5.0, check_fresh=False)
        except PhoneError:
            if k == tries - 1:
                raise
            time.sleep(1.0)


def try_set(cam, key, value, cur, log):
    if key not in cur:
        log.append(f"skip {key}: not reported by this phone")
        return False
    cam.set_setting(key, value)
    log.append(f"set {key}={value}")
    return True


def stability(cam, cfg, n=10):
    labs = []
    rect = None
    shas = []
    for _ in range(n):
        fr_ = grab_retry(cam)
        shas.append(fr_.sha)
        f = fr_.bgr
        if rect is None:
            rect, desc = white_region(cfg, f)
        px = crop(f, rect)[..., ::-1].reshape(-1, 3)
        labs.append(rgb8_to_lab(np.median(px, axis=0)))
        time.sleep(0.25)
    labs = np.array(labs)
    dE = delta_e2000(labs, labs.mean(axis=0))
    dup = n - len(set(shas))
    if dup:
        desc += f"; WARNING {dup} of {n} frames were byte-identical (camera stream stalled)"
        return float("nan"), float("nan"), labs.mean(axis=0).round(2).tolist(), desc
    return float(dE.mean()), float(dE.max()), labs.mean(axis=0).round(2).tolist(), desc


def do_new(cam, cfg, args):
    st = cam.status(avail=True)
    cur, avail = st.get("curvals", {}), st.get("avail", {})
    log, manual = [], []
    mode = cfg.get("lighting_mode", "dock_leds")

    # 1. resolution / quality / night vision / HDR / flash
    if "video_size" in avail:
        try_set(cam, "video_size", closest_size(avail["video_size"]), cur, log)
    if "photo_size" in avail:
        try_set(cam, "photo_size", closest_size(avail["photo_size"]), cur, log)
    try_set(cam, "quality", JPEG_QUALITY, cur, log)
    try_set(cam, "night_vision", "off", cur, log)
    if cur.get("scenemode") == "hdr" or "scenemode" in cur:
        try_set(cam, "scenemode", "auto", cur, log)      # HDR off
    try_set(cam, "flashmode", "off", cur, log)            # never flash per shot
    # 2. lighting
    if "torch" in cur:
        cam.torch(mode == "phone_torch")
        log.append(f"torch {'on' if mode == 'phone_torch' else 'off'} ({mode})")
    elif mode == "phone_torch":
        manual.append(MANUAL_STEPS["torch"])
    # make sure we start from the automatic state for the search
    try_set(cam, "manual_sensor", "off", cur, log)
    try_set(cam, "whitebalance", "auto", cur, log)
    print("Settling 3 s ...")
    time.sleep(3.0)

    # 3. focus. Preferred: manual focus sweep (focusmode off + focus_distance) = a true lock.
    #    If the strip is closer than the phone lets manual focus reach (IP Webcam clamps
    #    focus_distance at 10 diopters = 10 cm), fall back to single-shot autofocus:
    #    focusmode=auto + ONE /focus trigger now; the lens then stays put (measured on this
    #    phone 2026-11-19: sharpness 33.2 -> 32.7 over 20 s). Never triggered at read time.
    focus_method, sharp_ref = None, None
    if "focusmode" in avail and "focus_distance" in avail and "off" in avail["focusmode"]:
        f0 = grab(cam, settle=0.3)
        srect, sdesc = sharp_region(cfg, f0)
        prect = patch_region(cfg)

        def meas():
            fr = grab(cam, settle=0.5)
            return sharpness(cv2.cvtColor(crop(fr, srect), cv2.COLOR_BGR2GRAY)), fr

        af_score = None
        if "auto" in avail["focusmode"]:
            cam.set_setting("focusmode", "auto")
            cam.trigger_focus()
            time.sleep(2.5)
            af_score, _ = meas()
            log.append(f"single autofocus on {sdesc}: sharpness {af_score:.1f}")
        cam.set_setting("focusmode", "off")
        dists = [float(v) for v in avail["focus_distance"]]
        coarse = [d for d in dists if abs((d * 2) - round(d * 2)) < 1e-6]   # 0.5 steps
        scores = {}
        for d in coarse:
            cam.set_setting("focus_distance", f"{d:.2f}" if d < 10 else "10.0")
            scores[d] = meas()[0]
        best = max(scores, key=scores.get)
        for d in [d for d in dists if abs(d - best) <= 0.45 and d not in scores]:
            cam.set_setting("focus_distance", f"{d:.2f}" if d < 10 else "10.0")
            scores[d] = meas()[0]
        best = max(scores, key=scores.get)
        log.append(f"manual focus sweep on {sdesc}: best focus_distance={best} (sharpness {scores[best]:.1f}; "
                   f"range {min(scores.values()):.1f}..{max(scores.values()):.1f})")
        if af_score is not None and scores[best] < 0.8 * af_score:
            cam.set_setting("focusmode", "auto")
            cam.trigger_focus()
            time.sleep(2.5)
            focus_method = "single_af"
            log.append(f"focus locked by single autofocus (manual best {scores[best]:.1f} < 0.8 x AF {af_score:.1f}; "
                       "strip is closer than manual focus reaches)")
        else:
            cam.set_setting("focus_distance", f"{best:.2f}" if best < 10 else "10.0")
            focus_method = "manual"
            log.append(f"focus locked manually at focus_distance={best}")
        print(log[-1])
        fr = grab(cam, settle=0.5)
        if prect:
            sharp_ref = {"rect": prect, "value": sharpness(cv2.cvtColor(crop(fr, prect), cv2.COLOR_BGR2GRAY)),
                         "region": "reference patches"}
    else:
        manual.append(MANUAL_STEPS["focus"])

    # 4. white balance: fixed preset giving the most neutral white region
    if "whitebalance" in avail:
        presets = [p for p in avail["whitebalance"] if p not in ("auto", "off")]
        best_wb, best_c = None, 1e9
        for p in presets:
            cam.set_setting("whitebalance", p)
            f = grab(cam, settle=1.0)
            rect, _ = white_region(cfg, f)
            C, _ = lch(rgb8_to_lab(np.median(crop(f, rect)[..., ::-1].reshape(-1, 3), axis=0)))
            log.append(f"wb {p}: white chroma {float(C):.2f}")
            if C < best_c:
                best_wb, best_c = p, float(C)
        cam.set_setting("whitebalance", best_wb)
        log.append(f"white balance locked: preset {best_wb} (white chroma {best_c:.2f})")
        print(log[-1])
    else:
        manual.append(MANUAL_STEPS["whitebalance"])

    # 5. exposure: manual sensor, lowest ISO that reaches target, bisection on exposure_ns
    if all(k in avail for k in ("manual_sensor", "exposure_ns", "iso")):
        cam.set_setting("manual_sensor", "on")
        exps = sorted(float(v) for v in avail["exposure_ns"])
        isos = sorted(float(v) for v in avail["iso"])
        fds = sorted(float(v) for v in avail.get("frame_duration", []))
        f = grab(cam)
        rect, desc = white_region(cfg, f)
        roi_mode = desc.startswith("white")
        target = args.target if args.target else (215.0 if roi_mode else 235.0)

        def measure(e, iso):
            if fds:
                fd = next((x for x in fds if x >= e), fds[-1])
                cam.set_setting("frame_duration", int(fd))
            cam.set_setting("iso", int(iso))
            cam.set_setting("exposure_ns", int(e))
            return level_of(grab(cam, settle=0.7), rect, roi_mode)

        chosen = None
        for iso in isos[:: max(1, len(isos) // 12)]:
            lo, hi = 0, len(exps) - 1
            if measure(exps[hi], iso) < target - 20:
                log.append(f"iso {int(iso)}: too dark even at {exps[hi] / 1e6:.1f} ms")
                continue
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if measure(exps[mid], iso) < target:
                    lo = mid
                else:
                    hi = mid
            lvl_lo, lvl_hi = measure(exps[lo], iso), measure(exps[hi], iso)
            idx = lo if abs(lvl_lo - target) <= abs(lvl_hi - target) else hi
            lvl = measure(exps[idx], iso)
            chosen = (exps[idx], iso, lvl)
            break
        if chosen is None:
            log.append("WARNING: could not reach the exposure target; set to max exposure")
            e, iso = exps[-1], isos[-1]
            lvl = measure(e, iso)
            chosen = (e, iso, lvl)
        log.append(f"exposure locked on {desc}: exposure {chosen[0] / 1e6:.3f} ms, ISO {int(chosen[1])}, "
                   f"level {chosen[2]:.0f}/255 (target {target:.0f})")
        print(log[-1])
    else:
        manual.append(MANUAL_STEPS["exposure"])

    time.sleep(1.0)
    cur2 = cam.curvals()
    frozen = {
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "phone": cam.base,
        "lighting_mode": mode,
        "settings": {k: cur2[k] for k in FROZEN_KEYS if k in cur2},
        "observe_only": sorted(k for k in OBSERVE_ONLY if k in cur2),
        "focus_method": focus_method,
        "sharpness_ref": sharp_ref,
        "log": log,
        "manual_steps_needed": manual,
    }
    return frozen


def apply_frozen(cam, frozen, cfg):
    cur = cam.curvals()
    s = frozen["settings"]
    order = ["video_size", "photo_size", "quality", "night_vision", "scenemode", "flashmode",
             "focusmode", "focus_distance", "whitebalance", "manual_sensor", "frame_duration",
             "iso", "exposure_ns"]
    for k in order:
        if k in s and k in cur and k not in OBSERVE_ONLY and str(cur[k]) != str(s[k]):
            cam.set_setting(k, s[k])
            print(f"  set {k}={s[k]} (was {cur[k]})")
    want = cfg.get("lighting_mode") == "phone_torch"
    if "torch" in cur and (cur["torch"] == "on") != want:
        cam.torch(want)
        print(f"  torch {'on' if want else 'off'}")
    time.sleep(1.5)
    if frozen.get("focus_method") == "single_af":
        cam.trigger_focus()           # one autofocus, as at lock time (setup only, never at read time)
        print("  single autofocus triggered (focus_method single_af)")
        time.sleep(2.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", action="store_true", help="search and freeze new settings")
    ap.add_argument("--check", action="store_true", help="only check against the frozen settings")
    ap.add_argument("--force", action="store_true", help="allow --new when a frozen model exists")
    ap.add_argument("--target", type=float, default=None, help="8-bit exposure target")
    ap.add_argument("--out", default=None, help="write frozen settings here instead (testing)")
    ap.add_argument("--refresh-focus-ref", action="store_true",
                    help="after (re)calibrating the ROI: re-measure the patch sharpness reference only; "
                         "no camera setting is changed")
    args = ap.parse_args()
    cfg = load_config()
    path = Path(args.out) if args.out else rpath(cfg["camera_settings_file"])
    cam = PhoneCam(phone_base(cfg), timeout=5.0)

    if args.check:
        ok, problems, frozen = check_camera(cam, cfg, path)
        if ok:
            print(f"CAMERA LOCK OK: phone matches {path.name} (frozen {frozen['frozen_at']}, "
                  f"hash {settings_hash(frozen)})")
            return 0
        print("CAMERA LOCK CHECK FAILED:")
        for p in problems:
            print("  -", p)
        print("Fix: run  .venv\\Scripts\\python tools\\lock_camera.py  (re-applies the frozen settings)")
        return 1

    frozen = load_frozen(path)
    if args.refresh_focus_ref:
        if frozen is None:
            print("No frozen settings yet; run with --new first.")
            return 2
        prect = patch_region(cfg)
        if not prect:
            print("No ROI yet; calibrate the regions first.")
            return 2
        fr = cam.grab("/shot.jpg", timeout=5.0, check_fresh=False).bgr
        val = sharpness(cv2.cvtColor(crop(fr, prect), cv2.COLOR_BGR2GRAY))
        frozen["sharpness_ref"] = {"rect": prect, "value": val, "region": "reference patches",
                                   "refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        path.write_text(json.dumps(frozen, indent=1))
        print(f"Focus reference refreshed on the patches: sharpness {val:.1f} (settings unchanged, "
              f"hash {settings_hash(frozen)})")
        return 0
    if args.new or frozen is None:
        if frozen is not None and any((ROOT / "models" / "frozen").glob("*.json")) and not args.force:
            print("A frozen model exists. New camera settings would invalidate it. Use --force "
                  "only if you are starting training again from scratch.")
            return 2
        try:
            frozen = do_new(cam, cfg, args)
        except PhoneError as e:
            print("ERROR:", e)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(frozen, indent=1))
        print(f"Saved frozen settings to {path} (hash {settings_hash(frozen)})")
        for m in frozen["manual_steps_needed"]:
            print("MANUAL STEP NEEDED:", m)
    else:
        print(f"Re-applying frozen settings from {path.name} (frozen {frozen['frozen_at']})")
        apply_frozen(cam, frozen, cfg)

    problems = compare_settings(frozen, cam.curvals(), cfg.get("lighting_mode", "dock_leds"))
    mean_dE, max_dE, lab, desc = stability(cam, cfg)
    ok = not problems and mean_dE < 1.0   # NaN (stalled stream) is never < 1.0
    res = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "settings_match": not problems,
           "problems": problems, "stability_region": desc, "dE00_mean": mean_dE,
           "dE00_max": max_dE, "Lab_mean": lab, "pass": ok,
           "settings_file": str(path), "settings_hash": settings_hash(frozen)}
    if not args.out:
        (ROOT / "results").mkdir(exist_ok=True)
        (ROOT / "results" / "camera_lock_check.json").write_text(json.dumps(res, indent=1))
    print(f"Stability over 10 frames on {desc}: dE00 mean {mean_dE:.2f}, max {max_dE:.2f}, Lab {lab}")
    print("LOCK VERIFIED" if ok else f"LOCK NOT VERIFIED: {problems or 'colour not stable (dE00 >= 1.0)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PhoneError as e:
        print(f"ERROR: {e}")
        print("Is IP Webcam running ('Start server') and is the PC on the same Wi-Fi?")
        sys.exit(1)
