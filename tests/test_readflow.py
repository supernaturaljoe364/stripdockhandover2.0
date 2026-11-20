"""End-to-end read flow on SYNTHETIC frames with a fake phone and a fake panel."""
import json
import time

import cv2
import numpy as np
import pytest
from synth import render, roi_dict
from synth_training import synthetic_samples

from app.chart import load_chart
from app.config import ROOT
from app.model import LoadedModel, train_all
from app.phone import Frame, PhoneError
from app.readflow import ReadJob
from app.session import new_session

BLOCKS = load_chart(ROOT / "data" / "chart" / "chart.json")["blocks_no3"]
_CACHE = {}


def jpeg_for(kw, seed):
    key = (tuple(sorted(kw.items())), seed % 3)
    if key not in _CACHE:
        img = render(seed=seed % 3 + 10, **kw)
        _CACHE[key] = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    return _CACHE[key]


class FakeCam:
    """scenario(t_elapsed) -> render kwargs, or raises PhoneError."""

    def __init__(self, scenario, t0):
        self.scenario, self.t0, self.n = scenario, t0, 0

    def grab(self, endpoint, timeout=None, check_fresh=True):
        t = time.time()
        kw = self.scenario(t - self.t0)
        self.n += 1
        data = jpeg_for(kw, self.n)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        return Frame(img, data, t, time.time() + 0.05, endpoint, f"{self.n}")


class FakePanel:
    def __init__(self):
        self.sent = []

    def send(self, cmd):
        self.sent.append(cmd)
        return "HOLD" if cmd in ("HOLD", "UNKNOWN") else "CONFIRM_WAIT"


class FakeStation:
    def __init__(self, cfg, model):
        self.cfg = cfg
        self.roi = roi_dict()
        self.ref_frame = render(25, seed=1)
        self.empty_frame = render(None, seed=5)
        self.blocks = BLOCKS
        self.panel = FakePanel()
        self.camera_hash = "cam"
        self.roi_hash = "roi"
        self._model = model
        self.read_cam = None

    def model_for(self, mode):
        return self._model


@pytest.fixture(scope="module")
def model():
    import copy

    from app.config import load_config
    cfg = copy.deepcopy(load_config())
    return LoadedModel(train_all(synthetic_samples(cfg), cfg, BLOCKS))


@pytest.fixture
def fast_cfg(cfg):
    cfg["read_time_s"] = 2.0
    cfg["read_offsets_s"] = [0.0, 0.2, 0.4, 0.6, 0.8]
    cfg["monitor_interval_s"] = 0.3
    cfg["early_read_s"] = 0.8
    return cfg


def run(fast_cfg, model, scenario, tmp_path, mode="test", extra=None, model_on=True):
    st = FakeStation(fast_cfg, model if model_on else None)
    sess = new_session(mode, "pytest", {}, root=tmp_path)
    t0 = time.time()
    st.read_cam = FakeCam(scenario, t0)
    job = ReadJob(st, sess, mode, "S1", extra or {}, send_to_panel=True, t_start=t0).start()
    job.thread.join(30)
    assert job.progress["done"]
    return job.result, st


def test_high_nitrate_holds(fast_cfg, model, tmp_path):
    r, st = run(fast_cfg, model, lambda t: {"conc": 100}, tmp_path)
    assert r["verdict"]["command"] == "HOLD", r["verdict"]
    assert st.panel.sent == ["HOLD"]
    meta = json.loads((tmp_path.glob("*/S1/meta.json").__next__()).read_text())
    assert len(meta["frames"]) == 5
    f0 = meta["frames"][0]
    for region in ("nitrate_pad", "white", "grey", "black", "nitrite_pad"):
        assert region in f0["raw_rgb"] and region in f0["corr_lab"]
    assert meta["features"]["n_frames"] == 5
    assert meta["start_to_verdict_s"] >= 2.8
    assert all(c["passed"] for c in meta["checks"]), meta["checks"]


def test_low_nitrate_passes(fast_cfg, model, tmp_path):
    r, st = run(fast_cfg, model, lambda t: {"conc": 0}, tmp_path)
    assert r["verdict"]["command"] == "PASS", r["verdict"]
    assert st.panel.sent == ["PASS"]


def test_45_holds(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 45}, tmp_path)
    assert r["verdict"]["command"] == "HOLD"


def test_drawer_opened_mid_read(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0, "stray": 0.03 if t > 1.0 else 0.0}, tmp_path,
               mode="degraded", extra={"degradation": "drawer_open"})
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("light leak" in x for x in r["verdict"]["reasons"])


def test_phone_lost_mid_read(fast_cfg, model, tmp_path):
    def sc(t):
        if t > 1.2:
            raise PhoneError("frame request failed: timeout")
        return {"conc": 0}
    r, st = run(fast_cfg, model, sc, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"
    assert st.panel.sent == ["UNKNOWN"]


def test_no_strip(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": None}, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("no strip" in x for x in r["verdict"]["reasons"])


def test_phone_moved(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0, "shift": (25, 0)}, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("not seated" in x for x in r["verdict"]["reasons"])


def test_early_read_fails_timing(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0}, tmp_path, mode="degraded",
               extra={"degradation": "early_read"})
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("too early" in x for x in r["verdict"]["reasons"])


def test_glare(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0, "glare": 0.15}, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"


def test_blur(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0, "blur": 4.0}, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"


def test_no_model_is_unknown(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0}, tmp_path, model_on=False)
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("no calibration model" in x for x in r["verdict"]["reasons"])


def test_off_curve_colour_is_unknown(fast_cfg, model, tmp_path):
    r, _ = run(fast_cfg, model, lambda t: {"conc": 0, "pad_lab_override": (60.0, -30.0, 40.0)}, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"
    assert any("not on calibration curve" in x for x in r["verdict"]["reasons"])


def test_single_network_blip_is_retried(fast_cfg, model, tmp_path):
    state = {"failed": False}

    def sc(t):
        if t > 1.0 and not state["failed"]:
            state["failed"] = True
            raise PhoneError("frame request failed: timeout")   # one blip only
        return {"conc": 0}
    r, _ = run(fast_cfg, model, sc, tmp_path)
    assert r["verdict"]["command"] == "PASS", r["verdict"]
    meta = json.loads(next(tmp_path.glob("*/S1/meta.json")).read_text())
    assert meta["metrics"]["n_retries"] == 1 and meta["metrics"]["n_errors"] == 0


def test_retries_disabled_blip_fails(fast_cfg, model, tmp_path):
    fast_cfg["frame_retries"] = 0
    state = {"failed": False}

    def sc(t):
        if t > 1.0 and not state["failed"]:
            state["failed"] = True
            raise PhoneError("frame request failed: timeout")
        return {"conc": 0}
    r, _ = run(fast_cfg, model, sc, tmp_path)
    assert r["verdict"]["command"] == "UNKNOWN"
