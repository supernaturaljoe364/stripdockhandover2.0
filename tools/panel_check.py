r"""Arduino panel check: connect, mirror state, PING every 2 s, send commands by hand.

Usage:
  .venv\\Scripts\\python tools\\panel_check.py            interactive
  .venv\\Scripts\\python tools\\panel_check.py --watch 15  just ping for 15 s and print
Type HOLD, PASS, UNKNOWN, STATUS (or PING), 'state', 'log', or 'quit'.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402
from app.panel import PanelLink, PortBusyError, list_ports  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=float, default=0, help="ping for N seconds then exit")
    ap.add_argument("--port", default=None)
    args = ap.parse_args()
    cfg = load_config()

    print("Serial ports:")
    for dev, desc, hwid in list_ports():
        print(f"  {dev}: {desc}  [{hwid}]")

    def show(entry):
        if entry["dir"] in ("rx", "tx", "sys"):
            ts = time.strftime("%H:%M:%S", time.localtime(entry["t"]))
            print(f"  {ts} {entry['dir']:>3} {entry['text']}")

    link = PanelLink(args.port or cfg.get("serial_port", "auto"), cfg.get("serial_baud", 115200),
                     cfg.get("ping_interval_s", 2.0), log_cb=show)
    try:
        st = link.connect()
    except PortBusyError as e:
        print("\nERROR:", e)
        return 2
    except Exception as e:
        print("\nERROR:", e)
        return 1
    print(f"\nConnected on {link.port}. Board state: {st}")
    link.start()  # PING thread (connect already done, supervisor just pings)

    if args.watch:
        t_end = time.time() + args.watch
        while time.time() < t_end:
            time.sleep(1)
        s = link.snapshot()
        print(f"\nAfter {args.watch:.0f} s: connected={s.connected} state={s.state} "
              f"link_ok={link.link_ok()} (OLED should show 'Link OK')")
        link.close()
        return 0

    print("Commands: HOLD PASS UNKNOWN STATUS PING | state | log | quit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        u = line.upper()
        if u in ("QUIT", "EXIT", "Q"):
            break
        if u == "STATE":
            s = link.snapshot()
            print(f"  connected={s.connected} port={s.port} state={s.state} link_ok={link.link_ok()} err={s.error!r}")
            continue
        if u == "LOG":
            for e in link.snapshot().events:
                show(e)
            continue
        try:
            r = link.send(u)
        except ValueError as e:
            print(" ", e)
            continue
        print(f"  reply state: {r}")
    link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
