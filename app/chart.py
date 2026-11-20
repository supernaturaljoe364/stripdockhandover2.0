"""Chart definitions, unit conversion and block logic."""
from __future__ import annotations

import json
import math
from pathlib import Path

NO3N_TO_NO3 = 1.0 / 0.2259   # 1 mg/L NO3-N = 4.427 mg/L NO3-
NO3_TO_NO3N = 0.2259


def to_no3(value: float, unit: str) -> float:
    """Convert a nitrate value to mg/L NO3- (the internal unit)."""
    u = unit.strip().upper().replace(" ", "").replace("⁻", "-").replace("₃", "3")
    if u in ("NO3", "NO3-", "MG/LNO3", "MG/LNO3-", "NITRATE"):
        return float(value)
    if u in ("NO3-N", "NO3N", "MG/LNO3-N", "NITRATE-N", "N"):
        return float(value) * NO3N_TO_NO3
    raise ValueError(f"unknown nitrate unit: {unit!r}")


def load_chart(path: Path | str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        chart = json.load(f)
    n = chart["nitrate"]
    factor = float(n.get("to_no3_factor", 1.0))
    chart["blocks_no3"] = [b * factor for b in n["blocks_mg_L"]]
    return chart


def _lc(c: float, offset: float = 1.0) -> float:
    return math.log(max(c, 0.0) + offset)


def nearest_block(conc: float, blocks: list[float], offset: float = 1.0) -> float:
    """Nearest chart block in log(c + offset) space."""
    return min(blocks, key=lambda b: abs(_lc(conc, offset) - _lc(b, offset)))


def acceptable_blocks(true_conc: float, blocks: list[float]) -> list[float]:
    """"Within one block" definition (results file states it):
    - on a block: that block or either neighbour;
    - between two blocks: either bracketing block."""
    blocks = sorted(blocks)
    for i, b in enumerate(blocks):
        if abs(true_conc - b) < 1e-9:
            return blocks[max(0, i - 1): i + 2]
    for i in range(len(blocks) - 1):
        if blocks[i] < true_conc < blocks[i + 1]:
            return [blocks[i], blocks[i + 1]]
    if true_conc > blocks[-1]:
        return [blocks[-1]]
    return [blocks[0]]
