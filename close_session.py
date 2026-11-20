r"""Close (lock) a session: read-only files + MANIFEST.sha256, so data can't be edited later.

  .venv\Scripts\python close_session.py 20261122_1030_test
  .venv\Scripts\python close_session.py --verify 20261122_1030_test
  .venv\Scripts\python close_session.py --list
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.session import SESSIONS_DIR, close_session, list_sessions, load_session, verify_session  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", nargs="?")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.session:
        for s in list_sessions():
            m = load_session(s)
            n = sum(1 for d in s.iterdir() if d.is_dir())
            print(f"{s.name:32s} {m['purpose']:9s} reads={n:3d} {'CLOSED' if m.get('closed') else 'open'}")
        return 0
    path = SESSIONS_DIR / a.session
    if not (path / "session.json").exists():
        print(f"No session {a.session} in {SESSIONS_DIR}")
        return 2
    if a.verify:
        probs = verify_session(path)
        print("INTACT" if not probs else "PROBLEMS:\n  " + "\n  ".join(probs))
        return 0 if not probs else 1
    man = close_session(path)
    print(f"Closed {a.session}: {len(man.read_text().splitlines())} files hashed in {man.name}, all read-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
