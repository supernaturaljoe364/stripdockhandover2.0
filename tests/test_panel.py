"""Serial parser + PanelLink against a fake board that runs the StripDockPanel.ino state
machine (transcribed from the sketch) and recorded Arduino lines."""
import threading
import time

import pytest

from app.panel import PanelLink, parse_line, state_after_event

# Lines recorded from the real board on COM8 (2026-11-19, tools/panel_check.py)
RECORDED = ["READY ADAPTIVE", "OK ADAPTIVE", "OK HOLD", "OK CONFIRM_WAIT", "EVT CLEARED",
            "EVT CONFIRM_TIMEOUT", "EVT BUTTON_IGNORED", "ERR unknown command: FOO"]


def test_parse_recorded():
    kinds = [parse_line(x) for x in RECORDED]
    assert (kinds[0].kind, kinds[0].state) == ("ready", "ADAPTIVE")
    assert [k.state for k in kinds[1:4]] == ["ADAPTIVE", "HOLD", "CONFIRM_WAIT"]
    assert [k.event for k in kinds[4:7]] == ["CLEARED", "CONFIRM_TIMEOUT", "BUTTON_IGNORED"]
    assert kinds[7].kind == "err" and kinds[7].text == "unknown command: FOO"
    assert parse_line("OK HOLD\r").state == "HOLD"
    assert parse_line("garbage").kind == "other"
    assert parse_line("OK MAYBE").kind == "other"     # never invent a state


def test_event_mirror():
    assert state_after_event("CONFIRM_WAIT", "CLEARED") == "ADAPTIVE"
    assert state_after_event("CONFIRM_WAIT", "CONFIRM_TIMEOUT") == "HOLD"
    assert state_after_event("HOLD", "BUTTON_IGNORED") == "HOLD"


class FakeBoard:
    """Emulates StripDockPanel.ino over a fake serial port."""

    def __init__(self, held=True, boot_delay=0.3, confirm_s=60.0):
        self.state = "HOLD" if held else "ADAPTIVE"
        self.eeprom_hold = held
        self.out = bytearray()
        self.lock = threading.Lock()
        self.inbuf = b""
        self.boot_delay = boot_delay
        self.confirm_s = confirm_s
        self.confirm_t = None
        self.unplugged = False
        self.received = []

    # serial API
    def open(self, port, baud):
        self.state = "HOLD" if self.eeprom_hold else "ADAPTIVE"   # reset on open (DTR)
        self.t_boot = time.time() + self.boot_delay
        self.booted = False
        return self

    def _tick(self):
        if not self.booted and time.time() >= self.t_boot:
            self.booted = True
            self._emit(f"READY {self.state}")
        if self.state == "CONFIRM_WAIT" and time.time() - self.confirm_t > self.confirm_s:
            self.state = "HOLD"
            self._emit("EVT CONFIRM_TIMEOUT")

    def _emit(self, line):
        with self.lock:
            self.out += (line + "\r\n").encode()

    def read(self, n):
        if self.unplugged:
            import serial
            raise serial.SerialException("device disconnected")
        self._tick()
        time.sleep(0.01)
        with self.lock:
            chunk, self.out[:] = bytes(self.out[:n]), self.out[n:]
        return chunk

    def write(self, data):
        if self.unplugged:
            import serial
            raise serial.SerialException("device disconnected")
        if not self.booted:
            return len(data)           # bootloader swallows bytes
        self.inbuf += data
        while b"\n" in self.inbuf:
            line, self.inbuf = self.inbuf.split(b"\n", 1)
            self._cmd(line.decode().strip().upper())
        return len(data)

    def flush(self):
        pass

    def close(self):
        pass

    def _cmd(self, c):
        self.received.append(c)
        if c == "HOLD":
            self.state, self.eeprom_hold = "HOLD", True
        elif c == "PASS":
            if self.state != "ADAPTIVE":
                self.state, self.confirm_t = "CONFIRM_WAIT", time.time()
        elif c == "UNKNOWN":
            if self.state == "CONFIRM_WAIT":
                self.state = "HOLD"
        elif c in ("PING", "STATUS"):
            pass
        elif c:
            self._emit(f"ERR unknown command: {c}")
            return
        self._emit(f"OK {self.state}")

    def press_button(self):
        if self.state == "CONFIRM_WAIT":
            self.state, self.eeprom_hold = "ADAPTIVE", False
            self._emit("EVT CLEARED")
        else:
            self._emit("EVT BUTTON_IGNORED")


