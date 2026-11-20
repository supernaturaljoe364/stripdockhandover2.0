"""One strip read: countdown from START, light-leak monitoring, read frames, quality gate,
features, model, decision, panel command, and everything saved to the sample folder."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from . import quality as Q
from .chart import nearest_block
from .colour import delta_e2000, rgb8_to_lab
from .decision import UNKNOWN, decide
from .features import capture_features, measure_frame, region_pixels
from .roi import crop, locate, shrink
from .session import sample_dir


class Cancelled(Exception):
    pass


class ReadJob:
    """Runs in its own thread. `progress` is read by the web UI."""

    def __init__(self, station, session: Path, mode: str, sample_id: str, extra: dict,
                 send_to_panel: bool = True, t_start: float | None = None):
        self.st = station
        self.session = session
        self.mode = mode
        self.sample_id = sample_id
        self.extra = extra
        self.send_to_panel = send_to_panel
        self.t0 = t_start or time.time()
        self.cancel_evt = threading.Event()
        self.progress = {"phase": "starting", "elapsed": 0.0, "message": "", "done": False}
        self.result: dict | None = None
        self._strip_metrics = {"strip_dE": None, "strip_absdiff": None}
        self.thread = threading.Thread(target=self._run, name="read-job", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def cancel(self):
        self.cancel_evt.set()

    def _sleep_until(self, t):
        while True:
            left = t - time.time()
            self.progress["elapsed"] = time.time() - self.t0
            if self.cancel_evt.is_set():
                raise Cancelled()
            if left <= 0:
                return
            time.sleep(min(0.1, left))

    # ------------------------------------------------------------ run
    def _run(self):
        try:
            self.result = self._read()
        except Cancelled:
            self.result = {"cancelled": True}
            self.progress.update(phase="cancelled", message="Read cancelled. Panel not changed.")
        except Exception as e:  # any crash -> UNKNOWN, never PASS
            self.progress["message"] = f"internal error: {e}"
            self.result = self._fail_safe(f"internal error: {e}")
        finally:
            self.progress["done"] = True

    def _fail_safe(self, reason):
        v = {"command": UNKNOWN, "reasons": [reason], "display": "UNKNOWN: re-test"}
        panel_state = None
        if self.send_to_panel and self.st.panel is not None:
            panel_state = self.st.panel.send(UNKNOWN)
        return {"verdict": v, "panel_reply": panel_state}

    def _read(self):
        cfg, st = self.st.cfg, self.st
        q = cfg["quality"]
        read_time = float(cfg["read_time_s"])
        if self.mode == "degraded" and self.extra.get("degradation") == "early_read":
            read_time = float(cfg.get("early_read_s", 20))
        offsets = [float(x) for x in cfg["read_offsets_s"]]
        sdir = sample_dir(self.session, self.sample_id)
        fdir = sdir / "frames"
        cam = st.read_cam
        roi = st.roi
        ref = st.ref_frame
        tol = int(cfg["roi"]["shift_tol_px"])
        search = int(cfg["roi"]["search_px"])
        min_score = float(cfg["roi"]["min_match_score"])

        errors, latencies, black_L, monitor, retries = [], [], [], [], []
        located_ok, locate_reasons = [], []

        max_age = float(q["max_frame_age_s"])
        attempts = 1 + int(cfg.get("frame_retries", 1))

        def grab_and_locate(tag):
            # A single slow/failed HTTP request is retried once (DECISIONS D-35). The frame
            # used must itself arrive within max_frame_age_s; a phone that stays unreachable
            # still fails the phone check -> UNKNOWN.
            fr, last_err = None, ""
            for k in range(attempts):
                try:
                    f = cam.grab(cfg["frame_endpoint"], timeout=max_age)
                except Exception as e:
                    last_err = str(e)
                else:
                    if f.latency <= max_age:
                        fr = f
                        break
                    last_err = f"frame took {f.latency:.1f} s"
                if k < attempts - 1:
                    retries.append(f"{tag}: {last_err}")
                    time.sleep(0.2)
            if fr is None:
                errors.append(f"{tag}: {last_err}")
                return None, None
            latencies.append(fr.latency)
            loc = locate(roi, ref, fr.bgr, tol, search, min_score)
            located_ok.append(loc.ok)
            locate_reasons.append(loc.reason)
            bpx = region_pixels(fr.bgr, shrink(loc.regions["black"], cfg["roi"]["shrink_frac"]))
            bl = float(rgb8_to_lab(np.median(bpx, axis=0))[0]) if len(bpx) else 100.0
            black_L.append(bl)
            return fr, loc

        # 1. monitoring until the read time
        self.progress.update(phase="countdown", read_time=read_time,
                             message="Developing. Keep the drawer closed.")
        k = 0
        next_t = self.t0 + 1.0
        while next_t < self.t0 + read_time + offsets[0] - 0.3:
            self._sleep_until(next_t)
            fr, loc = grab_and_locate(f"monitor{k}")
            el = time.time() - self.t0
            entry = {"t": round(el, 2), "black_L": black_L[-1] if fr is not None else None,
                     "located": loc.ok if loc else None, "shift": loc.patch_shift if loc else None,
                     "error": None if fr is not None else errors[-1]}
            if fr is not None and k % 5 == 0:
                cv2.imwrite(str(fdir / f"monitor_{k:03d}.jpg"), fr.bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
                entry["file"] = f"frames/monitor_{k:03d}.jpg"
            monitor.append(entry)
            k += 1
            next_t += float(cfg["monitor_interval_s"])

        # 2. read frames (never before the read time)
        self.progress.update(phase="reading", message="Reading the pad ...")
        reads = []
        for i, off in enumerate(offsets):
            self._sleep_until(self.t0 + read_time + off)
            fr, loc = grab_and_locate(f"read{i}")
            if fr is None:
                continue
            el = fr.t_request - self.t0
            name = f"read_{i}.jpg"
            (fdir / name).write_bytes(fr.jpeg)       # the exact bytes the phone sent
            m = measure_frame(fr.bgr, loc.regions, cfg)
            m.update({"file": f"frames/{name}", "elapsed_s": round(el, 3), "latency_s": round(fr.latency, 3),
                      "located_ok": loc.ok, "locate_reason": loc.reason,
                      "patch_shift": list(loc.patch_shift), "strip_shift": list(loc.strip_shift),
                      "patch_score": round(loc.patch_score, 3),
                      "strip_score": None if loc.strip_score is None else round(loc.strip_score, 3),
                      "regions_used": loc.regions})
            reads.append((fr, loc, m))

        # 3. quality gate
        self.progress.update(phase="deciding", message="Checking quality ...")
        checks = [Q.check_phone(errors, latencies, q)]
        if not reads:
            checks.append(Q.Check("frames", False, 0, ">= 1 read frame", "no read frames received from the phone"))
        else:
            ms = [m for _, _, m in reads]
            checks.append(Q.check_seated(located_ok, locate_reasons))
            checks.append(Q.check_light_leak(black_L, q))
            wl = float(np.mean([m["raw_lab"]["white"][0] for m in ms]))
            checks.append(Q.check_exposure(wl, max(m["white_clip_frac"] for m in ms), q))
            checks.append(Q.check_glare(max(m["pad_glare_frac"] for m in ms), q))
            checks.append(Q.check_blur(min(m["sharpness"] for m in ms), q))
            checks.append(Q.check_timing(min(m["elapsed_s"] for m in ms), float(cfg["read_time_s"])))
            checks.append(Q.check_drift([m["corr_lab"]["nitrate_pad"] for m in ms], q))
            checks.append(Q.check_reference(max(m["grey_chroma"] for m in ms), q))
            checks.append(self._strip_present(reads[0], q))
        q_ok, q_reasons = Q.gate(checks)
        metrics = {"black_L_series": [round(x, 2) for x in black_L],
                   "black_jump_max": float(max(np.abs(np.diff(black_L)))) if len(black_L) > 1 else 0.0,
                   "latency_max_s": max(latencies) if latencies else None, "n_errors": len(errors),
                   "n_retries": len(retries), "retries": retries[:20]}
        if reads:
            ms = [m for _, _, m in reads]
            metrics.update({
                "black_L_max": float(max(black_L)),
                "white_L_mean": float(np.mean([m["raw_lab"]["white"][0] for m in ms])),
                "white_clip_max": float(max(m["white_clip_frac"] for m in ms)),
                "glare_max": float(max(m["pad_glare_frac"] for m in ms)),
                "sharpness_min": float(min(m["sharpness"] for m in ms)),
                "grey_chroma_max": float(max(m["grey_chroma"] for m in ms)),
                "drift_dE": next((c.value for c in checks if c.name == "drift"), None),
                **self._strip_metrics})

        # 4. features + model + decision
        feats = capture_features([m for _, _, m in reads]) if reads else None
        model = st.model_for(self.mode)
        pred, block = None, None
        if feats is not None and model is not None:
            lab = [feats["pad_L"], feats["pad_a"], feats["pad_b"]]
            pred = model.predict(lab)
            block = nearest_block(pred["est"], st.blocks, float(cfg["model"]["conc_offset_mg_L"]))
        verdict = decide(q_ok, q_reasons, pred, model.thr["reject_dE"] if model else None,
                         float(cfg["hold_block_mg_L"]), model.thr["band_low_mg_L"] if model else None, block)

        # 5. panel
        panel_reply = None
        t_verdict = time.time()
        if self.send_to_panel and st.panel is not None:
            panel_reply = st.panel.send(verdict.command)
        delivered = panel_reply is not None
        self.progress.update(phase="done", message=verdict.display)

        # 6. save
        meta = {
            "sample_id": self.sample_id, "folder": sdir.name, "mode": self.mode,
            "session": self.session.name, **self.extra,
            "t_start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)),
            "start_to_verdict_s": round(t_verdict - self.t0, 2),
            "read_time_s": read_time, "read_offsets_s": offsets,
            "lighting_mode": cfg["lighting_mode"],
            "camera_settings_hash": st.camera_hash, "roi_hash": st.roi_hash,
            "quality_thresholds": q,
            "model": None if model is None else {"file": model.path.name if model.path else None,
                                                 "sha256": model.sha, "frozen": model.frozen,
                                                 "primary": model.primary},
            "checks": [c.to_dict() for c in checks], "quality_ok": q_ok, "metrics": metrics,
            "features": feats, "prediction": pred, "verdict": verdict.to_dict(),
            "panel": {"sent": self.send_to_panel, "reply_state": panel_reply, "delivered": delivered},
            "monitor": monitor, "frames": [m for _, _, m in reads], "errors": errors,
        }
        (sdir / "meta.json").write_text(json.dumps(meta, indent=1, default=float))
        return {"verdict": verdict.to_dict(), "panel_reply": panel_reply, "delivered": delivered,
                "sample_folder": str(sdir), "checks": meta["checks"], "features": feats,
                "start_to_verdict_s": meta["start_to_verdict_s"]}

    def _strip_present(self, read0, q):
        fr, loc, _ = read0
        self._strip_metrics = {"strip_dE": None, "strip_absdiff": None}
        empty = self.st.empty_frame
        if empty is None:
            return Q.check_strip_present(None, None, q)
        frac = self.st.cfg["roi"]["shrink_frac"]
        # the empty-tray reference was taken at calibration, so use the calibration pad position
        # shifted by the patch-row shift (the tray is fixed to the dock)
        pad_cur = shrink(loc.regions["nitrate_pad"], frac)
        r0 = self.st.roi["regions"]["nitrate_pad"]
        pad_emp = shrink([r0[0] + loc.patch_shift[0], r0[1] + loc.patch_shift[1], r0[2], r0[3]], frac)
        a = crop(fr.bgr, pad_cur)
        b = crop(empty, pad_emp)
        if a.size == 0 or b.size == 0 or a.shape != b.shape:
            return Q.check_strip_present(None, None, q)
        la = rgb8_to_lab(np.median(a[..., ::-1].reshape(-1, 3), axis=0))
        lb = rgb8_to_lab(np.median(b[..., ::-1].reshape(-1, 3), axis=0))
        dE = float(delta_e2000(la, lb))
        diff = float(np.mean(np.abs(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(float)
                                    - cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(float))))
        self._strip_metrics = {"strip_dE": dE, "strip_absdiff": diff}
        return Q.check_strip_present(dE, diff, q)
