r"""Train the nitrate calibration model from train sessions.

  .venv\\Scripts\\python train.py                    all purpose=train sessions
  .venv\\Scripts\\python train.py --sessions A B     only these session folders
  .venv\\Scripts\\python train.py --include-dry-blanks   also use dry-session reads whose note
                                                    is 'distilled' as 0 mg/L blanks (only if confirmed)

Refuses to run unless tools\\lock_camera.py --check passes now AND every training
session was recorded with the same frozen camera settings and the same ROI as now.
Writes models\\model_latest.json (+ .sha256), models\\model_card.md, results\\train_*.
Then run freeze_model.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.camlock import check_camera, settings_hash  # noqa: E402
from app.chart import load_chart  # noqa: E402
from app.config import load_config, phone_base, quality_thresholds, rpath  # noqa: E402
from app.model import save_model, train_all  # noqa: E402
from app.roi import load_roi, roi_hash  # noqa: E402
from app.session import SESSIONS_DIR, iter_samples, list_sessions, load_session  # noqa: E402
from app.station import roi_locate_params  # noqa: E402


class TrainError(RuntimeError):
    pass


def read_labels(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = (row.get("sample_id") or "").strip()
            if sid and not sid.startswith("#"):
                out[sid] = row
    return out


def collect(session_dirs, cam_hash, cur_roi_hash, labels, include_dry_blanks=False):
    samples, excluded, warnings = [], [], []
    for sd in session_dirs:
        meta = load_session(sd)
        purpose = meta.get("purpose")
        if purpose not in ("train", "dry"):
            raise TrainError(f"{sd.name}: purpose {purpose} is not train (test data is never used for training)")
        if purpose == "dry" and not include_dry_blanks:
            continue
        if meta.get("camera_settings_hash") != cam_hash:
            raise TrainError(f"{sd.name}: recorded with camera settings {meta.get('camera_settings_hash')}, "
                             f"current frozen settings are {cam_hash}")
        if meta.get("roi_hash") != cur_roi_hash:
            raise TrainError(f"{sd.name}: recorded with ROI {meta.get('roi_hash')}, current ROI is {cur_roi_hash}")
        for d, m in iter_samples(sd):
            sid = m["sample_id"]
            if purpose == "dry":
                if "distilled" not in str(m.get("note", "")).lower():
                    continue
                conc = 0.0
            else:
                conc = m.get("concentration_mg_L")
                if sid in labels:
                    lc = float(labels[sid]["concentration_mg_L"])
                    if conc is not None and abs(lc - float(conc)) > 1e-6:
                        raise TrainError(f"{sd.name}/{d.name}: app says {conc} mg/L, train_labels.csv says {lc}")
                    conc = lc
                elif labels:
                    warnings.append(f"{sd.name}/{d.name}: {sid} not in train_labels.csv (using the app entry {conc})")
            if conc is None:
                excluded.append((f"{sd.name}/{d.name}", "no concentration"))
                continue
            if not m.get("quality_ok"):
                excluded.append((f"{sd.name}/{d.name}", "quality gate failed: " + "; ".join(m["verdict"]["reasons"][:2])))
                continue
            f = m["features"]
            samples.append({"sample_id": f"{sd.name}/{d.name}", "conc": float(conc),
                            "lab": [f["pad_L"], f["pad_a"], f["pad_b"]], "session": sd.name})
    return samples, excluded, warnings


def build_model(samples, cfg, chart, extra):
    if len({s["conc"] for s in samples}) < 2:
        raise TrainError(f"need reads of at least 2 different standards (have {len(samples)} usable reads)")
    d = train_all(samples, cfg, chart["blocks_no3"])
    d.update(extra)
    d["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    d["training_samples"] = samples
    d["quality_thresholds"] = quality_thresholds(cfg)
    d["roi_locate"] = roi_locate_params(cfg)        # D-43: the 'seated' tolerance is frozen too
    d["read_time_s"] = cfg["read_time_s"]
    d["correction_mode"] = cfg.get("correction_mode", "three_point")
    d["read_offsets_s"] = cfg["read_offsets_s"]
    d["chart_blocks_no3"] = chart["blocks_no3"]
    thr = d["methods"][d["primary"]]["thresholds"]
    w = []
    if thr["band_low_mg_L"] <= 10:
        w.append(f"borderline band reaches {thr['band_low_mg_L']:.1f} mg/L (<= the 10 block): expect false holds on 10 mg/L water")
    d["warnings"] = w
    return d


def write_reports(d, out_models: Path, out_results: Path, excluded, warnings):
    out_models.mkdir(parents=True, exist_ok=True)
    out_results.mkdir(parents=True, exist_ok=True)
    p = d["primary"]
    lines = ["# Model card (auto-generated by train.py)", "",
             f"- Created: {d['created']}",
             f"- Primary method: **{p}** (chosen by: {d['selection_rule']})",
             f"- Training reads: {len(d['training_samples'])} from sessions {sorted({s['session'] for s in d['training_samples']})}",
             f"- ROI hash: {d.get('roi_hash')} | camera settings hash: {d.get('camera_settings_hash')}",
             f"- Read time: {d['read_time_s']} s, read offsets {d['read_offsets_s']}",
             f"- Hold block: {d['hold_block_mg_L']} mg/L NO3- (decision rule 3)", "",
             "| method | reject dE00 | borderline band (mg/L) | LOSO n | missed (true>=25 read PASS) | false holds | unknown | within 1 block | mean abs log err |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, r in d["methods"].items():
        t, s = r["thresholds"], r["summary"]
        lines.append(f"| {name}{' (primary)' if name == p else ''} | {t['reject_dE']:.2f} "
                     f"(p{d.get('reject_percentile', '')}={t['reject_percentile_value']:.2f}) | "
                     f"{t['band_low_mg_L']:.1f} to {d['hold_block_mg_L']:.0f} (band {t['band_log']:.3f} log, n={t['band_basis_n']}) | "
                     f"{s['n']} | {s['missed_ge_hold']} | {s['false_holds']} | {s['unknown']} | "
                     f"{s['within_one_block']}/{s['n']} | {s['mean_abs_log_err']:.3f} |")
    lines += ["", "Rejection: UNKNOWN if the capture's dE00 to the nearest point of the model exceeds "
              "max(floor, percentile of leave-one-strip-out distances x factor).",
              "Borderline band: HOLD (not PASS) when the estimate is within band_k x RMS(LOSO log error) "
              "below the hold block, RMS taken over standards within 0.4x-2.5x of the hold block.",
              "LOSO thresholds are computed from the full training set and then applied to the LOSO rows "
              "(slightly optimistic; stated here).", ""]
    lines += ["## Per-standard mean pad colour (corrected CIELAB)", "", "| mg/L | n | L* | a* | b* |", "|---|---|---|---|---|"]
    m = d["methods"]["curve"]["model"]
    for c, node in zip(m["concs"], m["nodes_lab"]):
        lines.append(f"| {c:g} | {m['counts'].get(str(c), '')} | {node[0]:.2f} | {node[1]:.2f} | {node[2]:.2f} |")
    if d.get("warnings"):
        lines += ["", "## Warnings", ""] + [f"- {x}" for x in d["warnings"]]
    if excluded:
        lines += ["", "## Reads excluded from training", ""] + [f"- {a}: {b}" for a, b in excluded]
    if warnings:
        lines += ["", "## Label warnings", ""] + [f"- {x}" for x in warnings]
    (out_models / "model_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out_results / "train_loso.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["method", "sample_id", "true_mg_L", "est_mg_L", "distance_dE00", "log_err", "decision", "block"])
        for name, r in d["methods"].items():
            for row in r["rows"]:
                w.writerow([name, row["sample_id"], row["true"], f"{row['est']:.2f}", f"{row['distance']:.3f}",
                            f"{row['log_err']:.4f}", row.get("decision"), row.get("block")])
    try:
        plot_curve(d, out_results / "fig_training_curve.png")
    except Exception as e:  # plotting must never block training
        print("plot failed:", e)


def plot_curve(d, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    s = d["training_samples"]
    m = d["methods"]["curve"]["model"]
    c = np.array([x["conc"] for x in s])
    lab = np.array([x["lab"] for x in s])
    fig, ax = plt.subplots(1, 3, figsize=(13, 4))
    for i, name in enumerate(["L*", "a*", "b*"]):
        ax[i].scatter(c + 1, lab[:, i], s=22, label="training strips")
        ax[i].plot(np.array(m["concs"]) + 1, np.array(m["nodes_lab"])[:, i], "-o", color="k", ms=4, label="curve nodes")
        ax[i].set_xscale("log")
        ax[i].set_xlabel("standard (mg/L NO3-) + 1")
        ax[i].set_ylabel(name)
        ax[i].grid(alpha=.3)
    ax[0].legend()
    fig.suptitle(f"Nitrate pad colour vs standard (model {d['created']})")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="*", help="session folder names (default: all train sessions)")
    ap.add_argument("--include-dry-blanks", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    chart = load_chart(rpath(cfg["chart_file"]))

    from app.phone import PhoneCam
    ok, problems, frozen = check_camera(PhoneCam(phone_base(cfg), 5.0), cfg, rpath(cfg["camera_settings_file"]))
    if not ok:
        print("REFUSED: camera lock check failed (tools\\lock_camera.py --check):")
        for p in problems:
            print("  -", p)
        return 2
    cam_hash = settings_hash(frozen)
    roi = load_roi(rpath(cfg["roi_file"]))
    if roi is None:
        print("REFUSED: no ROI (data\\calib\\roi.json)")
        return 2
    rh = roi_hash(roi)

    if args.sessions:
        dirs = [SESSIONS_DIR / s for s in args.sessions]
    else:
        dirs = list_sessions("train") + (list_sessions("dry") if args.include_dry_blanks else [])
    if not dirs:
        print("REFUSED: no train sessions found in data\\sessions")
        return 2
    labels = read_labels(ROOT / "data" / "labels" / "train_labels.csv")
    try:
        samples, excluded, warnings = collect(dirs, cam_hash, rh, labels, args.include_dry_blanks)
        d = build_model(samples, cfg, chart, {"roi_hash": rh, "camera_settings_hash": cam_hash,
                                              "reject_percentile": cfg["model"]["reject_percentile"],
                                              "sessions": [x.name for x in dirs],
                                              "labels_file_used": bool(labels)})
    except TrainError as e:
        print("REFUSED:", e)
        return 2
    stamp = time.strftime("%Y%m%d_%H%M%S")
    sha = save_model(d, ROOT / "models" / "model_latest.json")
    save_model(d, ROOT / "models" / f"model_{stamp}.json")
    write_reports(d, ROOT / "models", ROOT / "results", excluded, warnings)
    p = d["methods"][d["primary"]]
    print(f"Trained on {len(samples)} reads ({len(excluded)} excluded). Primary: {d['primary']}")
    print(f"  reject dE00 > {p['thresholds']['reject_dE']:.2f} -> UNKNOWN; borderline HOLD from "
          f"{p['thresholds']['band_low_mg_L']:.1f} mg/L; LOSO summary {p['summary']}")
    for w in d["warnings"] + warnings:
        print("  WARNING:", w)
    print(f"Saved models\\model_latest.json (sha256 {sha[:16]}...). Next: .venv\\Scripts\\python freeze_model.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
