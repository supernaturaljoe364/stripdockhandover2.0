"""Whole training -> freeze -> blind test -> close -> evaluate path on SYNTHETIC data.

Everything is written under tests/synthetic/_e2e/ (never data/ or results/)."""
import copy
import csv
import re
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import pytest
from synth_training import synthetic_samples

from app.config import ROOT, load_config
from app.model import freeze, load_frozen, save_model
from app.readflow import ReadJob
from app.session import close_session, new_session

sys.path.insert(0, str(ROOT))
import evaluate  # noqa: E402
import train  # noqa: E402
from tests.test_readflow import BLOCKS, FakeCam, FakeStation  # noqa: E402

E2E = ROOT / "tests" / "synthetic" / "_e2e"


def _rm(path):
    def onerr(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=onerr)


def test_clopper_pearson_known_values():
    lo, hi = evaluate.clopper_pearson(29, 30)
    assert lo == pytest.approx(0.8278, abs=1e-3) and hi == pytest.approx(0.9992, abs=1e-3)
    lo, hi = evaluate.clopper_pearson(0, 20)
    assert lo == 0 and hi == pytest.approx(0.1684, abs=1e-3)
    lo, hi = evaluate.clopper_pearson(20, 20)
    assert lo == pytest.approx(0.8316, abs=1e-3) and hi == 1


def test_full_pipeline(monkeypatch):
    _rm(E2E)
    sess_root = E2E / "sessions"
    cfg = copy.deepcopy(load_config())
    # 1. synthetic train session in the on-disk format
    tsess = new_session("train", "pytest", {"camera_settings_hash": "CAM", "roi_hash": "ROI"}, root=sess_root)
    for s in synthetic_samples(cfg):
        d = tsess / s["sample_id"]
        (d / "frames").mkdir(parents=True)
        L, a, b = s["lab"]
        (d / "meta.json").write_text(json.dumps({
            "sample_id": s["sample_id"], "concentration_mg_L": s["conc"], "quality_ok": True,
            "features": {"pad_L": L, "pad_a": a, "pad_b": b}, "verdict": {"reasons": []}}))
    # 2. train (wrong camera hash must be refused)
    with pytest.raises(train.TrainError):
        train.collect([tsess], "OTHER", "ROI", {})
    samples, excl, warn = train.collect([tsess], "CAM", "ROI", {})
    assert len(samples) == 21 and not excl
    chart = {"blocks_no3": BLOCKS}
    d = train.build_model(samples, cfg, chart, {"roi_hash": "ROI", "camera_settings_hash": "CAM", "synthetic": True})
    save_model(d, E2E / "model_latest.json")
    train.write_reports(d, E2E / "models", E2E / "results", excl, warn)
    assert (E2E / "models" / "model_card.md").exists()
    fdir = E2E / "frozen"
    freeze(E2E / "model_latest.json", fdir)
    model = load_frozen(fdir)
    assert model.frozen

    # 3. blind test + degraded sessions read through the real ReadJob with a fake phone
    fast = copy.deepcopy(cfg)
    fast.update({"read_time_s": 2.0, "read_offsets_s": [0, 0.2, 0.4, 0.6, 0.8], "monitor_interval_s": 0.3,
                 "early_read_s": 0.8})
    test_s = new_session("test", "pytest", {}, root=sess_root)
    deg_s = new_session("degraded", "pytest", {}, root=sess_root)
    plan = [(test_s, "test", "B01", {"conc": 100}, {}), (test_s, "test", "B02", {"conc": 0}, {}),
            (test_s, "test", "B03", {"conc": 45}, {}), (test_s, "test", "B04", {"conc": 10}, {}),
            (deg_s, "degraded", "D01", {"conc": None}, {"degradation": "no_strip"}),
            (deg_s, "degraded", "D02", {"conc": 0, "blur": 4.0}, {"degradation": "blur"})]
    for sess, mode, sid, kw, extra in plan:
        st = FakeStation(fast, model)
        t0 = time.time()
        st.read_cam = FakeCam(lambda t, kw=kw: dict(kw), t0)
        job = ReadJob(st, sess, mode, sid, extra, True, t0).start()
        job.thread.join(30)
    # 4. evaluation refuses open sessions
    tmp_root = E2E / "root"
    (tmp_root / "data" / "labels").mkdir(parents=True)
    with open(tmp_root / "data" / "labels" / "test_answer_key.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "true_concentration_mg_L", "type", "tds_ppm"])
        w.writerows([["B01", 100, "spiked_tap", 210], ["B02", 0, "compliant", 150],
                     ["B03", 45, "unseen_standard", 120], ["B04", 10, "compliant", 140]])
    monkeypatch.setattr(evaluate, "ROOT", tmp_root)
    monkeypatch.setattr(evaluate, "load_frozen", lambda: model)
    monkeypatch.setattr(evaluate, "list_sessions", lambda p: [test_s] if p == "test" else [deg_s])
    monkeypatch.setattr(sys, "argv", ["evaluate.py"])
    with pytest.raises(SystemExit, match="not closed"):
        evaluate.main()
    close_session(test_s)
    close_session(deg_s)
    assert evaluate.main() == 0
    md = (tmp_root / "results" / "round3_results.md").read_text(encoding="utf-8")
    assert "Missed nitrate" in md and "not held: 0/1" in md
    assert "UNKNOWN: 2/2" in md                       # both degraded reads
    assert "within one block: 1/1" in md
    assert not re.search(r"(?<![a-z])safe(?![a-z])", md, re.I)   # "safety" is allowed, "safe" never
    rows = list(csv.DictReader(open(tmp_root / "results" / "test_reads.csv")))
    v = {r["sample_id"]: r["verdict"] for r in rows}
    assert (v["B01"], v["B02"], v["B03"]) == ("HOLD", "PASS", "HOLD")
    assert v["B04"] in ("PASS", "HOLD")              # 10 mg/L may sit in the borderline band
    assert all(r["recomputed"] == r["verdict"] for r in rows)
    _rm(E2E)
