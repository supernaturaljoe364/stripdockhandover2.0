import json
import os

import pytest

from app.session import close_session, iter_samples, new_session, sample_dir, safe_id, verify_session


def test_session_lifecycle(tmp_path):
    s = new_session("test", "op", {"roi_hash": "x"}, root=tmp_path)
    assert s.name.endswith("_test")
    d = sample_dir(s, "B 07")
    assert d.name == "B_07"
    (d / "meta.json").write_text(json.dumps({"sample_id": "B 07"}))
    (d / "frames" / "read_0.jpg").write_bytes(b"jpeg")
    d2 = sample_dir(s, "B 07")
    assert d2.name == "B_07_r2"                    # re-test keeps both
    (d2 / "meta.json").write_text("{}")
    assert len(list(iter_samples(s))) == 2
    close_session(s)
    assert json.loads((s / "session.json").read_text())["closed"]
    assert verify_session(s) == []
    assert not os.access(d / "meta.json", os.W_OK)
    with pytest.raises(RuntimeError):
        close_session(s)
    # tamper
    os.chmod(d / "meta.json", 0o666)
    (d / "meta.json").write_text('{"sample_id": "edited"}')
    (s / "extra.txt").write_text("x")
    probs = verify_session(s)
    assert any("modified" in p for p in probs) and any("added" in p for p in probs)


def test_bad_purpose_and_id(tmp_path):
    with pytest.raises(ValueError):
        new_session("party", "op", {}, root=tmp_path)
    with pytest.raises(ValueError):
        safe_id("   ")
