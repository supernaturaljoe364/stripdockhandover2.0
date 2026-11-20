"""Session folders: data/sessions/<YYYYMMDD_HHMM>_<purpose>/<sample_id>/frames/*.jpg, meta.json."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

from .config import ROOT

PURPOSES = ("train", "test", "degraded", "demo", "dry")
SESSIONS_DIR = ROOT / "data" / "sessions"
DEGRADATIONS = ("drawer_open", "torch_through_seam", "blur", "early_read", "no_strip", "phone_moved", "other")
_SAFE = re.compile(r"[^A-Za-z0-9_\-]")


def safe_id(s: str) -> str:
    s = _SAFE.sub("_", s.strip())
    if not s:
        raise ValueError("sample code is empty")
    return s[:60]


def new_session(purpose: str, operator: str, info: dict, root: Path = SESSIONS_DIR) -> Path:
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}")
    name = time.strftime("%Y%m%d_%H%M") + f"_{purpose}"
    path = root / name
    k = 2
    while path.exists():
        path = root / f"{name}{k}"
        k += 1
    path.mkdir(parents=True)
    meta = {"session": path.name, "purpose": purpose, "operator": operator,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"), "closed": False, **info}
    (path / "session.json").write_text(json.dumps(meta, indent=1))
    return path


def load_session(path: Path) -> dict:
    return json.loads((path / "session.json").read_text())


def sample_dir(session: Path, sample_id: str) -> Path:
    sid = safe_id(sample_id)
    d = session / sid
    k = 2
    while d.exists():
        d = session / f"{sid}_r{k}"   # a re-test of the same code keeps both reads
        k += 1
    (d / "frames").mkdir(parents=True)
    return d


def list_sessions(purpose: str | None = None, root: Path = SESSIONS_DIR) -> list[Path]:
    if not root.exists():
        return []
    out = []
    for p in sorted(root.iterdir()):
        if (p / "session.json").exists():
            if purpose is None or load_session(p).get("purpose") == purpose:
                out.append(p)
    return out


def iter_samples(session: Path):
    for d in sorted(session.iterdir()):
        if d.is_dir() and (d / "meta.json").exists():
            yield d, json.loads((d / "meta.json").read_text())


# ---------------------------------------------------------------- closing (locking)

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def close_session(session: Path) -> Path:
    """Mark closed, write MANIFEST.sha256 of every file, make everything read-only."""
    meta = load_session(session)
    if meta.get("closed"):
        raise RuntimeError(f"{session.name} is already closed")
    meta["closed"] = True
    meta["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (session / "session.json").write_text(json.dumps(meta, indent=1))
    files = sorted(p for p in session.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [f"{_sha(p)}  {p.relative_to(session).as_posix()}" for p in files]
    man = session / "MANIFEST.sha256"
    man.write_text("\n".join(lines) + "\n")
    for p in files + [man]:
        os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    return man


def verify_session(session: Path) -> list[str]:
    """Problems found (empty = intact). Only closed sessions have a manifest."""
    man = session / "MANIFEST.sha256"
    if not man.exists():
        return ["session not closed (no MANIFEST.sha256)"]
    problems = []
    listed = set()
    for line in man.read_text().splitlines():
        if not line.strip():
            continue
        sha, rel = line.split("  ", 1)
        listed.add(rel)
        p = session / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif _sha(p) != sha:
            problems.append(f"modified: {rel}")
    for p in session.rglob("*"):
        if p.is_file() and p.name != "MANIFEST.sha256" and p.relative_to(session).as_posix() not in listed:
            problems.append(f"added after closing: {p.relative_to(session).as_posix()}")
    return problems