@pytest.fixture
def board(monkeypatch):
    b = FakeBoard()
    monkeypatch.setattr("app.panel.autodetect_port", lambda pref: "COM_FAKE")
    return b


def make_link(board, ping=0.2):
    return PanelLink("COM_FAKE", 115200, ping, serial_factory=board.open)


def wait_for(fn, timeout=3.0):
    t = time.time() + timeout
    while time.time() < t:
        if fn():
            return True
        time.sleep(0.02)
    return False


def test_connect_waits_for_ready_then_status(board):
    link = make_link(board)
    st = link.connect()
    assert st == "HOLD"
    assert board.received[0] == "STATUS"
    link.close()


def test_connect_retries_status_when_ready_missed(board):
    board.boot_delay = 3.4          # READY after the 3 s wait: first STATUS is swallowed
    link = make_link(board)
    assert link.connect(ready_timeout=3.0) == "HOLD"
    link.close()


def test_ping_thread_and_link_ok(board):
    link = make_link(board, ping=0.2)
    link.connect()
    link.start()
    assert wait_for(lambda: board.received.count("PING") >= 3)
    assert link.link_ok()
    link.close()


def test_unknown_on_hold_stays_hold(board):
    link = make_link(board)
    link.connect()
    assert link.send("UNKNOWN") == "HOLD"
    assert link.state == "HOLD"
    link.close()


def test_pass_on_hold_confirm_then_button(board):
    link = make_link(board)
    link.connect()
    assert link.send("PASS") == "CONFIRM_WAIT"
    events = []
    link.add_listener(lambda p: events.append(p.event))
    board.press_button()
    assert wait_for(lambda: link.state == "ADAPTIVE")
    assert "CLEARED" in events
    link.close()


def test_unknown_cancels_confirm(board):
    link = make_link(board)
    link.connect()
    link.send("PASS")
    assert link.send("UNKNOWN") == "HOLD"
    link.close()


def test_confirm_timeout_mirrored(board):
    board.confirm_s = 0.3
    link = make_link(board)
    link.connect()
    link.send("PASS")
    assert wait_for(lambda: link.state == "HOLD", 2.0)
    assert any("CONFIRM_TIMEOUT" in e["text"] for e in link.snapshot().events)
    link.close()


def test_pass_while_adaptive_stays_adaptive(board):
    board.eeprom_hold = False
    link = make_link(board)
    assert link.connect() == "ADAPTIVE"
    assert link.send("PASS") == "ADAPTIVE"
    link.close()


def test_unplug_drops_state_and_reconnects(board):
    link = make_link(board, ping=0.2)
    link.connect()
    link.start()
    link.send("HOLD")
    board.unplugged = True
    assert wait_for(lambda: not link.connected, 3.0)
    assert link.state is None             # never assume a state while unlinked
    assert link.send("PING") is None
    board.unplugged = False
    assert wait_for(lambda: link.connected and link.state == "HOLD", 8.0)  # EEPROM hold survives
    link.close()


def test_rejects_non_protocol_commands(board):
    link = make_link(board)
    link.connect()
    with pytest.raises(ValueError):
        link.send("CLEAR")
    link.close()


def test_silent_board_triggers_reconnect(board):
    link = make_link(board, ping=0.15)
    link.connect()
    link.start()
    opens = []
    orig = board.open
    board.open = lambda port, baud: (opens.append(1), orig(port, baud))[1]
    link._serial_factory = board.open
    board.booted = False                   # board stops answering (as if hung)
    board.t_boot = time.time() + 1e9
    assert wait_for(lambda: len(opens) >= 1, 6.0)     # reconnect attempted after 3 missed PINGs
    board.t_boot = time.time()                        # board answers again after reopen
    assert wait_for(lambda: link.link_ok(), 8.0)
    link.close()
