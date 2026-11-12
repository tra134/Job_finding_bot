from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from finder import main as fm
from finder import state as st
from finder import telegram as tg
from finder.http_client import BlockedError, RobotsDisallowed
from finder.models import Contest, Job

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
ENV = "TELEGRAM_BOT_TOKEN=SECRET-TOKEN\nTELEGRAM_JOBS_CHAT_ID=-1\nTELEGRAM_CONTESTS_CHAT_ID=-2\n"


def job(i, title=None):
    return Job(title=title or f"Python Intern {i:03d}", company=f"Co{i:03d}",
               location="Da Nang", url=f"https://x.example/{i}", source="fake")


def contest(i):
    return Contest(name=f"AI Hackathon {i}", organiser=f"Org{i}", mode="da nang", location="Da Nang",
                   url=f"https://c.example/{i}", source="fakec", topic="AI")


class Src:
    def __init__(self, items=(), exc=None):
        self.items, self.exc, self.calls = list(items), exc, 0

    def fetch(self, client):
        self.calls += 1
        if self.exc:
            raise self.exc
        return list(self.items)


class FakeSender:
    def __init__(self, fail_from=None, fail_if=None):
        self.sent, self.fail_from, self.fail_if = [], fail_from, fail_if

    def send(self, chat_id, text):
        if (self.fail_from is not None and len(self.sent) >= self.fail_from) or \
                (self.fail_if and self.fail_if(chat_id, text)):
            raise tg.TelegramError("boom")
        self.sent.append((chat_id, text))


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(ENV)
    jobs, contests = Src([job(1), job(2)]), Src([contest(1)])
    monkeypatch.setattr(fm, "JOB_SOURCES", {"j": jobs})
    monkeypatch.setattr(fm, "CONTEST_SOURCES", {"c": contests})
    return SimpleNamespace(root=tmp_path, jobs=jobs, contests=contests,
                           state_path=tmp_path / "state" / "state.json")


def run(env, *args, sender=None, net=lambda: True, sleep=lambda s: None, booted=None):
    sender = sender or FakeSender()
    rc = fm.main(list(args), root=env.root, sender_factory=lambda token: sender, sleep=sleep,
                 net_check=net, now=lambda: NOW, client_factory=object,
                 booted_at=lambda: booted)
    return rc, sender


def state(env):
    return st.State(env.state_path)


def init(env, *channels):
    s = state(env)
    for c in channels:
        s.mark_initialized(c)


def test_dry_run_sends_nothing_writes_no_state(env, capsys):
    rc, sender = run(env, "--dry-run")
    assert rc == 0 and sender.sent == []
    assert not (env.root / "state").exists()
    assert "Source report" in capsys.readouterr().out
    assert env.contests.calls == 0  # jobs only by default


def test_dry_run_needs_no_config(env):
    (env.root / ".env").unlink()
    assert run(env, "--dry-run")[0] == 0


def test_missing_config_exits_2_no_scraping(env, capsys):
    (env.root / ".env").write_text("TELEGRAM_BOT_TOKEN=x\n")
    rc, sender = run(env)
    err = capsys.readouterr().err
    assert rc == 2 and "TELEGRAM_JOBS_CHAT_ID" in err
    assert env.jobs.calls == 0 and sender.sent == []
    assert not env.state_path.exists()


def test_missing_env_file(env):
    (env.root / ".env").unlink()
    assert run(env)[0] == 2 and env.jobs.calls == 0


def test_three_hour_guard_and_force(env, capsys):
    init(env, "jobs", "contests")
    state(env).record_scan(NOW - timedelta(hours=1))
    rc, sender = run(env)
    assert rc == 0 and env.jobs.calls == 0 and sender.sent == []
    rc, sender = run(env, "--force")
    assert rc == 0 and env.jobs.calls == 1


def test_guard_allows_after_three_hours(env):
    init(env, "jobs", "contests")
    state(env).record_scan(NOW - timedelta(hours=4))
    run(env)
    assert env.jobs.calls == 1


def test_lock_held(env, capsys):
    with st.RunLock(env.root / "state" / "finder.lock"):
        rc, sender = run(env, "--force")
    assert rc == 0 and env.jobs.calls == 0 and sender.sent == []


def test_network_down_exits_0_without_scan_update(env):
    sleeps = []
    rc, sender = run(env, net=lambda: False, sleep=sleeps.append)
    assert rc == 0 and env.jobs.calls == 0 and sender.sent == []
    assert 0 < sum(sleeps) <= 330
    assert state(env).last_scan() is None


def test_network_comes_back(env):
    calls = iter([False, False, True])
    rc, _ = run(env, net=lambda: next(calls))
    assert rc == 0 and env.jobs.calls == 1


