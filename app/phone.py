"""IP Webcam (Pavel Khlebovich) HTTP client.

Endpoints used: /status.json?show_avail=1, /shot.jpg (current video frame),
/photo.jpg (camera still), /settings/<key>?set=<value>, /enabletorch, /disabletorch.
/photoaf.jpg and /focus are never used at read time (autofocus changes the image).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import cv2
import numpy as np
import requests


class PhoneError(RuntimeError):
    pass


@dataclass
class Frame:
    bgr: np.ndarray
    jpeg: bytes
    t_request: float
    t_received: float
    endpoint: str
    sha: str

    @property
    def latency(self) -> float:
        return self.t_received - self.t_request


class PhoneCam:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self._last_sha: dict[str, str] = {}

    # ------------------------------------------------------------ status
    def status(self, avail: bool = True) -> dict:
        url = f"{self.base}/status.json" + ("?show_avail=1" if avail else "")
        try:
            r = self.s.get(url, timeout=max(self.timeout, 3.0))
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise PhoneError(f"phone unreachable ({url}): {e}") from e

    def curvals(self) -> dict:
        return self.status(avail=False).get("curvals", {})

    def reachable(self) -> bool:
        try:
            self.status(avail=False)
            return True
        except PhoneError:
            return False

    # ------------------------------------------------------------ frames
    def grab(self, endpoint: str = "/shot.jpg", timeout: float | None = None,
             check_fresh: bool = True) -> Frame:
        if "photoaf" in endpoint or "focus" in endpoint:
            raise PhoneError("autofocus endpoints are not allowed")
        url = self.base + endpoint
        t0 = time.time()
        try:
            r = self.s.get(url, timeout=timeout or max(self.timeout, 1.0))
            r.raise_for_status()
        except Exception as e:
            raise PhoneError(f"frame request failed ({endpoint}): {e}") from e
        t1 = time.time()
        data = r.content
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise PhoneError(f"could not decode JPEG from {endpoint}")
        sha = hashlib.sha1(data).hexdigest()
        if check_fresh and self._last_sha.get(endpoint) == sha:
            # A live sensor never produces byte-identical JPEGs; identical = frozen stream.
            raise PhoneError("stale frame: identical to the previous frame (camera frozen?)")
        self._last_sha[endpoint] = sha
        return Frame(img, data, t0, t1, endpoint, sha)

    # ------------------------------------------------------------ settings
    def set_setting(self, key: str, value) -> str:
        url = f"{self.base}/settings/{key}"
        try:
            r = self.s.get(url, params={"set": str(value)}, timeout=3.0)
            r.raise_for_status()
            return r.text
        except Exception as e:
            raise PhoneError(f"setting {key}={value} failed: {e}") from e

    def trigger_focus(self) -> None:
        """One autofocus run. Used ONLY by lock_camera.py during setup, never at read time."""
        try:
            r = self.s.get(self.base + "/focus", timeout=5.0)
            r.raise_for_status()
        except Exception as e:
            raise PhoneError(f"focus trigger failed: {e}") from e

    def torch(self, on: bool) -> None:
        ep = "/enabletorch" if on else "/disabletorch"
        try:
            r = self.s.get(self.base + ep, timeout=3.0)
            r.raise_for_status()
        except Exception as e:
            raise PhoneError(f"torch {'on' if on else 'off'} failed: {e}") from e
