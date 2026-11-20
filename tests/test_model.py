"""Curve + centroid models, rejection, LOSO, train/freeze/load, on SYNTHETIC data only."""
import json
import os
import stat

import numpy as np
import pytest
from synth import pad_lab
from synth_training import synthetic_samples

from app.chart import load_chart
from app.config import ROOT
from app.model import (CentroidModel, CurveModel, LoadedModel, freeze, load_frozen, loso,
                       save_model, train_all)

BLOCKS = load_chart(ROOT / "data" / "chart" / "chart.json")["blocks_no3"]


@pytest.fixture(scope="module")
def samples():
    import copy

    from app.config import load_config
    return synthetic_samples(copy.deepcopy(load_config()))


def test_curve_interpolates_unseen_level():
    pts = [{"sample_id": f"s{c}", "conc": c, "lab": pad_lab(c).tolist()} for c in (0, 10, 25, 50, 100)]
    m = CurveModel(1.0).fit(pts)
    for c in (0, 10, 25, 50, 100):
        assert m.predict(pad_lab(c))["est"] == pytest.approx(c, abs=0.5)
    p = m.predict(pad_lab(35))                 # synthetic response is linear in log(c+1)
    assert p["est"] == pytest.approx(35, rel=0.05)
    assert p["distance"] < 0.5


def test_curve_far_point_has_large_distance():
    pts = [{"sample_id": f"s{c}", "conc": c, "lab": pad_lab(c).tolist()} for c in (0, 25, 100)]
    m = CurveModel(1.0).fit(pts)
    assert m.predict([60.0, -30.0, 40.0])["distance"] > 30     # green: not on the curve


def test_centroid_model():
    pts = [{"sample_id": f"s{c}", "conc": c, "lab": pad_lab(c).tolist()} for c in (0, 10, 25, 50, 100)]
    m = CentroidModel(1.0).fit(pts)
    assert m.predict(pad_lab(25))["est"] == pytest.approx(25, abs=0.5)
    assert 25 < m.predict(pad_lab(35))["est"] < 50


def test_needs_two_standards():
    with pytest.raises(ValueError):
        CurveModel().fit([{"sample_id": "a", "conc": 0, "lab": [90, 0, 0]}])


def test_loso_and_train_all(cfg, samples):
    rows = loso(CurveModel, samples, 1.0)
    assert len(rows) == len(samples) == 21
    d = train_all(samples, cfg, BLOCKS)
    assert d["primary"] in ("curve", "centroid")
    for name in ("curve", "centroid"):
        thr = d["methods"][name]["thresholds"]
        assert thr["reject_dE"] >= cfg["model"]["reject_floor_dE"]
        assert 0 < thr["band_low_mg_L"] <= 25
        s = d["methods"][name]["summary"]
        assert s["n"] == 21
    # on clean synthetic data, LOSO should miss nothing at or above the hold block
    assert d["methods"][d["primary"]]["summary"]["missed_ge_hold"] == 0


def test_rejection_threshold_rejects_off_curve(cfg, samples):
    d = train_all(samples, cfg, BLOCKS)
    lm = LoadedModel(d)
    p = lm.predict([60.0, -30.0, 40.0])
    assert p["distance"] > lm.thr["reject_dE"]
    p = lm.predict(pad_lab(45))
    assert p["distance"] <= lm.thr["reject_dE"]
    assert p["est"] >= 25


def test_save_freeze_load_and_tamper(cfg, samples, tmp_path):
    d = train_all(samples, cfg, BLOCKS)
    d.update({"roi_hash": "r", "camera_settings_hash": "c", "quality_thresholds": cfg["quality"],
              "synthetic": True})
    src = tmp_path / "model_latest.json"
    sha = save_model(d, src)
    assert (tmp_path / "model_latest.sha256").read_text().startswith(sha)
    fdir = tmp_path / "frozen"
    dst = freeze(src, fdir)
    assert not os.access(dst, os.W_OK)                       # read-only
    lm = load_frozen(fdir)
    assert lm.frozen and lm.d["frozen_at"]
    # tamper: make writable, edit, reload -> hash mismatch
    os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
    j = json.loads(dst.read_text())
    j["methods"][j["primary"]]["thresholds"]["reject_dE"] = 99
    dst.write_text(json.dumps(j))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        load_frozen(fdir)
    assert load_frozen(tmp_path / "none") is None
