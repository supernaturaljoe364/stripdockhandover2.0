import copy
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "synthetic"))

import app.config as _appcfg  # noqa: E402
from app.config import load_config  # noqa: E402

# The synthetic dock scene (tests/synthetic/synth.py) was designed for these quality thresholds.
# The field thresholds in config.yaml are set from real dry runs (tools/suggest_thresholds.py) and
# change with the dock, so the tests use this fixed copy: they check the LOGIC of every check, not
# the field values. Everything else (roi tolerances, read timing, model settings) is the live config.
SYNTH_QUALITY = {
    "black_L_max": 25.0, "black_jump_max": 4.0, "white_L_min": 60.0, "white_L_max": 97.0,
    "white_clip_frac_max": 0.01, "clip_level": 250, "glare_level": 240, "glare_margin": 10,
    "glare_sat_max": 0.12, "glare_frac_max": 0.02, "blur_min": 15.0, "drift_max_dE": 3.0,
    "strip_min_dE": 6.0, "strip_min_absdiff": 12.0, "grey_chroma_max": 8.0, "max_frame_age_s": 2.0,
}

_live = load_config(_appcfg.CONFIG_PATH)
_live.pop("_path", None)
_live["quality"] = dict(SYNTH_QUALITY)
_TEST_CFG = Path(tempfile.mkdtemp(prefix="stripdock_testcfg_")) / "test_config.yaml"   # outside the repo
_TEST_CFG.write_text(yaml.safe_dump(_live, sort_keys=False), encoding="utf-8")
_appcfg.CONFIG_PATH = _TEST_CFG          # load_config() with no path now reads the test copy


@pytest.fixture
def cfg():
    return copy.deepcopy(load_config())
