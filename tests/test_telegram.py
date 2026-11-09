import re

import pytest
import requests

from finder import telegram as tg
from finder.models import Contest, Job
from finder.telegram import Block, Message, TelegramError, TelegramSender

TOKEN = "123456:SECRET-token_xyz"


def job(i=0, title="Intern Dev", url=None, loc="Da Nang", **kw):
    return Job(title=title + str(i), company="Co", location=loc,
               url=url if url is not None else f"https://x.test/{i}", source="s", **kw)


def key(x):
    return getattr(x, "title", None) or x.name


class Resp:
    def __init__(self, status=200, data=None, raises=False):
        self.status_code, self.data, self.raises = status, data if data is not None else {"ok": True}, raises

    def json(self):
        if self.raises:
            raise ValueError("bad")
        return self.data


class Session:
    def __init__(self, *items):
        self.items, self.calls = list(items), []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        it = self.items.pop(0) if self.items else Resp()
        if isinstance(it, Exception):
            raise it
        return it


class Clock:
    def __init__(self):
        self.t = 100.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def sender(*items):
    c = Clock()
    return TelegramSender(TOKEN, Session(*items), sleep=c.sleep, clock=c.now), c


def test_esc():
    assert tg.esc('<a>&"x"') == "&lt;a&gt;&amp;&quot;x&quot;"
    assert tg.esc(None) == ""


def test_render_escapes_text_and_href():
    j = job(title="<i>X</i> & ", url='https://x.test/?a="1"&b=<2>')
    out = tg.render_jobs({1: [j], 2: [], 3: []}, key)
    text = "\n".join(b.text for b in out)
    assert "<i>" not in text
    assert "&lt;i&gt;X&lt;/i&gt; &amp;" in text
    assert 'href="https://x.test/?a=&quot;1&quot;&amp;b=&lt;2&gt;"' in text


def test_contest_escape_and_labels():
    c = Contest(name="<i>Hack</i>", organiser="A&B", mode="online", location="", url='https://d.test/?q="',
                source="devpost", topic="AI")
    out = tg.render_contests([c], key)
    text = "\n".join(b.text for b in out)
    assert "&lt;i&gt;Hack&lt;/i&gt;" in text and "A&amp;B" in text and "<i>" not in text
    assert "deadline (end of submission period): unknown" in text and "event: unknown" in text
    assert 'href="https://d.test/?q=&quot;"' in text
    assert out[1].keys == ["<i>Hack</i>"] and not out[0].keys and not out[-1].keys


def test_unsafe_urls_dropped():
    bad = [job(1, url="javascript:alert(1)"), job(2, url=""), job(3, url="ftp://x/y")]
    assert tg.render_jobs({1: bad, 2: [], 3: []}, key) == []
    assert tg.render_jobs({1: [], 2: [], 3: []}, key) == []
    good = job(4)
    out = tg.render_jobs({1: bad + [good], 2: [], 3: []}, key)
    assert [k for b in out for k in b.keys] == [good.title]
    c = Contest(name="n", organiser="", mode="online", location="", url="javascript:x", source="s")
    assert tg.render_contests([c], key) == []


def test_tiers_order_and_footer():
    g = {1: [job(1)], 2: [job(2, loc="Remote")], 3: [job(3, loc="Hanoi")]}
    out = tg.render_jobs(g, key)
    heads = [b.text for b in out if not b.keys][:3]
    assert "📍" in heads[0] and "🏠" in heads[1] and "🏙️" in heads[2]
    assert not out[-1].keys and "facebook.com" in out[-1].text and "linkedin.com" in out[-1].text
    g2 = tg.render_jobs({1: [], 2: [job(2)], 3: []}, key)
    assert "📍" not in g2[0].text and "🏠" in g2[0].text


def test_tier3_cap_keys():
    jobs = [job(i, loc="Hanoi") for i in range(14)]
    out = tg.render_jobs({1: [], 2: [], 3: jobs}, key)
    assert [k for b in out for k in b.keys] == [j.title for j in jobs[:10]]
    assert any(b.text == "+4 more" and not b.keys for b in out)


def test_split_below_limit_and_no_item_broken():
    blocks = [Block(f"<b>item{i}</b>" + "x" * 90, [f"k{i}"]) for i in range(60)]
    msgs = tg.split_blocks(blocks, limit=500)
    assert len(msgs) > 1 and all(len(m.text) <= 500 for m in msgs)
    for m in msgs:
        for k in m.keys:
            assert f"<b>item{k[1:]}</b>" in m.text
    assert [k for m in msgs for k in m.keys] == [f"k{i}" for i in range(60)]
    assert "\n\n".join(m.text for m in msgs).count("</b>") == 60


