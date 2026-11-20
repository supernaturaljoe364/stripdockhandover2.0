r"""Evaluate the scored tests against the abstract's targets.

  .venv\\Scripts\\python evaluate.py                       all closed test + degraded sessions
  .venv\\Scripts\\python evaluate.py --sessions A B         only these
  .venv\\Scripts\\python evaluate.py --tag v2_bugfix        write results with a label (never
                                                          overwrite: report both versions)

Rules: loads ONLY the frozen model (hash-checked). Sessions must be closed with an intact
MANIFEST. Reads data\\labels\\test_answer_key.csv (the app never does). The verdict that
was actually sent to the panel at read time is what is scored; a recomputation from the
stored features with the frozen model is reported as a consistency check only.
Thresholds are never changed here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.chart import acceptable_blocks, load_chart, nearest_block  # noqa: E402
from app.config import load_config, rpath  # noqa: E402
from app.decision import decide  # noqa: E402
from app.model import load_frozen  # noqa: E402
from app.session import SESSIONS_DIR, iter_samples, list_sessions, load_session, verify_session  # noqa: E402

BASELINE_TDS_HOLD_PPM = 300.0   # Round-2 TDS-only logic: RO+UV only when TDS >= 300 ppm (DECISIONS.md)
TYPES = ("spiked_tap", "compliant", "unseen_standard", "conservative")


# ---------------------------------------------------------------- statistics

def _binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    if n == 0:
        return (float("nan"), float("nan"))

    def solve(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - (1 - _binom_cdf(k - 1, n, p)), 1 - alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p), alpha / 2)
    return lower, upper


def frac(k, n):
    if n == 0:
        return "0/0"
    lo, hi = clopper_pearson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%, 95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"


# ---------------------------------------------------------------- loading

def read_key(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"No answer key at {path}. The chemistry person writes it (see data\\labels\\README.md).")
    key = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = (row.get("sample_id") or "").strip()
            if not sid:
                continue
            t = row["type"].strip()
            if t not in TYPES:
                raise SystemExit(f"answer key: {sid} has unknown type {t!r}")
            key[sid] = {"true": float(row["true_concentration_mg_L"]), "type": t,
                        "tds": float(row["tds_ppm"]) if row.get("tds_ppm") else None}
    return key


def read_baselines(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("sample_id"):
                out[row["sample_id"].strip()] = row
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    cfg = load_config()
    chart = load_chart(rpath(cfg["chart_file"]))
    blocks = chart["blocks_no3"]
    off = float(cfg["model"]["conc_offset_mg_L"])
    hold = float(cfg["hold_block_mg_L"])
    model = load_frozen()
    if model is None:
        raise SystemExit("No frozen model. Evaluation only uses frozen models (freeze_model.py).")
    suffix = f"_{a.tag}" if a.tag else ""
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    md_path = out / f"round3_results{suffix}.md"
    if a.tag == "" and md_path.exists():
        prev = md_path.with_name(f"round3_results_prev_{time.strftime('%Y%m%d_%H%M%S')}.md")
        md_path.rename(prev)

    if a.sessions:
        sessions = [SESSIONS_DIR / s for s in a.sessions]
    else:
        sessions = list_sessions("test") + list_sessions("degraded")
    if not sessions:
        raise SystemExit("No test/degraded sessions found.")
    problems = []
    for s in sessions:
        meta = load_session(s)
        if not meta.get("closed"):
            problems.append(f"{s.name}: not closed (run close_session.py first)")
        else:
            problems += [f"{s.name}: {p}" for p in verify_session(s)]
    if problems:
        raise SystemExit("REFUSED, sessions not closed/intact:\n  " + "\n  ".join(problems))

    key = read_key(ROOT / "data" / "labels" / "test_answer_key.csv")
    base = read_baselines(ROOT / "data" / "labels" / "baseline_readings.csv")

    test_rows, deg_rows, times, notes = [], [], [], []
    for s in sessions:
        purpose = load_session(s)["purpose"]
        for d, m in iter_samples(s):
            v = m["verdict"]
            msha = (m.get("model") or {}).get("sha256")
            if msha != model.sha:
                notes.append(f"{s.name}/{d.name}: read with model {msha}, frozen model is {model.sha}")
            if m.get("start_to_verdict_s") is not None:
                times.append(m["start_to_verdict_s"])
            # consistency: recompute from the stored features with the frozen model
            recomputed = None
            if m.get("features"):
                f = m["features"]
                p = model.predict([f["pad_L"], f["pad_a"], f["pad_b"]])
                blk = nearest_block(p["est"], blocks, off)
                rv = decide(m["quality_ok"], [c["reason"] for c in m["checks"] if not c["passed"]], p,
                            model.thr["reject_dE"], hold, model.thr["band_low_mg_L"], blk)
                recomputed = rv.command
            else:
                recomputed = "UNKNOWN"
            row = {"session": s.name, "folder": d.name, "sample_id": m["sample_id"], "verdict": v["command"],
                   "est_mg_L": v.get("est_mg_L"), "block_mg_L": v.get("block_mg_L"),
                   "borderline": v.get("borderline"), "reasons": " | ".join(v["reasons"]),
                   "recomputed": recomputed, "panel_reply": (m.get("panel") or {}).get("reply_state"),
                   "start_to_verdict_s": m.get("start_to_verdict_s"),
                   "reference_est_mg_L": ((m.get("prediction") or {}).get("reference") or {}).get("est"),
                   "reference_rejected": ((m.get("prediction") or {}).get("reference") or {}).get("rejected")}
            if recomputed != v["command"]:
                notes.append(f"{s.name}/{d.name}: recorded {v['command']} but recomputation gives {recomputed}")
            if purpose == "degraded":
                row["degradation"] = m.get("degradation")
                deg_rows.append(row)
            else:
                k = key.get(m["sample_id"])
                if k is None:
                    notes.append(f"{s.name}/{d.name}: sample {m['sample_id']} not in the answer key (excluded)")
                    continue
                row.update({"true_mg_L": k["true"], "type": k["type"], "tds_ppm": k["tds"]})
                test_rows.append(row)

    # ---------------------------------------------------------------- tables
    L = [f"# StripDock Round 3 results{(' (' + a.tag + ')') if a.tag else ''}", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')} by `evaluate.py` from real captures.",
         f"Frozen model: `{model.path.name}` sha256 `{model.sha}` (primary method: {model.primary}; "
         f"UNKNOWN if dE00 > {model.thr['reject_dE']:.2f}; borderline HOLD from {model.thr['band_low_mg_L']:.1f} mg/L; "
         f"HOLD at >= {hold:.0f} mg/L NO3-).",
         f"Sessions: {', '.join(s.name for s in sessions)} (all closed, manifests intact).",
         "Answer key: `data/labels/test_answer_key.csv`. Every proportion has a 95% Clopper-Pearson interval.",
         "The verdict scored is the one sent to the panel at read time.", ""]

    def met(ok, n, planned):
        """Target judged on the observed proportion; reduced n is flagged (strip shortage, D-38)."""
        if not n:
            return "no data"
        return ("yes" if ok else "no") + (f" (n={n} < planned {planned}; see CI)" if n < planned else "")

    def by(t):
        return [r for r in test_rows if r["type"] == t]

    sp = by("spiked_tap")
    n_unk = sum(r["verdict"] == "UNKNOWN" for r in sp)
    missed = sum(r["verdict"] == "PASS" for r in sp)
    tds_known = [r for r in sp if r["tds_ppm"] is not None]
    tds_missed = sum(r["tds_ppm"] < BASELINE_TDS_HOLD_PPM for r in tds_known)
    L += ["## Targets", "", "| Test | Result | Target | Met? |", "|---|---|---|---|"]
    L.append(f"| Missed nitrate (spiked tap, 60-100 mg/L) | not held: {frac(missed, len(sp))}; held: "
             f"{sum(r['verdict'] == 'HOLD' for r in sp)}; UNKNOWN: {n_unk} | <= 5% not held (planned 1/20) | "
             f"{met(len(sp) and missed / len(sp) <= 0.05, len(sp), 20)} |")
    co = by("compliant")
    fh = sum(r["verdict"] == "HOLD" for r in co)
    L.append(f"| False holds (compliant 0-10 mg/L) | held: {frac(fh, len(co))}; UNKNOWN: "
             f"{sum(r['verdict'] == 'UNKNOWN' for r in co)} | <= 10% held (planned 2/20) | "
             f"{met(len(co) and fh / len(co) <= 0.10, len(co), 20)} |")
    us = by("unseen_standard")
    for r in us:
        r["acceptable"] = acceptable_blocks(r["true_mg_L"], blocks)
        r["within"] = r["block_mg_L"] is not None and r["verdict"] != "UNKNOWN" and r["block_mg_L"] in r["acceptable"]
    wi = sum(r["within"] for r in us)
    L.append(f"| Block accuracy (unseen standards) | within one block: {frac(wi, len(us))}; UNKNOWN (no block, "
             f"counted as not within): {sum(r['verdict'] == 'UNKNOWN' for r in us)} | >= 96.7% (planned 29/30) | "
             f"{met(len(us) and wi / len(us) >= 29 / 30, len(us), 30)} |")
    cz = by("conservative")
    L.append(f"| Conservative zone (25-44 mg/L) | held: {frac(sum(r['verdict'] == 'HOLD' for r in cz), len(cz))}; "
             f"UNKNOWN: {sum(r['verdict'] == 'UNKNOWN' for r in cz)} | report | - |")
    du = sum(r["verdict"] == "UNKNOWN" for r in deg_rows)
    L.append(f"| Degraded images | UNKNOWN: {frac(du, len(deg_rows))} | >= 95% UNKNOWN (planned 30) | "
             f"{met(deg_rows and du / len(deg_rows) >= 0.95, len(deg_rows), 30)} |")
    if times:
        st = sorted(times)
        med = st[len(st) // 2]
        L.append(f"| Dip to verdict (START press to verdict) | median {med:.0f} s, max {max(st):.0f} s over "
                 f"{len(st)} reads | <= 3 min | {'yes' if max(st) <= 180 else 'no'} |")
    L += ["", "Notes on the claims:",
          "- An UNKNOWN on a spiked sample is counted as not missed for the safety claim (the hold is never "
          "cleared by UNKNOWN); UNKNOWN counts are listed separately in every row.",
          "- 29/30 within one block is a pass/fail target. It is not proof of 95% accuracy; see the interval.",
          "- Sample sizes were reduced from the plan (20/20/30/10/30) because only ~50 strips were available "
          "(DECISIONS D-38). Targets are judged on the observed proportion; the 95% intervals show how little "
          "a small n can prove.",
          "- Timing is measured from the START press (made right after dipping and blotting) to the verdict; "
          "the dip-to-START gap is operator time, typically 10-20 s, not measured by the app.",
          f"- Baseline TDS rule (Round 2 logic, RO+UV only when TDS >= {BASELINE_TDS_HOLD_PPM:.0f} ppm): "
          f"would have missed {tds_missed}/{len(tds_known)} spiked samples (meter TDS from the answer key).", "",
          "**Within one block** (definition): for a standard exactly on a chart block, correct = that block "
          "or either neighbour; for a standard between two blocks, correct = either bracketing block. "
          f"Chart blocks (mg/L NO3-): {blocks}.", ""]

    # baselines
    if us:
        L += ["## Baselines on the unseen standards", "", "| Reader | Within one block |", "|---|---|"]
        L.append(f"| StripDock | {frac(wi, len(us))} |")
        for col, name in (("eye_block_mg_L", "Eye vs bottle chart"), ("phone_photo_block_mg_L", "Phone photo vs chart")):
            have = [r for r in us if r["sample_id"] in base and base[r["sample_id"]].get(col, "").strip()]
            ok = sum(float(base[r["sample_id"]][col]) in r["acceptable"] for r in have)
            L.append(f"| {name} | {frac(ok, len(have)) if have else 'not recorded'} |")
        L.append("")

    # per-test tables
    for t in TYPES:
        rows = by(t)
        if not rows:
            continue
        L += [f"## {t} ({len(rows)} reads)", "",
              "| sample | true mg/L | TDS | verdict | est mg/L | block | within 1 block | reasons |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            est = "" if r["est_mg_L"] is None else f"{r['est_mg_L']:.0f}"
            w = "" if t != "unseen_standard" else ("yes" if r["within"] else "no")
            L.append(f"| {r['sample_id']} | {r['true_mg_L']:g} | {r['tds_ppm'] if r['tds_ppm'] is not None else ''} | "
                     f"{r['verdict']}{' (borderline)' if r['borderline'] else ''} | {est} | {r['block_mg_L'] or ''} | {w} | {r['reasons'][:90]} |")
        L.append("")
    if deg_rows:
        L += ["## Degraded captures", "", "| degradation | n | UNKNOWN | other verdicts |", "|---|---|---|---|"]
        kinds = sorted({r.get("degradation") or "?" for r in deg_rows})
        for k in kinds:
            rr = [r for r in deg_rows if (r.get("degradation") or "?") == k]
            u = sum(r["verdict"] == "UNKNOWN" for r in rr)
            other = ", ".join(f"{r['sample_id']}={r['verdict']}" for r in rr if r["verdict"] != "UNKNOWN")
            L.append(f"| {k} | {len(rr)} | {u} | {other} |")
        L.append("")
    # reference method
    if us:
        ref_ok = 0
        for r in us:
            e = r.get("reference_est_mg_L")
            if e is not None and not r.get("reference_rejected"):
                ref_ok += nearest_block(e, blocks, off) in r["acceptable"]
        L += [f"Reference method ({model.ref_name}, logged at read time, not used for decisions): within one block "
              f"{frac(ref_ok, len(us))}.", ""]
    if notes:
        L += ["## Consistency notes", ""] + [f"- {n}" for n in notes] + [""]

    md_path.write_text("\n".join(L), encoding="utf-8")
    for name, rows in ((f"test_reads{suffix}.csv", test_rows), (f"degraded_reads{suffix}.csv", deg_rows)):
        if rows:
            keys = sorted({k for r in rows for k in r})
            with open(out / name, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for r in rows:
                    w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()})
    try:
        figures(us, model, blocks, out, suffix, test_rows)
    except Exception as e:
        print("figures failed:", e)
    print(f"Wrote {md_path}")
    return 0


def figures(us, model, blocks, out, suffix, test_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    if us:
        trues = sorted({r["true_mg_L"] for r in us})
        cols = [str(b) for b in blocks] + ["UNKNOWN"]
        M = np.zeros((len(trues), len(cols)), int)
        for r in us:
            j = cols.index("UNKNOWN") if r["verdict"] == "UNKNOWN" or r["block_mg_L"] is None else \
                [float(b) for b in blocks].index(float(r["block_mg_L"]))
            M[trues.index(r["true_mg_L"]), j] += 1
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.imshow(M, cmap="Blues")
        ax.set_xticks(range(len(cols)), cols)
        ax.set_yticks(range(len(trues)), [f"{t:g}" for t in trues])
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                if M[i, j]:
                    ax.text(j, i, M[i, j], ha="center", va="center")
        ax.set_xlabel("StripDock block (mg/L NO3-)")
        ax.set_ylabel("true standard (mg/L NO3-)")
        ax.set_title("Unseen standards: true vs reported block")
        fig.tight_layout()
        fig.savefig(out / f"fig_confusion{suffix}.png", dpi=120)
        plt.close(fig)
    tr = model.d.get("training_samples", [])
    if tr:
        m = model.d["methods"]["curve"]["model"]
        fig, ax = plt.subplots(figsize=(6, 5))
        lab = np.array([s["lab"] for s in tr])
        sc = ax.scatter(lab[:, 1], lab[:, 2], c=np.log10(np.array([s["conc"] for s in tr]) + 1), cmap="magma_r",
                        s=30, label="training strips")
        nodes = np.array(m["nodes_lab"])
        ax.plot(nodes[:, 1], nodes[:, 2], "-k", lw=1, label="calibration curve")
        for c, n in zip(m["concs"], nodes):
            ax.annotate(f"{c:g}", (n[1], n[2]), fontsize=8)
        ax.set_xlabel("a*")
        ax.set_ylabel("b*")
        ax.legend()
        plt.colorbar(sc, label="log10(mg/L + 1)")
        ax.set_title("Pad colour (corrected CIELAB) with training points")
        fig.tight_layout()
        fig.savefig(out / f"fig_colour_curve{suffix}.png", dpi=120)
        plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
