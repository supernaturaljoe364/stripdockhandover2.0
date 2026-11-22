"""The frozen model must match the current setup before test/degraded/demo reads (D-20, D-43)."""
import copy

from app.config import load_config, quality_thresholds
from app.station import frozen_mismatches, roi_locate_params


def _model_d(cfg):
    return {"roi_hash": "r1", "camera_settings_hash": "c1", "quality_thresholds": quality_thresholds(cfg),
            "roi_locate": roi_locate_params(cfg), "read_time_s": cfg["read_time_s"],
            "correction_mode": cfg.get("correction_mode", "three_point")}


def test_matching_setup_has_no_problems():
    cfg = load_config()
    assert frozen_mismatches(_model_d(cfg), cfg, "r1", "c1") == []


def test_each_change_is_reported():
    cfg = load_config()
    md = _model_d(cfg)
    assert any("ROI changed" in p for p in frozen_mismatches(md, cfg, "r2", "c1"))
    assert any("camera" in p for p in frozen_mismatches(md, cfg, "r1", "c2"))
    for key, val in [(("quality", "black_L_max"), 99.0), (("roi", "shift_tol_px"), 40),
                     (("roi", "search_px"), 80), (("roi", "min_match_score"), 0.3)]:
        c2 = copy.deepcopy(cfg)
        c2[key[0]][key[1]] = val
        probs = frozen_mismatches(md, c2, "r1", "c1")
        assert probs, f"changing {key} after freezing must block test mode"
    c3 = copy.deepcopy(cfg)
    c3["read_time_s"] = 30
    assert any("read time" in p for p in frozen_mismatches(md, c3, "r1", "c1"))
    c4 = copy.deepcopy(cfg)
    c4["correction_mode"] = "three_point" if cfg.get("correction_mode") == "white_gain" else "white_gain"
    assert any("correction" in p for p in frozen_mismatches(md, c4, "r1", "c1"))


def test_model_without_roi_locate_still_loads():
    """Models frozen before D-43 have no roi_locate field; they are judged on the other fields."""
    cfg = load_config()
    md = _model_d(cfg)
    del md["roi_locate"]
    assert frozen_mismatches(md, cfg, "r1", "c1") == []
