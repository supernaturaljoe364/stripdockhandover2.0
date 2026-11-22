r"""Hardware-in-the-loop check, run with an operator watching. Close the web app first
(only one program can hold the Arduino's COM port).

  .venv\\Scripts\\python tools\\hil_check.py              all steps
  .venv\\Scripts\\python tools\\hil_check.py --steps 1 2 3
  .venv\\Scripts\\python tools\\hil_check.py --read-time 20   shorter strip timer for steps 4-6 (logged)

Steps:
 1. PING keeps Link OK (operator confirms the OLED).
 2. UNKNOWN while on HOLD -> stays HOLD.
 3. PASS while on HOLD -> CONFIRM_WAIT; operator presses CONFIRM -> ADAPTIVE mirrored.
 4. Phone link lost mid-read (USB cable unplugged, or IP Webcam server stopped) -> UNKNOWN.
 5. Drawer opened mid-read -> light-leak fail -> UNKNOWN.
 6. Dry, undipped strip read -> record what happens.
Results are appended to results\\hil_log.md with times.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_config  # noqa: E402

LOG = ROOT / "results" / "hil_log.md"


def log(step, result, detail):
    LOG.parent.mkdir(exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("# Hardware-in-the-loop log\n\n| time | step | result | detail |\n|---|---|---|---|\n")
        f.write(f"| {time.strftime('%Y-%m-%d %H:%M:%S')} | {step} | {result} | {detail.replace('|', '/')} |\n")
    print(f"  -> {result}: {detail}")


NO_PROMPT = False


def ask(q):
    """Operator yes/no. With --no-prompt the answer is recorded separately by whoever runs it."""
    if NO_PROMPT:
        print(f"  (operator question, answer recorded separately: {q})")
        return None
    return input(f"{q} [y/n] ").strip().lower().startswith("y")


def wait_state(link, want, timeout):
    t = time.time() + timeout
    while time.time() < t:
        if link.state == want:
            return True
        time.sleep(0.1)
    return False


def run_read(station, note, purpose="dry"):
    from app.readflow import ReadJob
    if station.session is None:
        station.open_session(purpose, "hil_check")
    job = ReadJob(station, station.session, purpose, f"HIL_{note}", {"note": note}, send_to_panel=True).start()
    last = -1
    while not job.progress["done"]:
        el = int(job.progress.get("elapsed", 0))
        if el != last and el % 5 == 0:
            print(f"    t={el:3d}s {job.progress.get('phase')}")
            last = el
        time.sleep(0.2)
    return job.result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", nargs="*", type=int, default=[1, 2, 3, 4, 5, 6])
    ap.add_argument("--read-time", type=float, default=None)
    ap.add_argument("--no-prompt", action="store_true", help="steps 1-3 only; operator answers logged separately")
    a = ap.parse_args()
    global NO_PROMPT
    NO_PROMPT = a.no_prompt
    cfg = load_config()
    if a.read_time:
        cfg["read_time_s"] = a.read_time
    from app.station import Station
    st = Station(cfg)
    print("Connecting to the panel ...")
    if not _wait_link(st, 12):
        print("Panel not linked:", st.panel.snapshot().error)
        log("setup", "FAIL", f"panel not linked: {st.panel.snapshot().error}")
        return 1
    link = st.panel
    print(f"Panel linked on {link.port}, state {link.state}")
    try:
        if 1 in a.steps:
            print("\nStep 1: pinging for 12 s ...")
            time.sleep(12)
            seen = ask("Does the OLED bottom line say 'Link OK'?")
            ok = link.link_ok() and seen is not False
            log("1 ping keeps Link OK", ("PASS" if ok else "FAIL") + (" (software side; OLED: see operator line)" if seen is None else ""),
                f"link_ok={link.link_ok()}, operator saw Link OK={seen}")
        if 2 in a.steps:
            print("\nStep 2: HOLD, then UNKNOWN")
            r1 = link.send("HOLD")
            r2 = link.send("UNKNOWN")
            ok = r1 == "HOLD" and r2 == "HOLD"
            log("2 UNKNOWN on HOLD stays HOLD", "PASS" if ok else "FAIL", f"HOLD->{r1}, UNKNOWN->{r2}")
        if 3 in a.steps:
            print("\nStep 3: PASS while on HOLD")
            if link.state != "HOLD":
                link.send("HOLD")
            r = link.send("PASS")
            print(f"  panel replied {r}. PRESS THE CONFIRM BUTTON NOW (within 60 s).")
            ok = r == "CONFIRM_WAIT" and wait_state(link, "ADAPTIVE", 62)
            seen = ask("Did the green LED light, then the OLED show ADAPTIVE after the press?")
            log("3 PASS on HOLD -> CONFIRM_WAIT -> button -> ADAPTIVE", "PASS" if ok and seen is not False else "FAIL",
                f"PASS->{r}, mirrored state now {link.state}, operator confirmed={seen}")
        if any(s in a.steps for s in (4, 5, 6)):
            items = st.checklist_items("dry")
            bad = [f"{n}: {w}" for n, ok, w in items if not ok and n not in ("Session open",)]
            if bad:
                print("Read steps need the station ready:", bad)
                for s in (4, 5, 6):
                    if s in a.steps:
                        log(f"{s} read step", "PENDING", "station not ready: " + "; ".join(bad))
                return 0
            link.send("HOLD")
        if 4 in a.steps:
            input("\nStep 4: put a strip in the tray, close the drawer, press ENTER. "
                  "When the countdown passes ~10 s, UNPLUG the phone's USB cable "
                  "(or stop IP Webcam's server). Leave it out until the verdict shows.")
            r = run_read(st, "phone_link_lost")
            v = r["verdict"]
            ok = v["command"] == "UNKNOWN" and any("phone" in x or "frame" in x for x in v["reasons"])
            log("4 phone link lost mid-read (USB cable pulled / server stopped)", "PASS" if ok else "FAIL",
                f"verdict {v['command']}; reasons {v['reasons'][:2]}; panel {r.get('panel_reply')} "
                f"(read_time {cfg['read_time_s']} s)")
            input("  Plug the phone's USB cable back in (if IP Webcam's server was stopped instead: "
                  "Start server, then run tools\\lock_camera.py). Wait 10 s, press ENTER.")
        if 5 in a.steps:
            input("\nStep 5: strip in, drawer closed, press ENTER. At ~10 s pull the drawer open a few cm.")
            r = run_read(st, "drawer_open")
            v = r["verdict"]
            ok = v["command"] == "UNKNOWN" and any("light leak" in x or "not seated" in x for x in v["reasons"])
            log("5 drawer opened mid-read", "PASS" if ok else "FAIL",
                f"verdict {v['command']}; reasons {v['reasons'][:2]} (read_time {cfg['read_time_s']} s)")
        if 6 in a.steps:
            input("\nStep 6: put a DRY, undipped strip in, drawer closed, press ENTER.")
            r = run_read(st, "dry_undipped_strip")
            v = r["verdict"]
            log("6 dry undipped strip", "RECORDED", f"verdict {v['command']}; est {v.get('est_mg_L')}; "
                f"reasons {v['reasons'][:2]}; features {r.get('features')}")
            print("  If this read like 0 mg/L (PASS), the limitation 'a dry strip can read as 0' stands.")
    finally:
        st.stop()
    return 0


def _wait_link(st, timeout):
    t = time.time() + timeout
    while time.time() < t:
        if st.panel.link_ok():
            return True
        time.sleep(0.2)
    return False


if __name__ == "__main__":
    sys.exit(main())