def test_seed_marks_everything_sends_nothing(env):
    rc, sender = run(env, "--seed")
    s = state(env)
    assert rc == 0 and sender.sent == []
    assert s.is_initialized("jobs") and s.is_initialized("contests")
    assert s.is_seen("jobs", st.item_key(job(1))) and s.is_seen("contests", st.item_key(contest(1)))
    assert s.last_scan() == NOW


def test_seed_needs_no_config_and_sends_no_warnings(env):
    (env.root / ".env").unlink()
    env.jobs.exc = BlockedError("403")
    rc, sender = run(env, "--seed", "--channel", "contests")
    assert rc == 0 and sender.sent == []


def test_seed_does_not_warn_on_blocked_source(env):
    env.jobs.exc = BlockedError("403")
    rc, sender = run(env, "--seed")
    assert sender.sent == []


def test_first_run_sends_one_summary_and_marks_all(env):
    env.jobs.items = [job(i) for i in range(30)]
    rc, sender = run(env)
    s = state(env)
    assert rc == 0
    assert [c for c, _ in sender.sent] == ["-1", "-2"]
    assert sender.sent[0][1] == tg.first_run_summary("jobs", 30)
    assert all(s.is_seen("jobs", st.item_key(job(i))) for i in range(30))
    assert s.is_initialized("jobs") and s.is_initialized("contests")
    assert s.last_scan() == NOW


def test_first_run_send_failure_marks_nothing(env, capsys):
    rc, sender = run(env, sender=FakeSender(fail_if=lambda c, t: c == "-1"))
    s = state(env)
    assert rc == 1
    assert not s.is_initialized("jobs") and not s.is_seen("jobs", st.item_key(job(1)))
    assert s.is_initialized("contests")  # other channel unaffected
    assert s.last_scan() is None
    assert "SECRET-TOKEN" not in capsys.readouterr().err


def test_normal_run_sends_only_new(env):
    init(env, "jobs", "contests")
    state(env).mark_seen("jobs", [st.item_key(job(1))])
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    rc, sender = run(env)
    assert rc == 0
    assert len(sender.sent) == 1 and sender.sent[0][0] == "-1"
    assert "Python Intern 002" in sender.sent[0][1] and "Python Intern 001" not in sender.sent[0][1]
    assert state(env).is_seen("jobs", st.item_key(job(2)))
    assert state(env).last_scan() == NOW


def test_normal_run_nothing_new_sends_nothing(env):
    init(env, "jobs", "contests")
    state(env).mark_seen("jobs", [st.item_key(job(1)), st.item_key(job(2))])
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    rc, sender = run(env)
    assert rc == 0 and sender.sent == []


def test_partial_delivery_marks_only_delivered(env, capsys):
    init(env, "jobs", "contests")
    items = [job(i, f"Python Intern {i:03d} " + "x" * 150) for i in range(60)]
    env.jobs.items = items
    rc, sender = run(env, "--channel", "jobs", sender=FakeSender(fail_from=1))
    s = state(env)
    assert rc == 1 and len(sender.sent) == 1
    delivered = sender.sent[0][1]
    seen = [s.is_seen("jobs", st.item_key(j)) for j in items]
    assert any(seen) and not all(seen)
    for j, was in zip(items, seen):
        assert was == (j.title in delivered)


def test_one_channel_failing_does_not_stop_other(env):
    init(env, "jobs", "contests")
    rc, sender = run(env, sender=FakeSender(fail_if=lambda c, t: c == "-1"))
    assert rc == 1
    assert [c for c, _ in sender.sent] == ["-2"]
    assert state(env).is_seen("contests", st.item_key(contest(1)))
    assert not state(env).is_seen("jobs", st.item_key(job(1)))
    assert state(env).last_scan() is None


def test_record_scan_not_with_sources_filter(env):
    init(env, "jobs", "contests")
    rc, _ = run(env, "--sources", "j")
    assert rc == 0 and env.jobs.calls == 1 and env.contests.calls == 0
    assert state(env).last_scan() is None


def test_record_scan_not_with_channel_filter(env):
    init(env, "jobs", "contests")
    run(env, "--channel", "jobs")
    assert state(env).last_scan() is None


def test_record_scan_requires_ok_source_in_each_channel(env):
    init(env, "jobs", "contests")
    env.contests.exc = BlockedError("403")
    rc, _ = run(env)
    assert state(env).last_scan() is None


def test_empty_counts_as_data(env):
    init(env, "jobs", "contests")
    env.jobs.items, env.contests.items = [], []
    run(env)
    assert state(env).last_scan() == NOW


def test_unknown_source_exits_2(env):
    assert run(env, "--sources", "nope")[0] == 2 and env.jobs.calls == 0


