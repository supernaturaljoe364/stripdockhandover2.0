import numpy as np
import pytest

from app.colour import (apply_correction, delta_e2000, fit_correction, lch, linear_rgb_to_lab,
                        rgb8_to_lab, srgb_to_linear)

# Sharma, Wu, Dalal (2005) CIEDE2000 test data (pairs 1, 2, 7, 17, 25, 33)
SHARMA = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("a,b,expected", SHARMA)
def test_de2000_sharma(a, b, expected):
    assert delta_e2000(a, b) == pytest.approx(expected, abs=1e-4)
    assert delta_e2000(b, a) == pytest.approx(expected, abs=1e-4)


def test_de2000_vectorised():
    a = np.array([p[0] for p in SHARMA])
    b = np.array([p[1] for p in SHARMA])
    np.testing.assert_allclose(delta_e2000(a, b), [p[2] for p in SHARMA], atol=1e-4)


def test_lab_white_black():
    np.testing.assert_allclose(rgb8_to_lab([255, 255, 255]), [100, 0, 0], atol=0.05)
    np.testing.assert_allclose(rgb8_to_lab([0, 0, 0]), [0, 0, 0], atol=1e-6)
    L, a, b = rgb8_to_lab([255, 0, 0])
    assert L == pytest.approx(53.24, abs=0.05) and a == pytest.approx(80.09, abs=0.1)


def test_correction_removes_cast():
    # true neutral patches and a pink pad, seen under a warm cast plus a small offset
    true = {"k": np.full(3, 0.03), "g": np.full(3, 0.22), "w": np.full(3, 0.85),
            "pad": np.array([0.70, 0.35, 0.50])}
    cast, off = np.array([1.25, 1.0, 0.72]), np.array([0.01, 0.006, 0.004])
    seen = {k: v * cast + off for k, v in true.items()}
    corr = fit_correction(seen["k"], seen["g"], seen["w"])
    assert corr["method"] == "three_point"
    pad = linear_rgb_to_lab(apply_correction(seen["pad"], corr))
    grey = linear_rgb_to_lab(apply_correction(seen["g"], corr))
    assert lch(grey)[0] < 0.5                                  # grey comes out neutral
    assert delta_e2000(pad, linear_rgb_to_lab(true["pad"])) < 1.5


def test_correction_falls_back_to_white_gain():
    corr = fit_correction([0.05, 0.05, 0.05], [0.04, 0.3, 0.3], [0.8, 0.8, 0.8])  # grey < black in R
    assert corr["method"] == "white_gain"
    corr = fit_correction([0, 0, 0], [0.1, 0.1, 0.1], [0, 0, 0])
    assert corr["method"] == "invalid"


def test_srgb_linear_roundtrip():
    from app.colour import linear_to_srgb
    x = np.linspace(0, 1, 50)
    np.testing.assert_allclose(linear_to_srgb(srgb_to_linear(x)), x, atol=1e-9)


def test_white_gain_mode_is_fixed():
    corr = fit_correction([0.03] * 3, [0.22] * 3, [0.85] * 3, mode="white_gain")
    assert corr["method"] == "white_gain" and corr["offset"] == [0.0, 0.0, 0.0]
