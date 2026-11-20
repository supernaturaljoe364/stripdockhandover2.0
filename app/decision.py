"""Decision rules (master prompt section 4; frozen, do not change without asking).

1. Read at the strip read time (enforced by the read flow + timing check).
2. Any quality failure, phone unreachable, or classifier not confident -> UNKNOWN.
3. Estimated nitrate >= the 25 mg/L block -> HOLD.
   A borderline band below 25 (from training spread) also -> HOLD.
4. Otherwise -> PASS.
5. UNKNOWN never clears a hold (the Arduino also enforces this).
6. Never say water is safe.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

HOLD, PASS, UNKNOWN = "HOLD", "PASS", "UNKNOWN"

# Wording shown on screen. Never "safe".
DISPLAY = {
    HOLD: "HOLD: RO+UV",
    PASS: "Adaptive mode (TDS logic)",
    UNKNOWN: "UNKNOWN: re-test",
}


@dataclass
class Verdict:
    command: str
    reasons: list = field(default_factory=list)
    est_mg_L: float | None = None
    block_mg_L: float | None = None
    borderline: bool = False
    distance_dE: float | None = None

    @property
    def display(self) -> str:
        return DISPLAY[self.command]

    def to_dict(self):
        d = asdict(self)
        d["display"] = self.display
        return d


def decide(quality_ok: bool, quality_reasons: list, prediction: dict | None,
           reject_dE: float | None, hold_block: float, band_low: float | None,
           block: float | None = None) -> Verdict:
    if not quality_ok:
        return Verdict(UNKNOWN, list(quality_reasons) or ["quality check failed"])
    if prediction is None or reject_dE is None:
        return Verdict(UNKNOWN, ["no calibration model loaded (not confident)"])
    est = prediction.get("est")
    dist = prediction.get("distance")
    if est is None or dist is None or not math.isfinite(est) or not math.isfinite(dist):
        return Verdict(UNKNOWN, ["classifier returned no estimate"])
    if dist > reject_dE:
        return Verdict(UNKNOWN, [f"colour not on calibration curve (dE00 {dist:.1f} > {reject_dE:.1f})"],
                       est, block, False, dist)
    if est >= hold_block:
        return Verdict(HOLD, [f"estimated {est:.0f} mg/L NO3- >= {hold_block:.0f} mg/L hold block"],
                       est, block, False, dist)
    if band_low is not None and est >= band_low:
        return Verdict(HOLD, [f"borderline: estimated {est:.0f} mg/L is within the band "
                              f"{band_low:.1f}-{hold_block:.0f} mg/L below the hold block (conservative)"],
                       est, block, True, dist)
    return Verdict(PASS, [f"estimated {est:.0f} mg/L NO3- < {hold_block:.0f} mg/L hold block"],
                   est, block, False, dist)
