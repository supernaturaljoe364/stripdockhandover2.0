"""Guards for the honesty and safety rules (master prompt sections 1, 4 and 8)."""
import re
from pathlib import Path

from app.config import ROOT

CODE_DIRS = [ROOT / "app", ROOT / "tools"]
CODE_FILES = [p for d in CODE_DIRS for p in d.rglob("*") if p.suffix in (".py", ".html", ".js")] + \
             [ROOT / f for f in ("run_app.py", "train.py", "freeze_model.py", "evaluate.py", "close_session.py")]
SAFE_WORD = re.compile(r"(?<![a-z_-])safe(?![a-z_-])", re.I)   # "safety", "safe_load", "thread-safe" are fine


def test_app_never_reads_answer_key():
    for p in [x for x in (ROOT / "app").rglob("*") if x.suffix in (".py", ".html", ".js")] + [ROOT / "run_app.py"]:
        assert "answer_key" not in p.read_text(encoding="utf-8"), p


def test_only_evaluate_reads_answer_key():
    readers = [p.name for p in CODE_FILES if "test_answer_key" in p.read_text(encoding="utf-8")]
    assert readers == ["evaluate.py"], readers


def test_no_safe_wording_in_code_or_ui():
    for p in CODE_FILES:
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines():
            if SAFE_WORD.search(line):
                # only allowed in comments/docstrings that state the rule itself
                assert "never" in line.lower() or "not" in line.lower(), f"{p.name}: {line.strip()}"
        for line in text.lower().splitlines():
            if "safe to drink" in line:
                assert "never" in line or "not" in line, f"{p.name}: {line.strip()}"


def test_no_synthetic_data_in_data_or_results():
    for d in (ROOT / "data", ROOT / "results"):
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".csv", ".md", ".txt"):
                t = p.read_text(encoding="utf-8", errors="ignore")
                assert "SYNTHETIC" not in t and '"synthetic": true' not in t, p
            assert "SYN_" not in p.name and "SYNTHETIC" not in p.name, p


def test_unknown_never_mapped_to_pass_in_code():
    for p in CODE_FILES:
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"UNKNOWN['\"]?\s*[:=]+\s*['\"]?PASS", t), p


def test_flask_app_smoke(cfg):
    from app.station import Station
    from app.web import create_app
    st = Station(cfg, start_threads=False)
    c = create_app(st).test_client()
    assert c.get("/").status_code == 200
    assert c.get("/calibrate").status_code == 200
    s = c.get("/api/state").get_json()
    assert s["can_start"] is False and s["why_not"]
    r = c.post("/api/read/start", json={"sample_id": "X"})
    assert r.status_code == 400 and "START blocked" in r.get_json()["error"]
    r = c.post("/api/panel/send", json={"cmd": "PASS"})
    assert r.status_code == 400            # PASS is never sent by hand
    html = c.get("/").get_data(as_text=True)
    assert not SAFE_WORD.search(html)
    assert c.get("/api/preview.jpg").status_code == 200
