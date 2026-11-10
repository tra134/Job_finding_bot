import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from finder.models import Contest, Job
from finder.state import LockHeld, RunLock, State, StateError, item_key


def job(**kw):
    d = dict(title="Thực tập Python", company="Công ty A", location="Da Nang",
             url="https://x.com/j/1?utm=1#f", source="s")
    d.update(kw)
    return Job(**d)


def contest(**kw):
    d = dict(name="Hackathon Đà Nẵng", organiser="Org", mode="online", location="",
             url="https://y.com/c/1?a=b", source="s")
    d.update(kw)
    return Contest(**d)


def test_item_key_job_and_contest():
    assert item_key(job()) == "thuc tap python|cong ty a"
    assert item_key(contest()) == "hackathon da nang|org"


def test_item_key_url_fallback_strips_query_and_fragment():
    a = item_key(job(company="", url="https://x.com/j/1?utm=1#f"))
    b = item_key(job(company="", url="https://x.com/j/1?utm=2"))
    assert a == b == "thuc tap python|https://x.com/j/1"
    assert item_key(contest(organiser="", url="https://y.com/c/1?a=b")) == \
        "hackathon da nang|https://y.com/c/1"


def test_persistence_and_separate_channels(tmp_path):
    p = tmp_path / "sub" / "state.json"
    s = State(p)
    assert not s.is_initialized("jobs")
    s.mark_seen("jobs", ["k1", "k2"])
    s.mark_initialized("jobs")
    when = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    s.record_scan(when)
    s2 = State(p)
    assert s2.is_seen("jobs", "k1") and s2.is_seen("jobs", "k2")
    assert not s2.is_seen("contests", "k1")
    assert s2.is_initialized("jobs") and not s2.is_initialized("contests")
    assert s2.last_scan() == when


def test_missing_file_is_empty(tmp_path):
    s = State(tmp_path / "none.json")
    assert s.last_scan() is None and not s.is_seen("jobs", "x")


@pytest.mark.parametrize("content", ["{not json", "[1,2]", '{"last_scan": "garbage"}'])
def test_corrupt_file_raises_and_stays(tmp_path, content):
    p = tmp_path / "state.json"
    p.write_text(content)
    with pytest.raises(StateError):
        State(p)
    assert p.read_text() == content


def test_atomic_save_mode_600(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.mark_seen("jobs", ["a"])
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert json.loads(p.read_text())["channels"]["jobs"]["seen"] == ["a"]
    assert [f.name for f in tmp_path.iterdir()] == ["state.json"]


def test_failed_save_leaves_old_file(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    s = State(p)
    s.mark_seen("jobs", ["a"])
    before = p.read_text()
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        s.mark_seen("jobs", ["b"])
    assert p.read_text() == before
    assert [f.name for f in tmp_path.iterdir()] == ["state.json"]


def test_scan_due(tmp_path):
    s = State(tmp_path / "state.json")
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert s.scan_due(now)
    s.record_scan(now)
    assert not s.scan_due(now + timedelta(hours=2, minutes=59))
    assert s.scan_due(now + timedelta(hours=3))
    assert s.scan_due(now + timedelta(hours=3, seconds=1))


def test_source_health_blocked_cycle(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.update_source("a", "ok") is False
    assert s.update_source("a", "blocked") is True
    assert s.update_source("a", "blocked") is True
    s.mark_warned("a")
    assert s.update_source("a", "blocked") is False
    assert State(tmp_path / "state.json").update_source("a", "error") is False
    assert s.update_source("a", "ok") is False
    assert s.update_source("a", "error") is True


def test_source_health_empty_threshold_and_skipped(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.update_source("a", "empty") is False
    assert s.update_source("a", "skipped") is False
    assert s.update_source("a", "empty") is False
    assert s.update_source("a", "empty") is True
    s.mark_warned("a")
    assert s.update_source("a", "empty") is False
    s.update_source("a", "ok")
    assert s.update_source("a", "empty") is False
    assert s.update_source("a", "ok") is False
    assert s.update_source("a", "empty") is False
    assert s.update_source("a", "empty") is False


def test_skipped_changes_nothing(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.update_source("a", "blocked")
    before = p.read_text()
    assert s.update_source("a", "skipped") is False
    assert p.read_text() == before


def test_runlock(tmp_path):
    p = tmp_path / "d" / "f.lock"
    with RunLock(p):
        with pytest.raises(LockHeld):
            with RunLock(p):
                pass
    with RunLock(p):
        pass


def test_scan_due_after_reboot(tmp_path):
    s = State(tmp_path / "state.json")
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    s.record_scan(now - timedelta(hours=1))
    assert s.scan_due(now, booted_at=now - timedelta(minutes=5))      # last scan before boot
    assert not s.scan_due(now, booted_at=now - timedelta(hours=2))    # already scanned this boot
    assert not s.scan_due(now, booted_at=None)
