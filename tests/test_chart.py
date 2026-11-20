import pytest

from app.chart import acceptable_blocks, load_chart, nearest_block, to_no3
from app.config import ROOT

BLOCKS = [0, 10, 25, 50, 100, 250, 500]


def test_units():
    assert to_no3(45, "mg/L NO3-") == 45
    assert to_no3(10.2, "NO3-N") == pytest.approx(45.15, abs=0.05)
    assert to_no3(45 * 0.2259, "NO3-N") == pytest.approx(45.0)
    with pytest.raises(ValueError):
        to_no3(1, "ppm sugar")


def test_chart_file():
    c = load_chart(ROOT / "data" / "chart" / "chart.json")
    assert c["blocks_no3"] == BLOCKS
    assert c["read_time_s"] == 60
    assert c["nitrate"]["units"] == "mg/L NO3-"


@pytest.mark.parametrize("true,ok", [
    (0, [0, 10]), (25, [10, 25, 50]), (35, [25, 50]), (45, [25, 50]), (55, [50, 100]),
    (100, [50, 100, 250]), (500, [250, 500]), (10, [0, 10, 25]),
])
def test_within_one_block(true, ok):
    assert acceptable_blocks(true, BLOCKS) == ok


def test_nearest_block():
    assert nearest_block(0.5, BLOCKS) == 0
    assert nearest_block(20, BLOCKS) == 25
    assert nearest_block(35, BLOCKS) == 25   # log midpoint of 26..51 (offset 1) is c = 35.4
    assert nearest_block(36, BLOCKS) == 50
