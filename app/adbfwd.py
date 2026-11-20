"""USB link to the phone: `adb forward tcp:8080 tcp:8080`, so IP Webcam is reached at
http://127.0.0.1:8080 over the USB cable instead of Wi-Fi (DECISIONS D-36).

Enabled when config.yaml has `adb_path` set and `phone_ip: 127.0.0.1`. Needs USB debugging
on the phone and "Always allow from this computer" accepted once.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

_last_try = 0.0


def enabled(cfg: dict) -> bool:
    return bool(cfg.get("adb_path")) and str(cfg.get("phone_ip", "")).startswith("127.0.0.1")


def ensure_forward(cfg: dict, min_interval: float = 5.0) -> str:
    """(Re)create the port forward. Returns '' on success, else an error message.
    Rate-limited so a missing phone does not spawn adb in a tight loop."""
    global _last_try
    if not enabled(cfg):
        return ""
    now = time.time()
    if now - _last_try < min_interval:
        return ""
    _last_try = now
    adb = Path(cfg["adb_path"])
    if not adb.exists():
        return f"adb not found at {adb}"
    port = int(cfg.get("phone_port", 8080))
    try:
        r = subprocess.run([str(adb), "forward", f"tcp:{port}", f"tcp:{port}"], capture_output=True,
                           text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return f"adb failed: {e}"
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if "unauthorized" in msg:
            msg += " (accept 'Allow USB debugging' on the phone)"
        elif "no devices" in msg or "not found" in msg:
            msg += " (is the phone's USB cable plugged in, with USB debugging on?)"
        return f"adb forward failed: {msg}"
    return ""
