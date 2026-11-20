r"""Suggest initial quality-gate thresholds from DRY captures (and optionally training reads).

  .venv\\Scripts\\python tools\\suggest_thresholds.py                 print suggestions
  .venv\\Scripts\\python tools\\suggest_thresholds.py --apply         also write them into config.yaml
  .venv\\Scripts\\python tools\\suggest_thresholds.py --sessions X Y  use only these sessions

Use dry sessions with notes containing 'empty' (empty tray), 'dry' (dry strip), 'distilled',
'tap'. The rules are fixed here (margins over what good captures showed) and written to
results\\threshold_suggestions.md. FREEZE the result before scored tests: freezing the model
copies the thresholds; test mode refuses if config.yaml differs later.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import CONFIG_PATH, load_config  # noqa: E402
from app.model import load_frozen  # noqa: E402
from app.session import SESSIONS_DIR, iter_samples, list_sessions  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--with-train", action="store_true", help="also use training reads (drift, glare)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    q = cfg["quality"]
    if a.sessions:
        sessions = [SESSIONS_DIR / s for s in a.sessions]
    else:
        sessions = list_sessions("dry") + (list_sessions("train") if a.with_train else [])
    good, empty = [], []
    for s in sessions:
        for d, m in iter_samples(s):
            mt = m.get("metrics")
            if not mt or "white_L_mean" not in mt:
                continue
            if str(m.get("sample_id", "")).startswith("HIL_"):
                continue          # deliberate faults from hil_check.py are not "good" captures
            note = str(m.get("note", "")).lower()
            (empty if "empty" in note else good).append((f"{s.name}/{d.name}", note, mt))
    if not good:
        print("No usable dry reads with metrics. Do dry runs first (RUNBOOK step 'Dry runs').")
        return 1
    arr = {k: np.array([g[2][k] for g in good if g[2].get(k) is not None], dtype=float)
           for k in ("black_L_max", "black_jump_max", "white_L_mean", "white_clip_max", "glare_max",
                     "sharpness_min", "drift_dE", "grey_chroma_max", "strip_dE", "strip_absdiff", "latency_max_s")}
    sug = {}
    why = {}
    sug["black_L_max"] = round(float(arr["black_L_max"].max()) + 6.0, 1)
    why["black_L_max"] = f"max black L* in good reads {arr['black_L_max'].max():.1f} + 6"
    sug["black_jump_max"] = round(max(2.0, 3.0 * float(arr["black_jump_max"].max())), 1)
    why["black_jump_max"] = f"3 x max frame-to-frame jump {arr['black_jump_max'].max():.2f} (min 2.0)"
    sug["white_L_min"] = round(float(arr["white_L_mean"].min()) - 8.0, 1)
    sug["white_L_max"] = round(min(99.0, float(arr["white_L_mean"].max()) + 4.0), 1)
    why["white_L_min"] = why["white_L_max"] = f"white L* seen {arr['white_L_mean'].min():.1f}..{arr['white_L_mean'].max():.1f}, -8/+4"
    sug["blur_min"] = round(0.5 * float(arr["sharpness_min"].min()), 1)
    why["blur_min"] = f"half the lowest sharpness in good reads ({arr['sharpness_min'].min():.1f})"
    sug["grey_chroma_max"] = round(max(4.0, 2.0 * float(arr["grey_chroma_max"].max())), 1)
    why["grey_chroma_max"] = f"2 x max grey chroma {arr['grey_chroma_max'].max():.2f} (min 4)"
    if len(arr["drift_dE"]):
        sug["drift_max_dE"] = round(max(q["drift_max_dE"], 2.0 * float(arr["drift_dE"].max())), 2)
        why["drift_max_dE"] = (f"max(current {q['drift_max_dE']}, 2 x max drift {arr['drift_dE'].max():.2f}); "
                               "dry strips do not develop, so re-check with --with-train before freezing")
    strip_good = [g[2] for g in good if g[2].get("strip_dE") is not None]
    strip_empty = [e[2] for e in empty if e[2].get("strip_dE") is not None]
    if strip_good and strip_empty:
        lo = min(x["strip_dE"] for x in strip_good)
        hi = max(x["strip_dE"] for x in strip_empty)
        lo2 = min(x["strip_absdiff"] for x in strip_good)
        hi2 = max(x["strip_absdiff"] for x in strip_empty)
        if lo > hi:
            sug["strip_min_dE"] = round((lo + hi) / 2, 1)
            why["strip_min_dE"] = f"midpoint: strips >= {lo:.1f}, empty tray <= {hi:.1f}"
        else:
            why["strip_min_dE"] = f"NOT separable by colour (strips min {lo:.1f} <= empty max {hi:.1f}); kept"
        if lo2 > hi2:
            sug["strip_min_absdiff"] = round((lo2 + hi2) / 2, 1)
            why["strip_min_absdiff"] = f"midpoint: strips >= {lo2:.1f}, empty tray <= {hi2:.1f}"
    else:
        why["strip_min_dE"] = "needs both empty-tray and strip dry reads; kept"

    lines = [f"# Quality threshold suggestions ({time.strftime('%Y-%m-%d %H:%M:%S')})", "",
             f"From {len(good)} good reads and {len(empty)} empty-tray reads in: "
             f"{', '.join(sorted({g[0].split('/')[0] for g in good + empty}))}", "",
             "| threshold | current | suggested | basis |", "|---|---|---|---|"]
    for k in q:
        if k in sug or k in why:
            lines.append(f"| {k} | {q[k]} | {sug.get(k, q[k])} | {why.get(k, '')} |")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "threshold_suggestions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if a.apply:
        if load_frozen() is not None:
            print("\nREFUSED to apply: a frozen model exists (thresholds are frozen).")
            return 2
        text = CONFIG_PATH.read_text(encoding="utf-8")
        for k, v in sug.items():
            text, n = re.subn(rf"^(\s+{k}:\s*)([-0-9.]+)", rf"\g<1>{v}", text, flags=re.M)
            if n != 1:
                print(f"could not update {k} in config.yaml")
        CONFIG_PATH.write_text(text, encoding="utf-8")
        print("\nApplied to config.yaml (restart the app).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
