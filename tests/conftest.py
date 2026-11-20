import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "synthetic"))

from app.config import load_config  # noqa: E402


@pytest.fixture
def cfg():
    return copy.deepcopy(load_config())
