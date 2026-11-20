r"""Freeze models\model_latest.json: copy to models\frozen\model_<stamp>.json, read-only,
record its SHA-256 in models\frozen\CURRENT.txt. Evaluation and test/degraded/demo
sessions load only the frozen model and check its hash.

Freezing also freezes: the quality thresholds in config.yaml, the ROI and the camera
settings (their hashes are inside the model). Change any of them and test mode refuses.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.model import FROZEN_DIR, freeze, load_frozen  # noqa: E402


def main():
    src = ROOT / "models" / "model_latest.json"
    if not src.exists():
        print("No models\model_latest.json. Run train.py first.")
        return 2
    d = json.loads(src.read_text())
    if d.get("synthetic"):
        print("REFUSED: this model was trained on synthetic test data.")
        return 2
    cur = load_frozen()
    if cur is not None:
        print(f"Note: replacing the current frozen model {cur.path.name} (it stays on disk, read-only).")
    dst = freeze(src)
    lm = load_frozen()
    line = (f"- {time.strftime('%Y-%m-%d %H:%M:%S')}: froze {dst.name} sha256 {lm.sha} "
            f"(primary {lm.primary}, reject dE00 {lm.thr['reject_dE']:.2f}, band from {lm.thr['band_low_mg_L']:.1f} mg/L, "
            f"{len(lm.d['training_samples'])} training reads)\n")
    log = ROOT / "results" / "freeze_log.md"
    log.parent.mkdir(exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())
    print(f"Frozen to {FROZEN_DIR / dst.name} (read-only). Restart the app to load it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
