r"""Run one read through the running app (http://localhost:5000) and print a short summary.
Used for operator-guided data collection: the operator dips and places the strip, then
this starts the read (the 60 s timer starts here).

  .venv\\Scripts\python tools\guided_read.py --open train --operator team
  .venv\\Scripts\python tools\guided_read.py S25-1 --conc 25 [--note text] [--panel]
"""
import argparse
import json
import sys
import time
import urllib.request

BASE = "http://localhost:5000"


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sample_id", nargs="?")
    ap.add_argument("--conc", type=float)
    ap.add_argument("--note", default="")
    ap.add_argument("--degradation", default="")
    ap.add_argument("--panel", action="store_true", help="also send the verdict to the panel")
    ap.add_argument("--open", choices=["train", "dry", "test", "degraded", "demo"])
    ap.add_argument("--operator", default="team")
    ap.add_argument("--close", action="store_true")
    a = ap.parse_args()
    if a.open:
        print(call("/api/session/new", {"purpose": a.open, "operator": a.operator}))
        return 0
    if a.close:
        print(call("/api/session/close", {}))
        return 0
    r = call("/api/read/start", {"sample_id": a.sample_id, "concentration": a.conc, "note": a.note,
                                 "degradation": a.degradation, "send_to_panel": a.panel})
    if not r.get("ok"):
        print("NOT STARTED:", r.get("error"))
        return 1
    return wait_and_summarise(a.sample_id)


def wait_and_summarise(sample_id):
    """Wait for the running read to finish and print a short summary from its meta.json."""
    t0 = time.time()
    while True:
        time.sleep(2)
        s = call("/api/state")
        j = s.get("job") or {}
        if j.get("done"):
            break
        if time.time() - t0 > 150:
            print("timeout waiting for the read")
            return 1
    last = s["last"]
    folder = last.get("sample_folder")
    meta = json.load(open(folder + "/meta.json"))
    fr = meta["frames"]
    mt = meta.get("metrics", {})
    f = meta.get("features") or {}
    print(f"{sample_id}: {len(fr)}/5 read frames, verdict {meta['verdict']['command']}, "
          f"start->verdict {meta['start_to_verdict_s']} s")
    print(f"  located ok: {all(x['located_ok'] for x in fr) if fr else False}; shifts "
          f"{[x['patch_shift'] for x in fr][:1]} strip {[x['strip_shift'] for x in fr][:1]}")
    print(f"  max latency {mt.get('latency_max_s')}, errors {mt.get('n_errors')}, retries {mt.get('n_retries')}")
    if f:
        print(f"  pad corrected Lab ({f['pad_L']:.1f}, {f['pad_a']:.1f}, {f['pad_b']:.1f}), "
              f"drift {mt.get('drift_dE')}, glare {mt.get('glare_max')}, sharp {mt.get('sharpness_min')}, "
              f"black L {mt.get('black_L_max')}, strip dE vs empty {mt.get('strip_dE')}")
    print("  failed checks:", [c["name"] for c in meta["checks"] if not c["passed"]])
    print("  reasons:", meta["verdict"].get("reasons", [])[:3])
    print("  folder:", folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
