"""Nitrate calibration models, unknown rejection, leave-one-strip-out CV, save/freeze/load.

Primary candidate: CurveModel. Per-standard mean Lab points, ordered by concentration,
joined into a polyline in Lab (monotonic in concentration by construction). A capture is
projected onto the nearest segment; concentration is interpolated in log(c + offset)
between the segment's two standards. Distance from the curve (dE00) drives rejection.

Reference method: CentroidModel. Nearest standard centroid by dE00 (log-interpolated
with the adjacent runner-up), same rejection rule.

The primary is chosen by leave-one-strip-out CV on training data only.
"""
from __future__ import annotations

import json
import math
import os
import stat
import time
from pathlib import Path

import numpy as np

from .colour import delta_e2000
from .config import ROOT, file_hash


def _lc(c, off):
    return math.log(max(float(c), 0.0) + off)


def _unlc(v, off):
    return max(0.0, math.exp(v) - off)


def group_means(samples):
    by = {}
    for s in samples:
        by.setdefault(float(s["conc"]), []).append(np.asarray(s["lab"], dtype=np.float64))
    concs = sorted(by)
    return concs, [np.mean(by[c], axis=0) for c in concs], {c: len(by[c]) for c in concs}


class CurveModel:
    name = "curve"

    def __init__(self, off=1.0):
        self.off = off
        self.concs: list[float] = []
        self.nodes: list[np.ndarray] = []

    def fit(self, samples):
        self.concs, self.nodes, self.counts = group_means(samples)
        if len(self.concs) < 2:
            raise ValueError("need at least 2 distinct standards")
        return self

    def predict(self, lab):
        lab = np.asarray(lab, dtype=np.float64)
        best = None
        for i in range(len(self.nodes) - 1):
            a, b = self.nodes[i], self.nodes[i + 1]
            ab = b - a
            den = float(ab @ ab)
            t = 0.0 if den < 1e-12 else float(np.clip((lab - a) @ ab / den, 0.0, 1.0))
            p = a + t * ab
            d = float(delta_e2000(lab, p))
            if best is None or d < best[0]:
                best = (d, i, t, p)
        d, i, t, p = best
        lc = _lc(self.concs[i], self.off) + t * (_lc(self.concs[i + 1], self.off) - _lc(self.concs[i], self.off))
        return {"est": _unlc(lc, self.off), "distance": d, "segment": [self.concs[i], self.concs[i + 1]],
                "t": t, "nearest_point_lab": p.round(3).tolist()}

    def to_dict(self):
        return {"method": "curve", "conc_offset": self.off, "concs": self.concs,
                "nodes_lab": [n.round(4).tolist() for n in self.nodes],
                "counts": {str(k): v for k, v in self.counts.items()}}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["conc_offset"])
        m.concs = [float(c) for c in d["concs"]]
        m.nodes = [np.asarray(n) for n in d["nodes_lab"]]
        m.counts = d.get("counts", {})
        return m


class CentroidModel(CurveModel):
    name = "centroid"

    def predict(self, lab):
        lab = np.asarray(lab, dtype=np.float64)
        d = np.array([float(delta_e2000(lab, n)) for n in self.nodes])
        order = np.argsort(d)
        i = int(order[0])
        est = self.concs[i]
        if len(order) > 1:
            j = int(order[1])
            if abs(i - j) == 1:     # interpolate with an adjacent runner-up only
                w = d[j] / max(d[i] + d[j], 1e-9)
                lc = w * _lc(self.concs[i], self.off) + (1 - w) * _lc(self.concs[j], self.off)
                est = _unlc(lc, self.off)
        return {"est": est, "distance": float(d[i]), "nearest_standard": self.concs[i]}

    def to_dict(self):
        d = super().to_dict()
        d["method"] = "centroid"
        return d


METHODS = {"curve": CurveModel, "centroid": CentroidModel}


# ---------------------------------------------------------------- training / CV

def loso(method_cls, samples, off):
    """Leave-one-strip-out: refit without each strip and predict it."""
    out = []
    for k, s in enumerate(samples):
        rest = samples[:k] + samples[k + 1:]
        if len({r["conc"] for r in rest}) < 2:
            continue
        m = method_cls(off).fit(rest)
        p = m.predict(s["lab"])
        out.append({"sample_id": s["sample_id"], "true": s["conc"], "est": p["est"],
                    "distance": p["distance"],
                    "log_err": _lc(p["est"], off) - _lc(s["conc"], off)})
    return out


def thresholds_from_loso(rows, mcfg, hold_block, off):
    dists = np.array([r["distance"] for r in rows])
    p = float(np.percentile(dists, mcfg["reject_percentile"])) if len(dists) else 0.0
    reject = max(float(mcfg["reject_floor_dE"]), p * float(mcfg["reject_factor"]))
    near = [r for r in rows if 0.4 * hold_block <= r["true"] <= 2.5 * hold_block]
    use = near if len(near) >= 3 else rows
    errs = np.array([r["log_err"] for r in use])
    rmse = float(np.sqrt(np.mean(errs ** 2))) if len(errs) else 0.0
    band_log = float(mcfg["band_k"]) * rmse
    band_low = _unlc(_lc(hold_block, off) - band_log, off)
    return {"reject_dE": reject, "reject_percentile_value": p, "band_log": band_log,
            "band_low_mg_L": band_low, "band_basis_n": len(use),
            "band_basis": "standards within 0.4x..2.5x of the hold block" if use is near else "all standards",
            "loso_log_rmse": rmse}