def test_split_oversized_block_truncated_safely():
    b = Block("<b>" + "a&amp;" * 200 + '</b> <a href="https://x.test/' + "z" * 300 + '">l</a>', ["k"])
    [m] = tg.split_blocks([b], limit=100)
    assert len(m.text) <= 100 and m.keys == ["k"]
    assert m.text.count("<b>") == m.text.count("</b>")
    assert not re.search(r"<[^>]*$", m.text) and not re.search(r"&[a-z]*$", m.text)
    b = Block('x<a href="https://x.test/' + "z" * 300 + '">label</a>', ["k"])
    [m] = tg.split_blocks([b], limit=60)
    assert len(m.text) <= 60 and m.text.count("<a ") == m.text.count("</a>")
    assert tg.split_blocks([]) == []


def test_split_keys_stay_with_text():
    msgs = tg.split_blocks([Block("a" * 60, ["1"]), Block("b" * 60, ["2"])], limit=100)
    assert [(m.text[0], m.keys) for m in msgs] == [("a", ["1"]), ("b", ["2"])]


def test_summary_and_warning_escape():
    assert "7" in tg.first_run_summary("jobs", 7)
    w = tg.source_warning("itviec", "error", "<script>&")
    assert "&lt;script&gt;&amp;" in w and "<script>" not in w


def test_send_payload():
    s, _ = sender()
    s.send("-100", "hi")
    url, payload, timeout = s._session.calls[0]
    assert url.endswith("/sendMessage") and timeout
    assert payload["parse_mode"] == "HTML" and payload["disable_web_page_preview"] is True
    assert payload["chat_id"] == "-100" and payload["text"] == "hi"


def test_throttle_one_per_second():
    s, c = sender()
    s.send("c", "a")
    assert c.sleeps == []
    s.send("c", "b")
    assert c.sleeps == [pytest.approx(1.0)]
    c.t += 5
    s.send("c", "c")
    assert len(c.sleeps) == 1


def test_retry_after_honoured():
    s, c = sender(Resp(429, {"ok": False, "parameters": {"retry_after": 7}}), Resp())
    s.send("c", "a")
    assert 7 in c.sleeps and len(s._session.calls) == 2


def test_retry_bounded_and_long_wait_refused():
    def r():
        return Resp(429, {"ok": False, "parameters": {"retry_after": 1}})
    s, _ = sender(r(), r(), r(), r(), r())
    with pytest.raises(TelegramError):
        s.send("c", "a")
    assert len(s._session.calls) == tg.MAX_RETRIES + 1
    s, c = sender(Resp(429, {"ok": False, "parameters": {"retry_after": 99999}}))
    with pytest.raises(TelegramError):
        s.send("c", "a")
    assert 99999 not in c.sleeps


def test_error_never_contains_token():
    s, _ = sender(requests.ConnectionError(f"HTTPSConnectionPool url=/bot{TOKEN}/sendMessage failed"))
    with pytest.raises(TelegramError) as e:
        s.send("c", "a")
    assert TOKEN not in str(e.value) and "SECRET" not in repr(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    s, _ = sender(Resp(400, {"ok": False, "description": f"bad {TOKEN}"}))
    with pytest.raises(TelegramError) as e:
        s.send("c", "a")
    assert TOKEN not in str(e.value) and "400" in str(e.value)
    s, _ = sender(Resp(500, raises=True))
    with pytest.raises(TelegramError) as e:
        s.send("c", "a")
    assert TOKEN not in str(e.value)


class FakeSender:
    def __init__(self, fail_at=None):
        self.sent, self.fail_at = [], fail_at

    def send(self, chat, text):
        if self.fail_at is not None and len(self.sent) == self.fail_at:
            raise TelegramError("boom")
        self.sent.append(text)


def test_send_digest_marks_after_confirmation_and_stops_at_failure():
    msgs = [Message("a", ["k1"]), Message("b", ["k2"]), Message("c", ["k3"])]
    marked = []
    fs = FakeSender(fail_at=1)
    with pytest.raises(TelegramError):
        tg.send_digest(fs, "c", msgs, marked.extend)
    assert fs.sent == ["a"] and marked == ["k1"]
    marked.clear()
    assert tg.send_digest(FakeSender(), "c", msgs, marked.extend) == 3
    assert marked == ["k1", "k2", "k3"]


def test_failed_send_retry_and_overcap_never_marked():
    jobs = [job(i, loc="Hanoi") for i in range(13)]
    msgs = tg.split_blocks(tg.render_jobs({1: [], 2: [], 3: jobs}, key), limit=600)
    assert len(msgs) >= 3
    seen = set()
    with pytest.raises(TelegramError):
        tg.send_digest(FakeSender(fail_at=1), "c", msgs, seen.update)
    assert seen == set(msgs[0].keys)
    seen.clear()
    tg.send_digest(FakeSender(), "c", msgs, seen.update)
    assert seen == {j.title for j in jobs[:10]}