def test_robots_disallowed_is_skipped():
    src = Src(exc=RobotsDisallowed("robots"))
    jobs, status, _ = fm.run_source("j", src, None)
    assert (jobs, status) == ([], "skipped")
    assert fm.run_source("j", Src(exc=BlockedError("x")), None)[1] == "blocked"
    assert fm.run_source("j", Src(exc=ValueError("x")), None)[1] == "error"


def test_skipped_source_does_not_warn_or_count(env):
    init(env, "jobs", "contests")
    state(env).mark_seen("jobs", [st.item_key(job(1)), st.item_key(job(2))])
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    env.jobs.exc = RobotsDisallowed("robots")
    rc, sender = run(env)
    assert sender.sent == [] and state(env).last_scan() is None


def test_source_warning_sent_once_to_its_channel(env):
    init(env, "jobs", "contests")
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    env.jobs.exc = BlockedError("HTTP 403")
    for _ in range(st.FAIL_THRESHOLD - 1):      # a one-off failure stays quiet
        rc, sender = run(env, "--force")
        assert sender.sent == []
    rc, sender = run(env, "--force")
    assert rc == 0 or rc == 1
    assert len(sender.sent) == 1 and sender.sent[0][0] == "-1"
    assert "j" in sender.sent[0][1]
    rc, sender = run(env, "--force")
    assert sender.sent == []


def test_failed_warning_is_retried(env):
    init(env, "jobs", "contests")
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    env.jobs.exc = BlockedError("HTTP 403")
    for _ in range(st.FAIL_THRESHOLD - 1):
        run(env, "--force")
    rc, sender = run(env, "--force", sender=FakeSender(fail_from=0))
    assert rc == 1
    rc, sender = run(env, "--force")
    assert len(sender.sent) == 1 and sender.sent[0][0] == "-1"


def test_load_env_parsing(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# c\nA=1\nB = \"two\"\n\nbad line\nC='3'\n")
    assert fm.load_env(p) == {"A": "1", "B": "two", "C": "3"}
    assert fm.load_env(tmp_path / "none") == {}


def hcm_job(i):
    return Job(title=f"Python Intern {i:03d}", company=f"Co{i:03d}", location="Ho Chi Minh",
               url=f"https://x.example/{i}", source="fake")


def test_job_areas_danang_only_skips_other_cities(env):
    (env.root / ".env").write_text(ENV + "JOB_AREAS=danang\n")
    env.jobs.items = [job(1), hcm_job(2)]
    init(env, "jobs", "contests")
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    rc, sender = run(env)
    assert rc == 0 and len(sender.sent) == 1
    assert "Python Intern 001" in sender.sent[0][1]
    assert "Python Intern 002" not in sender.sent[0][1] and "other cities" not in sender.sent[0][1]
    assert not state(env).is_seen("jobs", st.item_key(hcm_job(2)))


def test_job_areas_unset_keeps_all(env):
    env.jobs.items = [job(1), hcm_job(2)]
    init(env, "jobs", "contests")
    state(env).mark_seen("contests", [st.item_key(contest(1))])
    rc, sender = run(env)
    assert rc == 0 and "Python Intern 002" in sender.sent[0][1]


def test_job_areas_invalid_exits_2(env, capsys):
    (env.root / ".env").write_text(ENV + "JOB_AREAS=hanoi\n")
    rc, sender = run(env)
    assert rc == 2 and sender.sent == [] and env.jobs.calls == 0
    assert "hanoi" in capsys.readouterr().err


def test_dry_run_respects_job_areas(env, capsys):
    (env.root / ".env").write_text("JOB_AREAS=danang\n")
    env.jobs.items = [job(1), hcm_job(2)]
    assert run(env, "--dry-run")[0] == 0
    out = capsys.readouterr().out
    assert "Python Intern 001" in out and "Python Intern 002" not in out
    assert "Remote" not in out and "other cities" not in out


def test_first_run_after_boot_ignores_three_hour_guard(env):
    init(env, "jobs", "contests")
    state(env).record_scan(NOW - timedelta(hours=1))  # scanned before the laptop was shut down
    run(env, booted=NOW - timedelta(minutes=2))
    assert env.jobs.calls == 1 and state(env).last_scan() == NOW


def test_guard_applies_again_after_scan_since_boot(env):
    init(env, "jobs", "contests")
    state(env).record_scan(NOW - timedelta(hours=1))  # already scanned since this boot
    run(env, booted=NOW - timedelta(hours=2))
    assert env.jobs.calls == 0


def test_boot_time_reads_proc_stat():
    b = fm.boot_time()
    assert b is None or (b.tzinfo is not None and b <= datetime.now(timezone.utc))