def evaluate_loso(rows, thr, hold_block, blocks, off):
    from .chart import acceptable_blocks, nearest_block
    missed = false_hold = unknown = within = 0
    for r in rows:
        if r["distance"] > thr["reject_dE"]:
            dec = "UNKNOWN"
        elif r["est"] >= hold_block or r["est"] >= thr["band_low_mg_L"]:
            dec = "HOLD"
        else:
            dec = "PASS"
        r["decision"] = dec
        r["block"] = nearest_block(r["est"], blocks, off)
        unknown += dec == "UNKNOWN"
        if r["true"] >= hold_block and dec == "PASS":
            missed += 1
        if r["true"] < hold_block and dec == "HOLD":
            false_hold += 1
        within += r["block"] in acceptable_blocks(r["true"], blocks)
    n = len(rows)
    mae = float(np.mean([abs(r["log_err"]) for r in rows])) if rows else float("nan")
    return {"n": n, "missed_ge_hold": missed, "false_holds": false_hold, "unknown": unknown,
            "within_one_block": within, "mean_abs_log_err": mae}


def train_all(samples, cfg, blocks):
    """Fit both methods, run LOSO, choose the primary. Returns a model dict (unsaved)."""
    mcfg = cfg["model"]
    off = float(mcfg["conc_offset_mg_L"])
    hold = float(cfg["hold_block_mg_L"])
    report = {}
    for name, cls in METHODS.items():
        rows = loso(cls, samples, off)
        thr = thresholds_from_loso(rows, mcfg, hold, off)
        summ = evaluate_loso(rows, thr, hold, blocks, off)
        report[name] = {"thresholds": thr, "summary": summ, "rows": rows,
                        "model": cls(off).fit(samples).to_dict()}
    primary = min(report, key=lambda k: (report[k]["summary"]["missed_ge_hold"],
                                         report[k]["summary"]["false_holds"] + report[k]["summary"]["unknown"],
                                         report[k]["summary"]["mean_abs_log_err"]))
    return {"primary": primary, "selection_rule": "LOSO lexicographic: fewest missed (true>=hold read PASS), "
            "then fewest false holds + unknowns, then lowest mean |log error|",
            "methods": report, "hold_block_mg_L": hold, "conc_offset": off}


# ---------------------------------------------------------------- loaded model

class LoadedModel:
    def __init__(self, d: dict, path: Path | None = None, sha: str | None = None):
        self.d = d
        self.path = path
        self.sha = sha
        self.primary = d["primary"]
        p = d["methods"][self.primary]
        self.model = METHODS[self.primary].from_dict(p["model"])
        self.thr = p["thresholds"]
        ref = "centroid" if self.primary == "curve" else "curve"
        self.ref_name = ref
        self.ref_model = METHODS[ref].from_dict(d["methods"][ref]["model"])
        self.ref_thr = d["methods"][ref]["thresholds"]
        self.hold_block = float(d["hold_block_mg_L"])
        self.frozen = bool(d.get("frozen_at"))

    def predict(self, lab):
        p = self.model.predict(lab)
        r = self.ref_model.predict(lab)
        p["reference"] = {"method": self.ref_name, "est": r["est"], "distance": r["distance"],
                          "rejected": r["distance"] > self.ref_thr["reject_dE"]}
        return p


def save_model(d: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=1, default=float))
    sha = file_hash(path)
    path.with_suffix(".sha256").write_text(f"{sha}  {path.name}\n")
    return sha


FROZEN_DIR = ROOT / "models" / "frozen"


def freeze(src: Path, frozen_dir: Path = FROZEN_DIR) -> Path:
    pointer = frozen_dir / "CURRENT.txt"
    d = json.loads(src.read_text())
    stamp = time.strftime("%Y%m%d_%H%M%S")
    d["frozen_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    d["frozen_from"] = src.name
    frozen_dir.mkdir(parents=True, exist_ok=True)
    dst = frozen_dir / f"model_{stamp}.json"
    sha = save_model(d, dst)
    for p in (dst, dst.with_suffix(".sha256")):
        os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    if pointer.exists():
        os.chmod(pointer, stat.S_IWRITE | stat.S_IREAD)
    pointer.write_text(f"{dst.name} {sha}\n")
    return dst


def load_frozen(frozen_dir: Path = FROZEN_DIR) -> LoadedModel | None:
    """Load the current frozen model and verify its hash. None if none frozen."""
    pointer = frozen_dir / "CURRENT.txt"
    if not pointer.exists():
        return None
    name, sha = pointer.read_text().split()
    path = frozen_dir / name
    actual = file_hash(path)
    if actual != sha:
        raise RuntimeError(f"frozen model {name} hash mismatch: file was modified")
    return LoadedModel(json.loads(path.read_text()), path, sha)


def load_any(path: Path) -> LoadedModel:
    return LoadedModel(json.loads(path.read_text()), path, file_hash(path))

