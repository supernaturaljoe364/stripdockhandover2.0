"""Every quality check, exercised on SYNTHETIC images from tests/synthetic/synth.py."""
import numpy as np
import pytest
from synth import REGIONS, render, roi_dict

from app import quality as Q
from app.features import measure_frame
from app.roi import locate


@pytest.fixture(scope="module")
def ref():
    return render(25, seed=1)


def meas(cfg, ref, **kw):
    f = render(kw.pop("conc", 25), seed=kw.pop("seed", 2), **kw)
    loc = locate(roi_dict(), ref, f)
    return loc, measure_frame(f, loc.regions, cfg)


def test_good_frame_passes_all(cfg, ref):
    q = cfg["quality"]
    loc, m = meas(cfg, ref)
    assert loc.ok
    assert Q.check_light_leak([m["raw_lab"]["black"][0]] * 3, q).passed
    assert Q.check_exposure(m["raw_lab"]["white"][0], m["white_clip_frac"], q).passed
    assert Q.check_glare(m["pad_glare_frac"], q).passed
    assert Q.check_blur(m["sharpness"], q).passed
    assert Q.check_reference(m["grey_chroma"], q).passed


def test_light_leak_level(cfg, ref):
    _, m = meas(cfg, ref, stray=0.03)
    c = Q.check_light_leak([m["raw_lab"]["black"][0]], cfg["quality"])
    assert not c.passed and "light leak" in c.reason


def test_light_leak_jump(cfg, ref):
    _, a = meas(cfg, ref)
    _, b = meas(cfg, ref, stray=0.012, seed=3)     # small leak: under the level limit, but a jump
    series = [a["raw_lab"]["black"][0], a["raw_lab"]["black"][0], b["raw_lab"]["black"][0]]
    assert max(series) <= cfg["quality"]["black_L_max"]
    c = Q.check_light_leak(series, cfg["quality"])
    assert not c.passed and "jumped" in c.reason


def test_exposure_dark_and_clipped(cfg, ref):
    _, m = meas(cfg, ref, exposure=0.3)
    assert not Q.check_exposure(m["raw_lab"]["white"][0], m["white_clip_frac"], cfg["quality"]).passed
    _, m = meas(cfg, ref, exposure=1.6)
    assert not Q.check_exposure(m["raw_lab"]["white"][0], m["white_clip_frac"], cfg["quality"]).passed
    _, m = meas(cfg, ref, cast=(1.2, 1.0, 0.75))   # red channel clips while L* is in range
    c = Q.check_exposure(m["raw_lab"]["white"][0], m["white_clip_frac"], cfg["quality"])
    assert not c.passed and "clipped" in c.reason


def test_glare(cfg, ref):
    _, m = meas(cfg, ref, glare=0.15)
    c = Q.check_glare(m["pad_glare_frac"], cfg["quality"])
    assert not c.passed and "glare" in c.reason


def test_blur(cfg, ref):
    _, m = meas(cfg, ref, blur=4)
    c = Q.check_blur(m["sharpness"], cfg["quality"])
    assert not c.passed and "blur" in c.reason


def test_timing():
    assert not Q.check_timing(20.0, 60).passed
    assert not Q.check_timing(59.9, 60).passed
    assert Q.check_timing(60.0, 60).passed


def test_drift(cfg, ref):
    q = cfg["quality"]
    stable = [meas(cfg, ref, seed=s)[1]["corr_lab"]["nitrate_pad"] for s in (2, 3, 4)]
    assert Q.check_drift(stable, q).passed
    developing = [meas(cfg, ref, conc=c, seed=2)[1]["corr_lab"]["nitrate_pad"] for c in (10, 25, 50)]
    c = Q.check_drift(developing, q)
    assert not c.passed and "still developing" in c.reason
    assert not Q.check_drift(stable[:1], q).passed


def test_strip_present(cfg):
    q = cfg["quality"]
    from app.colour import delta_e2000, rgb8_to_lab
    from app.roi import crop, shrink
    empty = render(None, seed=5)
    r = shrink(REGIONS["nitrate_pad"], 0.2)

    def lab(img):
        return rgb8_to_lab(np.median(crop(img, r)[..., ::-1].reshape(-1, 3), axis=0))
    for conc, expect in ((0, True), (100, True)):
        f = render(conc, seed=6)
        dE = float(delta_e2000(lab(f), lab(empty)))
        diff = float(np.mean(np.abs(crop(f, r).astype(float) - crop(empty, r).astype(float))))
        assert Q.check_strip_present(dE, diff, q).passed is expect
    f = render(None, seed=7)
    dE = float(delta_e2000(lab(f), lab(empty)))
    diff = float(np.mean(np.abs(crop(f, r).astype(float) - crop(empty, r).astype(float))))
    c = Q.check_strip_present(dE, diff, q)
    assert not c.passed and "no strip" in c.reason
    assert not Q.check_strip_present(None, None, q).passed


def test_phone(cfg):
    q = cfg["quality"]
    assert Q.check_phone([], [0.1, 0.2], q).passed
    assert not Q.check_phone(["read0: timeout"], [0.1], q).passed
    assert not Q.check_phone([], [0.1, 2.5], q).passed
    assert not Q.check_phone([], [], q).passed


def test_seated(cfg, ref):
    loc, _ = meas(cfg, ref, shift=(20, 0))
    c = Q.check_seated([loc.ok], [loc.reason])
    assert not c.passed and "not seated" in c.reason
    loc, _ = meas(cfg, ref, strip_shift=(0, 20))
    assert not Q.check_seated([loc.ok], [loc.reason]).passed
    loc, _ = meas(cfg, ref, shift=(8, -5))      # inside tolerance
    assert loc.ok and loc.patch_shift == (8, -5)
    assert Q.check_seated([True, True], ["", ""]).passed


def test_strip_tolerance_wider_with_strong_match(ref):
    """D-39/D-44: the strip tip may sit up to strip_tol px off if it is matched strongly;
    the patch row keeps the normal tolerance."""
    f = render(25, seed=2, strip_shift=(0, 35))
    assert not locate(roi_dict(), ref, f, tol=30, search=60).ok                 # original rule: 35 > 30
    loc = locate(roi_dict(), ref, f, tol=30, search=60, strip_tol=40)
    assert loc.ok and loc.strip_shift == (0, 35) and loc.strip_score >= 0.75
    assert loc.regions["nitrate_pad"][1] == REGIONS["nitrate_pad"][1] + 35   # pad follows the strip
    weak = locate(roi_dict(), ref, f, tol=30, search=60, strip_tol=40, strip_min_score=1.01)
    assert not weak.ok and "weak tip match" in weak.reason
    far = locate(roi_dict(), ref, render(25, seed=2, strip_shift=(0, 48)), tol=30, search=60, strip_tol=40)
    assert not far.ok and "strip moved 48 px (> 40)" in far.reason
    tray = locate(roi_dict(), ref, render(25, seed=2, shift=(0, 35)), tol=30, search=60, strip_tol=40)
    assert not tray.ok and "camera/dock moved" in tray.reason                   # patches stay at tol


def test_reference_inconsistent(cfg):
    assert not Q.check_reference(12.0, cfg["quality"]).passed
    assert Q.check_reference(1.0, cfg["quality"]).passed


def test_gate():
    ok, why = Q.gate([Q.Check("a", True, 1, ""), Q.Check("b", False, 2, "", "bad b")])
    assert not ok and why == ["bad b"]
