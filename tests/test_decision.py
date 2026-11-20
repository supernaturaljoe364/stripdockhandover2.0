import itertools
import math

from app.decision import DISPLAY, HOLD, PASS, UNKNOWN, decide

H = 25.0
BAND = 18.0
REJ = 5.0


def p(est, dist=1.0):
    return {"est": est, "distance": dist}


def test_quality_fail_is_unknown():
    v = decide(False, ["light leak"], p(100), REJ, H, BAND)
    assert v.command == UNKNOWN and v.reasons == ["light leak"]
    v = decide(False, [], p(0), REJ, H, BAND)          # even a clean-looking low reading
    assert v.command == UNKNOWN


def test_no_model_is_unknown():
    assert decide(True, [], None, None, H, None).command == UNKNOWN
    assert decide(True, [], p(5), None, H, BAND).command == UNKNOWN


def test_off_curve_is_unknown():
    assert decide(True, [], p(5, dist=9.0), REJ, H, BAND).command == UNKNOWN


def test_nan_is_unknown():
    assert decide(True, [], p(float("nan")), REJ, H, BAND).command == UNKNOWN
    assert decide(True, [], {"est": 5, "distance": float("inf")}, REJ, H, BAND).command == UNKNOWN


def test_hold_at_and_above_block():
    assert decide(True, [], p(25.0), REJ, H, BAND).command == HOLD
    assert decide(True, [], p(250), REJ, H, BAND).command == HOLD
    v = decide(True, [], p(25.0), REJ, H, BAND)
    assert not v.borderline


def test_borderline_band_holds():
    v = decide(True, [], p(20.0), REJ, H, BAND)
    assert v.command == HOLD and v.borderline
    v = decide(True, [], p(18.0), REJ, H, BAND)
    assert v.command == HOLD and v.borderline


def test_pass_below_band():
    v = decide(True, [], p(17.9), REJ, H, BAND)
    assert v.command == PASS
    assert decide(True, [], p(0.0), REJ, H, BAND).command == PASS
    assert decide(True, [], p(17.9), REJ, H, None).command == PASS   # band disabled


def test_unknown_never_maps_to_pass():
    # exhaustive grid: any failing condition must never produce PASS
    for q_ok, est, dist, has_model in itertools.product([True, False], [0, 5, 17, 20, 25, 60, math.nan],
                                                        [0.5, 4.9, 5.1, 50], [True, False]):
        v = decide(q_ok, ["x"], p(est, dist) if has_model else None, REJ if has_model else None, H, BAND)
        bad = (not q_ok) or (not has_model) or dist > REJ or math.isnan(est)
        if bad:
            assert v.command == UNKNOWN
        if v.command == PASS:
            assert q_ok and has_model and dist <= REJ and est < BAND


def test_wording_never_safe():
    for text in DISPLAY.values():
        assert "safe" not in text.lower()
    assert DISPLAY[HOLD] == "HOLD: RO+UV"
    assert DISPLAY[PASS] == "Adaptive mode (TDS logic)"
    assert DISPLAY[UNKNOWN] == "UNKNOWN: re-test"
