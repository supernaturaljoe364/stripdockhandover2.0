"""Load config.yaml and resolve project paths."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config(path: Path | str | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_path"] = str(p)
    return cfg


def rpath(cfg_value: str) -> Path:
    """Resolve a path from the config relative to the project root."""
    p = Path(cfg_value)
    return p if p.is_absolute() else ROOT / p


def phone_base(cfg: dict) -> str:
    from .adbfwd import ensure_forward
    err = ensure_forward(cfg, min_interval=0.0)
    if err:
        print("WARNING:", err)
    ip = cfg.get("phone_ip")
    if not ip:
        raise ValueError("phone_ip is not set in config.yaml")
    ip = str(ip).replace("http://", "").rstrip("/")
    if ":" in ip:
        return f"http://{ip}"
    return f"http://{ip}:{cfg.get('phone_port', 8080)}"


def stable_hash(obj) -> str:
    """SHA-256 of a JSON-serialisable object with sorted keys (short form)."""
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quality_thresholds(cfg: dict) -> dict:
    return copy.deepcopy(cfg.get("quality", {}))
