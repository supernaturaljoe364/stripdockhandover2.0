"""Station: everything the running app holds (config, panel link, phone, ROI, models,
session, current read job) plus the startup checklist."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2

from .camlock import check_camera, settings_hash
from .chart import load_chart
from .config import ROOT, load_config, phone_base, quality_thresholds, rpath, stable_hash
from .model import load_any, load_frozen
from .panel import PanelLink
from .phone import PhoneCam
from .roi import load_roi, roi_hash
from .session import load_session, new_session

LATEST_MODEL = ROOT / "models" / "model_latest.json"
FROZEN_MODES = ("test", "degraded", "demo")


class Station:
    def __init__(self, cfg: dict | None = None, start_threads: bool = True):
        self.cfg = cfg or load_config()
        self.chart = load_chart(rpath(self.cfg["chart_file"]))
        self.blocks = self.chart["blocks_no3"]
        self.lock = threading.RLock()
        self.messages: list[dict] = []
        self._ready_seen = False
        self.panel = PanelLink(self.cfg.get("serial_port", "auto"), self.cfg.get("serial_baud", 115200),
                               self.cfg.get("ping_interval_s", 2.0))
        self.panel.add_listener(self._on_panel_event)
        base = phone_base(self.cfg)
        self.preview_cam = PhoneCam(base, timeout=float(self.cfg["http_timeout_s"]))
        self.read_cam = PhoneCam(base, timeout=float(self.cfg["http_timeout_s"]))
        self.status_cam = PhoneCam(base, timeout=3.0)
        self.preview = None            # latest Frame
        self.preview_ok_t = 0.0
        self.preview_err = ""
        self.cam_check = (False, ["not checked yet"], None)
        self.cam_check_t = 0.0
        self.session: Path | None = None
        self.session_meta: dict | None = None
        self.job = None
        self.last_result = None
        self.confirm_since = None
        self.reload_roi()
        self.reload_models()
        self._stop = threading.Event()
        if start_threads:
            self.panel.start()
            threading.Thread(target=self._preview_loop, name="preview", daemon=True).start()
            threading.Thread(target=self._camcheck_loop, name="camcheck", daemon=True).start()

    # ------------------------------------------------------------ messages / events
    def msg(self, text, level="info"):
        with self.lock:
            self.messages.append({"t": time.time(), "text": text, "level": level})
            self.messages = self.messages[-40:]

    def _on_panel_event(self, p):
        if p.kind == "evt" and p.event == "CLEARED":
            self.msg("Panel: CONFIRM pressed. Hold cleared, back to Adaptive mode (TDS logic).", "ok")
        elif p.kind == "evt" and p.event == "CONFIRM_TIMEOUT":
            self.msg("Panel: CONFIRM not pressed within 60 s. Still HOLD: RO+UV.", "warn")
        elif p.kind == "evt" and p.event == "BUTTON_IGNORED":
            self.msg("Panel: button pressed but nothing to confirm (ignored).", "info")
        elif p.kind == "ready":
            if self._ready_seen:
                self.msg(f"Panel rebooted (USB reconnect?). It reports {p.state} from its memory.", "warn")
            else:
                self.msg(f"Panel linked. It reports {p.state} from its memory.", "ok")
            self._ready_seen = True

    # ------------------------------------------------------------ loading
    def reload_roi(self):
        self.roi = load_roi(rpath(self.cfg["roi_file"]))
        self.ref_frame = self.empty_frame = None
        self.roi_hash = None
        if self.roi:
            self.ref_frame = cv2.imread(str(ROOT / self.roi["reference_frame"]))
            if self.roi.get("empty_tray_frame"):
                self.empty_frame = cv2.imread(str(ROOT / self.roi["empty_tray_frame"]))
            self.roi_hash = roi_hash(self.roi)

    def reload_models(self):
        self.model_error = ""
        try:
            self.frozen_model = load_frozen()
        except Exception as e:
            self.frozen_model = None
            self.model_error = str(e)
        self.latest_model = load_any(LATEST_MODEL) if LATEST_MODEL.exists() else None

    def model_for(self, mode):
        if mode in FROZEN_MODES:
            return self.frozen_model
        return self.frozen_model or self.latest_model

    @property
    def camera_hash(self):
        fr = self.cam_check[2]
        return settings_hash(fr) if fr else None

    # ------------------------------------------------------------ background loops
    def _preview_loop(self):
        period = 1.0 / max(0.5, float(self.cfg["web"].get("preview_fps", 2)))
        while not self._stop.is_set():
            try:
                fr = self.preview_cam.grab(self.cfg["frame_endpoint"], check_fresh=False)
                with self.lock:
                    self.preview = fr
                    self.preview_ok_t = time.time()
                    self.preview_err = ""
            except Exception as e:
                from .adbfwd import ensure_forward
                fwd = ensure_forward(self.cfg)          # cable replugged -> forward is gone; redo it
                with self.lock:
                    self.preview_err = str(e) + (f" | {fwd}" if fwd else "")
            self._stop.wait(period)

    def _camcheck_loop(self):
        while not self._stop.is_set():
            self.refresh_cam_check()
            self._stop.wait(10.0)

    def refresh_cam_check(self):
        res = check_camera(self.status_cam, self.cfg, rpath(self.cfg["camera_settings_file"]))
        with self.lock:
            self.cam_check = res
            self.cam_check_t = time.time()
        return res

    # ------------------------------------------------------------ session
    def open_session(self, purpose, operator):
        info = {"lighting_mode": self.cfg["lighting_mode"], "camera_settings_hash": self.camera_hash,
                "roi_hash": self.roi_hash, "quality_thresholds_hash": stable_hash(quality_thresholds(self.cfg)),
                "read_time_s": self.cfg["read_time_s"],
                "model_sha256": (self.model_for(purpose).sha if self.model_for(purpose) else None)}
        if purpose in FROZEN_MODES:
            ok, why = self.checklist(purpose)
            if not ok:
                raise RuntimeError("cannot open a %s session: %s" % (purpose, "; ".join(why)))
        self.session = new_session(purpose, operator, info)
        self.session_meta = load_session(self.session)
        self.msg(f"Session {self.session.name} opened.", "ok")
        return self.session

    # ------------------------------------------------------------ checklist
    def checklist_items(self, mode=None):
        mode = mode or (self.session_meta or {}).get("purpose")
        items = []
        snap = self.panel.snapshot()
        items.append(("Arduino linked", self.panel.link_ok(),
                      "" if self.panel.link_ok() else (snap.error or "waiting for the panel on USB")))
        ph_ok = time.time() - self.preview_ok_t < 3.0
        items.append(("Phone reachable", ph_ok, "" if ph_ok else (self.preview_err or "no frames yet")))
        cok, cprob, _ = self.cam_check
        items.append(("Camera locked", cok, "" if cok else "; ".join(cprob[:3])))
        rok = self.roi is not None and self.ref_frame is not None
        why = "" if rok else "no roi.json; calibrate the regions"
        if rok and self.empty_frame is None:
            rok, why = False, "no empty-tray reference; recalibrate and capture the empty tray"
        items.append(("ROI loaded", rok, why))
        if mode in FROZEN_MODES:
            m = self.frozen_model
            if m is None:
                items.append(("Model frozen", False, self.model_error or "no frozen model; train and freeze first"))
            else:
                probs = []
                if m.d.get("roi_hash") != self.roi_hash:
                    probs.append("ROI changed since the model was frozen")
                if m.d.get("camera_settings_hash") != self.camera_hash:
                    probs.append("camera settings differ from the model's")
                if m.d.get("quality_thresholds") != quality_thresholds(self.cfg):
                    probs.append("quality thresholds in config.yaml differ from the frozen ones")
                if m.d.get("read_time_s") != self.cfg["read_time_s"]:
                    probs.append("read time differs from the frozen one")
                if m.d.get("correction_mode", "three_point") != self.cfg.get("correction_mode", "three_point"):
                    probs.append("colour correction mode differs from the frozen one")
                items.append(("Model frozen", not probs, "; ".join(probs)))
        items.append(("Session open", self.session is not None,
                      "" if self.session is not None else "start a session first"))
        busy = self.job is not None and not self.job.progress.get("done")
        items.append(("No read running", not busy, "a read is in progress" if busy else ""))
        return items

    def checklist(self, mode=None):
        """Checklist for opening a session (everything except 'Session open')."""
        items = self.checklist_items(mode)
        bad = [f"{n}: {w}" for n, ok, w in items if not ok and n != "Session open"]
        return (not bad), bad

    def can_start(self):
        items = self.checklist_items()
        bad = [f"{n}: {w}" for n, ok, w in items if not ok]
        return (not bad), bad

    def stop(self):
        self._stop.set()
        self.panel.close()
