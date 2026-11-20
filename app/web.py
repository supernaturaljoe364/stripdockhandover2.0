"""Local web app at http://localhost:5000 (Flask)."""
from __future__ import annotations

import logging
import threading
import time
import uuid

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

from .config import ROOT, rpath
from .decision import DISPLAY
from .readflow import ReadJob
from .roi import REQUIRED, OPTIONAL, locate, save_roi, shrink
from .session import DEGRADATIONS, PURPOSES, close_session

COLOURS = {"nitrate_pad": (255, 0, 255), "nitrite_pad": (255, 160, 0), "white": (255, 255, 255),
           "grey": (160, 160, 160), "black": (0, 200, 255), "anchor": (0, 255, 0)}


def create_app(station):
    app = Flask(__name__, template_folder=str(ROOT / "app" / "templates"),
                static_folder=str(ROOT / "app" / "static"))
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    st = station
    calib_frames: dict[str, np.ndarray] = {}

    @app.get("/")
    def index():
        return render_template("index.html", purposes=PURPOSES, degradations=DEGRADATIONS)

    @app.get("/calibrate")
    def calibrate_page():
        return render_template("calibrate.html", required=REQUIRED, optional=OPTIONAL)

    # ------------------------------------------------------------ state
    @app.get("/api/state")
    def api_state():
        snap = st.panel.snapshot()
        if snap.state == "CONFIRM_WAIT":
            st.confirm_since = st.confirm_since or time.time()
        else:
            st.confirm_since = None
        job = st.job
        items = st.checklist_items()
        can, why = st.can_start()
        mode = (st.session_meta or {}).get("purpose")
        m = st.model_for(mode) if mode else (st.frozen_model or st.latest_model)
        res = st.last_result
        # Test mode: nothing about the true value is known to the app; the verdict is the device output.
        return jsonify({
            "panel": {"connected": snap.connected, "state": snap.state, "port": snap.port,
                      "link_ok": st.panel.link_ok(), "error": snap.error,
                      "confirm_left_s": (max(0, 60 - (time.time() - st.confirm_since))
                                         if st.confirm_since else None)},
            "phone": {"ok": time.time() - st.preview_ok_t < 3.0, "error": st.preview_err,
                      "torch_needed": st.cfg["lighting_mode"] == "phone_torch"},
            "checklist": [{"name": n, "ok": ok, "why": w} for n, ok, w in items],
            "can_start": can, "why_not": why,
            "session": None if st.session is None else {"name": st.session.name, **(st.session_meta or {})},
            "model": None if m is None else {"file": m.path.name if m.path else None, "frozen": m.frozen,
                                             "primary": m.primary},
            "job": None if job is None else {**job.progress, "sample_id": job.sample_id, "mode": job.mode},
            "last": res,
            "messages": st.messages[-8:],
            "display": DISPLAY,
        })

    # ------------------------------------------------------------ preview
    @app.get("/api/preview.jpg")
    def preview():
        fr = st.preview
        if fr is None:
            img = np.zeros((360, 640, 3), np.uint8)
            cv2.putText(img, "no phone frame", (150, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (80, 80, 255), 2)
        else:
            img = fr.bgr.copy()
            if st.roi and st.ref_frame is not None and st.ref_frame.shape == img.shape:
                loc = locate(st.roi, st.ref_frame, img, int(st.cfg["roi"]["shift_tol_px"]),
                             int(st.cfg["roi"]["search_px"]), float(st.cfg["roi"]["min_match_score"]))
                for name, r in loc.regions.items():
                    c = COLOURS.get(name, (0, 255, 0))[::-1]
                    x, y, w, h = r
                    cv2.rectangle(img, (x, y), (x + w, y + h), c, 3)
                    sx, sy, sw, sh = shrink(r, st.cfg["roi"]["shrink_frac"])
                    cv2.rectangle(img, (sx, sy), (sx + sw, sy + sh), c, 1)
                    cv2.putText(img, name, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, c, 2)
                if not loc.ok:
                    cv2.putText(img, "NOT SEATED: " + loc.reason[:60], (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
            img = cv2.resize(img, (960, int(960 * img.shape[0] / img.shape[1])))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return Response(buf.tobytes(), mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------ session
    @app.post("/api/session/new")
    def session_new():
        d = request.get_json(force=True)
        try:
            if st.job is not None and not st.job.progress.get("done"):
                raise RuntimeError("a read is running")
            p = st.open_session(d.get("purpose", ""), d.get("operator", "").strip() or "unknown")
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": True, "session": p.name})

    @app.post("/api/session/close")
    def session_close():
        if st.session is None:
            return jsonify({"ok": False, "error": "no session open"}), 400
        if st.job is not None and not st.job.progress.get("done"):
            return jsonify({"ok": False, "error": "a read is running"}), 400
        name = st.session.name
        close_session(st.session)
        st.session = None
        st.session_meta = None
        st.msg(f"Session {name} closed and locked (read-only + MANIFEST.sha256).", "ok")
        return jsonify({"ok": True, "closed": name})

    # ------------------------------------------------------------ read
    @app.post("/api/read/start")
    def read_start():
        d = request.get_json(force=True)
        t_press = time.time()          # the timer starts at the START press (rule 1)
        can, why = st.can_start()
        if not can:
            return jsonify({"ok": False, "error": "START blocked: " + "; ".join(why)}), 400
        mode = st.session_meta["purpose"]
        sid = (d.get("sample_id") or "").strip()
        if not sid:
            return jsonify({"ok": False, "error": "enter the sample code"}), 400
        extra = {}
        if mode == "train":
            try:
                extra["concentration_mg_L"] = float(d.get("concentration"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "enter the known concentration (mg/L NO3-)"}), 400
        if mode == "degraded":
            if d.get("degradation") not in DEGRADATIONS:
                return jsonify({"ok": False, "error": "choose which degradation was done"}), 400
            extra["degradation"] = d["degradation"]
        if d.get("note"):
            extra["note"] = str(d["note"])[:200]
        send = bool(d.get("send_to_panel", True))
        st.job = ReadJob(st, st.session, mode, sid, extra, send_to_panel=send, t_start=t_press).start()

        def finish(job=st.job):
            job.thread.join()
            if job.result and not job.result.get("cancelled"):
                st.last_result = {**job.result, "sample_id": job.sample_id, "mode": job.mode}
                v = job.result["verdict"]
                st.msg(f"{job.sample_id}: {v['display']} ({'; '.join(v['reasons'][:2])})",
                       "warn" if v["command"] != "PASS" else "ok")
                if job.result.get("panel_reply") is None and job.send_to_panel:
                    st.msg("Verdict NOT delivered to the panel (not linked). Re-test once linked.", "warn")
                elif v["command"] == "PASS" and job.result.get("panel_reply") == "CONFIRM_WAIT":
                    st.msg("Press CONFIRM on the panel within 60 s to clear the hold.", "warn")
        threading.Thread(target=finish, daemon=True).start()
        return jsonify({"ok": True})

    @app.post("/api/read/cancel")
    def read_cancel():
        if st.job is not None:
            st.job.cancel()
        return jsonify({"ok": True})

    @app.post("/api/panel/send")
    def panel_send():
        # Service use only. PASS is not offered here: clearing a hold needs a real passing read.
        cmd = (request.get_json(force=True).get("cmd") or "").upper()
        if cmd not in ("HOLD", "UNKNOWN", "STATUS"):
            return jsonify({"ok": False, "error": "only HOLD, UNKNOWN, STATUS from the service panel"}), 400
        r = st.panel.send(cmd)
        st.msg(f"Service: sent {cmd}, panel replied {r}", "info")
        return jsonify({"ok": r is not None, "state": r})

    @app.get("/api/panel/log")
    def panel_log():
        snap = st.panel.snapshot()
        return jsonify({"events": [{"t": time.strftime("%H:%M:%S", time.localtime(e["t"])), "dir": e["dir"],
                                    "text": e["text"]} for e in snap.events],
                        "threads": [t.name for t in threading.enumerate()]})

    @app.post("/api/camcheck")
    def camcheck():
        ok, probs, _ = st.refresh_cam_check()
        return jsonify({"ok": ok, "problems": probs})

    # ------------------------------------------------------------ calibration
    @app.post("/api/calib/grab")
    def calib_grab():
        try:
            fr = st.read_cam.grab(st.cfg["frame_endpoint"], timeout=5.0, check_fresh=False)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        fid = uuid.uuid4().hex[:8]
        calib_frames[fid] = fr.bgr
        return jsonify({"ok": True, "id": fid, "w": fr.bgr.shape[1], "h": fr.bgr.shape[0]})

    @app.get("/api/calib/frame/<fid>.jpg")
    def calib_frame(fid):
        img = calib_frames.get(fid)
        if img is None:
            return "not found", 404
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return Response(buf.tobytes(), mimetype="image/jpeg")

    @app.get("/api/calib/current")
    def calib_current():
        return jsonify({"roi": st.roi})

    @app.post("/api/calib/save")
    def calib_save():
        d = request.get_json(force=True)
        img = calib_frames.get(d.get("frame_id"))
        empty = calib_frames.get(d.get("empty_id")) if d.get("empty_id") else None
        if img is None:
            return jsonify({"ok": False, "error": "grab a frame with a strip first"}), 400
        regs = {k: [int(round(v)) for v in r] for k, r in (d.get("regions") or {}).items() if r}
        missing = [k for k in REQUIRED if k not in regs]
        if missing:
            return jsonify({"ok": False, "error": f"missing regions: {missing}"}), 400
        if empty is None:
            return jsonify({"ok": False, "error": "capture the EMPTY tray frame too (needed for the no-strip check)"}), 400
        if (st.frozen_model is not None) and not d.get("confirm_overwrite"):
            return jsonify({"ok": False, "error": "a frozen model exists: a new ROI invalidates it. "
                                                  "Tick 'I understand' to overwrite."}), 400
        save_roi(rpath(st.cfg["roi_file"]), regs, img, empty)
        st.reload_roi()
        st.msg(f"ROI saved (hash {st.roi_hash}).", "ok")
        return jsonify({"ok": True, "roi_hash": st.roi_hash})

    return app
