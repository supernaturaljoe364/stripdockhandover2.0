"""Arduino Nano panel link (StripDockPanel.ino protocol, section 3 of the master prompt).

- 115200 baud, newline-terminated ASCII commands: HOLD PASS UNKNOWN PING STATUS.
- Every command -> "OK <STATE>", STATE in ADAPTIVE | HOLD | CONFIRM_WAIT.
- Unknown command -> "ERR unknown command: <text>".
- Boot -> "READY <STATE>". Opening the port resets the Nano (DTR): wait up to 3 s for
  READY, then send STATUS.
- Async events: EVT CLEARED, EVT CONFIRM_TIMEOUT, EVT BUTTON_IGNORED.
- The PC sends PING every 2 s. The Arduino is the source of truth for the hold; this
  class only mirrors what the board reports and never assumes a state.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from dataclasses import dataclass, field

STATES = ("ADAPTIVE", "HOLD", "CONFIRM_WAIT")
COMMANDS = ("HOLD", "PASS", "UNKNOWN", "PING", "STATUS")
EVENTS = ("CLEARED", "CONFIRM_TIMEOUT", "BUTTON_IGNORED")

_RE_OK = re.compile(r"^OK\s+(ADAPTIVE|HOLD|CONFIRM_WAIT)$")
_RE_READY = re.compile(r"^READY\s+(ADAPTIVE|HOLD|CONFIRM_WAIT)$")
_RE_EVT = re.compile(r"^EVT\s+([A-Z_]+)$")
_RE_ERR = re.compile(r"^ERR\s+(.*)$")


@dataclass
class ParsedLine:
    kind: str                 # ok | ready | evt | err | other
    state: str | None = None  # for ok / ready
    event: str | None = None  # for evt
    text: str = ""


def parse_line(line: str) -> ParsedLine:
    s = line.strip()
    if m := _RE_OK.match(s):
        return ParsedLine("ok", state=m.group(1), text=s)
    if m := _RE_READY.match(s):
        return ParsedLine("ready", state=m.group(1), text=s)
    if m := _RE_EVT.match(s):
        return ParsedLine("evt", event=m.group(1), text=s)
    if m := _RE_ERR.match(s):
        return ParsedLine("err", text=m.group(1))
    return ParsedLine("other", text=s)


def state_after_event(prev: str | None, event: str) -> str | None:
    """Mirror rule for async events (from the sketch)."""
    if event == "CLEARED":
        return "ADAPTIVE"
    if event == "CONFIRM_TIMEOUT":
        return "HOLD"
    return prev  # BUTTON_IGNORED changes nothing


def list_ports():
    from serial.tools import list_ports as lp
    return [(p.device, p.description or "", p.hwid or "") for p in lp.comports()]


_USB_SERIAL_HINTS = ("CH340", "USB-SERIAL", "USB SERIAL", "FTDI", "ARDUINO", "CP210")


def autodetect_port(preferred: str | None) -> str:
    ports = list_ports()
    names = [p[0] for p in ports]
    if preferred and preferred.lower() != "auto" and preferred in names:
        return preferred
    cands = [p for p in ports if any(h in (p[1] + " " + p[2]).upper() for h in _USB_SERIAL_HINTS)]
    if len(cands) == 1:
        return cands[0][0]
    if not cands:
        raise RuntimeError(f"No USB-serial port found (ports: {ports or 'none'}). "
                           "Is the Arduino plugged in?")
    raise RuntimeError(f"Several USB-serial ports found: {cands}. Set serial_port in config.yaml.")


class PortBusyError(RuntimeError):
    pass


@dataclass
class PanelSnapshot:
    connected: bool
    state: str | None
    port: str | None
    last_rx: float | None
    last_ping_ok: float | None
    error: str
    events: list = field(default_factory=list)


class PanelLink:
    """Thread-safe serial link with a reader thread and a 2 s PING thread.

    send(cmd) writes one command and waits for its OK reply. Reconnects automatically
    if the USB cable is pulled and replugged (the board then reboots and reports its
    EEPROM state with READY)."""

    def __init__(self, port: str = "auto", baud: int = 115200, ping_interval: float = 2.0,
                 log_cb=None, serial_factory=None):
        self.port_pref = port
        self.baud = baud
        self.ping_interval = ping_interval
        self._serial_factory = serial_factory
        self._ser = None
        self.port = None
        self._lock = threading.RLock()        # guards state fields
        self._cmd_lock = threading.Lock()     # one outstanding command at a time
        self._reply_cv = threading.Condition()
        self._replies: collections.deque = collections.deque()
        self._ready_evt = threading.Event()
        self.state: str | None = None
        self.connected = False
        self.last_rx: float | None = None
        self.last_ping_ok: float | None = None
        self.error = ""
        self.events: collections.deque = collections.deque(maxlen=500)
        self._listeners = []
        self._log_cb = log_cb
        self._stop = threading.Event()
        self._threads = []

    # ------------------------------------------------------------ logging / events
    def _log(self, direction: str, text: str):
        entry = {"t": time.time(), "dir": direction, "text": text}
        with self._lock:
            self.events.append(entry)
        if self._log_cb:
            try:
                self._log_cb(entry)
            except Exception:
                pass

    def add_listener(self, fn):
        """fn(parsed_line) is called for every READY/EVT line."""
        self._listeners.append(fn)

    def snapshot(self) -> PanelSnapshot:
        with self._lock:
            return PanelSnapshot(self.connected, self.state, self.port, self.last_rx,
                                 self.last_ping_ok, self.error, list(self.events)[-50:])

    def link_ok(self, max_age: float = 5.0) -> bool:
        with self._lock:
            return (self.connected and self.state is not None and self.last_ping_ok is not None
                    and time.time() - self.last_ping_ok < max_age)

    # ------------------------------------------------------------ open / close
    def _open_serial(self):
        import serial
        port = autodetect_port(self.port_pref)
        try:
            if self._serial_factory:
                ser = self._serial_factory(port, self.baud)
            else:
                ser = serial.Serial(port, self.baud, timeout=0.2, write_timeout=1.0)
        except serial.SerialException as e:
            msg = str(e)
            if "Access is denied" in msg or "PermissionError" in msg or "busy" in msg.lower():
                raise PortBusyError(
                    f"{port} is in use by another program (Access is denied). Close the Arduino "
                    "IDE Serial Monitor / Serial Plotter and any other serial tool, then retry.") from e
            raise
        return port, ser

    def connect(self, ready_timeout: float = 3.0) -> str | None:
        """Open the port, wait for READY (board resets on open), send STATUS.
        Returns the board state. Raises on failure."""
        port, ser = self._open_serial()
        with self._lock:
            self._ser = ser
            self.port = port
            self.state = None
            self.error = ""
        self._ready_evt.clear()
        self._log("sys", f"opened {port} @ {self.baud}")
        if not any(t.name == "panel-reader" and t.is_alive() for t in self._threads):
            t = threading.Thread(target=self._reader, name="panel-reader", daemon=True)
            t.start()
            self._threads.append(t)
        got_ready = self._ready_evt.wait(ready_timeout)
        if not got_ready:
            self._log("sys", f"no READY within {ready_timeout:.0f} s (board may not have reset); sending STATUS")
        with self._lock:
            self.connected = True
        # READY was measured at ~3 s after open on this board; if it was missed (slow
        # boot), STATUS is retried so a command sent into the bootloader is not fatal.
        st = None
        for _attempt in range(3):
            st = self.send("STATUS", timeout=1.5)
            if st is not None:
                break
        if st is None:
            with self._lock:
                self.connected = False
                self.error = "no reply to STATUS"
            raise RuntimeError(f"Arduino on {port} did not answer STATUS")
        return st

    def start(self):
        """Connect (with retry in the background) and start the PING thread."""
        t = threading.Thread(target=self._supervisor, name="panel-supervisor", daemon=True)
        t.start()
        self._threads.append(t)

    def close(self):
        self._stop.set()
        with self._lock:
            ser, self._ser = self._ser, None
            self.connected = False
        if ser:
            try:
                ser.close()
            except Exception:
                pass

    def _drop(self, why: str):
        with self._lock:
            ser, self._ser = self._ser, None
            self.connected = False
            self.state = None          # never assume a state while unlinked
            self.error = why
        self._log("sys", f"link dropped: {why}")
        if ser:
            try:
                ser.close()
            except Exception:
                pass

    # ------------------------------------------------------------ threads
    MAX_MISSED_PINGS = 3

    def _supervisor(self):
        next_ping = 0.0
        missed = 0
        while not self._stop.is_set():
            if not self.connected:
                try:
                    self.connect()
                    next_ping = time.time() + self.ping_interval
                    missed = 0
                except Exception as e:
                    with self._lock:
                        self.error = str(e)
                    self._stop.wait(2.0)
                    continue
            now = time.time()
            if now >= next_ping:
                next_ping = now + self.ping_interval
                if self.send("PING", timeout=1.0) is None and self.connected:
                    missed += 1
                    with self._lock:
                        self.error = f"PING not answered ({missed}x)"
                    if missed >= self.MAX_MISSED_PINGS:
                        # reopen the port: the board resets and reports its EEPROM state
                        self._drop(f"{missed} PINGs unanswered; reconnecting")
                        missed = 0
                else:
                    missed = 0
                    with self._lock:
                        if self.error.startswith("PING not answered"):
                            self.error = ""
            self._stop.wait(0.05)

    def _reader(self):
        buf = b""
        while not self._stop.is_set():
            ser = self._ser
            if ser is None:
                time.sleep(0.1)
                continue
            try:
                chunk = ser.read(256)
            except Exception as e:
                self._drop(f"read error: {e}")
                continue
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    try:
                        self._handle_line(line)
                    except Exception as e:      # the reader thread must never die
                        self._log("sys", f"error handling line {line!r}: {e}")

    def _handle_line(self, line: str):
        self._log("rx", line)
        p = parse_line(line)
        with self._lock:
            self.last_rx = time.time()
            if p.kind in ("ok", "ready"):
                self.state = p.state
            elif p.kind == "evt":
                self.state = state_after_event(self.state, p.event)
        if p.kind == "ready":
            self._ready_evt.set()
        if p.kind in ("ok", "err"):
            with self._reply_cv:
                self._replies.append(p)
                self._reply_cv.notify_all()
        if p.kind in ("ready", "evt"):
            for fn in self._listeners:
                try:
                    fn(p)
                except Exception:
                    pass

    # ------------------------------------------------------------ commands
    def send(self, cmd: str, timeout: float = 1.5) -> str | None:
        """Send a command and return the state from its OK reply, or None."""
        cmd = cmd.strip().upper()
        if cmd not in COMMANDS:
            raise ValueError(f"not a panel command: {cmd}")
        with self._cmd_lock:
            ser = self._ser
            if ser is None:
                return None
            with self._reply_cv:
                self._replies.clear()
            try:
                ser.write((cmd + "\n").encode("ascii"))
                ser.flush()
            except Exception as e:
                self._drop(f"write error: {e}")
                return None
            if cmd != "PING":
                self._log("tx", cmd)
            deadline = time.time() + timeout
            with self._reply_cv:
                while not self._replies:
                    left = deadline - time.time()
                    if left <= 0:
                        break
                    self._reply_cv.wait(left)
                rep = self._replies.popleft() if self._replies else None
        if rep is None:
            self._log("sys", f"no reply to {cmd}")
            return None
        if rep.kind == "err":
            self._log("sys", f"{cmd} -> ERR {rep.text}")
            return None
        with self._lock:
            self.last_ping_ok = time.time()   # any answered command proves the link
        return rep.state
