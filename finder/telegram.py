"""Telegram digests: HTML rendering, message splitting and sending."""
import re
import time
from dataclasses import dataclass, field

import requests

from . import contest_digest, digest
from .contest_filters import MODE_LABEL, is_global
from .filters import is_multi_city, job_langs, safe_url

API = "https://api.telegram.org/bot{}/sendMessage"
LIMIT = 4000
TIMEOUT = 20
MAX_RETRIES = 3
MAX_RETRY_AFTER = 120


class TelegramError(Exception):
    pass


@dataclass
class Block:
    text: str
    keys: list = field(default_factory=list)


@dataclass
class Message:
    text: str
    keys: list = field(default_factory=list)


def esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _link(label, url):
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def _footer(links):
    return Block("Search yourself:\n" + "\n".join(_link(n, u) for n, u in links if safe_url(u)))


def _job(j):
    tag = " (multi-city)" if is_multi_city(j) else ""
    langs = job_langs(j)
    lang = f"🗣 {esc(', '.join(langs))}\n" if langs else ""
    return (f"<b>{esc(j.title)}</b>\n{esc(j.company)} | {esc((j.location or 'location unknown') + tag)}\n"
            f"{esc(j.salary or 'salary n/a')} | {esc('/'.join(j.sources))}\n{lang}{_link('Open', j.url)}")


def _contest(c):
    flag = "🌍 " if is_global(c) else ""
    fmt = MODE_LABEL.get(c.mode, c.mode)
    deadline = c.reg_deadline.isoformat() if c.reg_deadline else "unknown"
    return (f"{flag}<b>{esc(c.name)}</b>\n{esc(c.organiser or 'organiser unknown')} | {fmt} | "
            f"topic: {esc(c.topic or 'unknown')}\n"
            f"deadline (end of submission period): {esc(deadline)} | event: {esc(c.event_date or 'unknown')}"
            f" | {esc(c.source)}\n{_link('Open', c.url)}")


def render_jobs(groups, key_fn):
    out = []
    for t in (1, 2, 3):
        jobs = [j for j in groups.get(t, []) if safe_url(j.url)]
        if not jobs:
            continue
        shown = jobs[:digest.OTHER_CAP] if t == 3 else jobs
        out.append(Block(f"<b>{esc(digest.TIER_TITLES[t])} ({len(jobs)})</b>"))
        out += [Block(_job(j), [key_fn(j)]) for j in shown]
        if len(jobs) > len(shown):
            out.append(Block(f"+{len(jobs) - len(shown)} more"))
    return out + [_footer(digest.search_links())] if out else []


def render_contests(contests, key_fn):
    items = [c for c in contests if safe_url(c.url)]
    if not items:
        return []
    out = [Block(f"<b>Contests ({len(items)})</b>")]
    out += [Block(_contest(c), [key_fn(c)]) for c in items]
    return out + [_footer(contest_digest.search_links())]


def _trim(text):
    text = re.sub(r"<[^>]*$", "", text)
    return re.sub(r"&[a-z]*;?$", "", text)


def _closers(text):
    stack = []
    for m in re.finditer(r"<(/?)(\w+)[^>]*>", text):
        if not m.group(1):
            stack.append(m.group(2))
        elif stack and stack[-1] == m.group(2):
            stack.pop()
    return "".join(f"</{t}>" for t in reversed(stack))


def _truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = _trim(text[:limit - 1])
    while len(cut) + len(_closers(cut)) > limit - 1:
        cut = _trim(cut[:limit - 1 - len(_closers(cut))])
    return cut + _closers(cut) + "…"


def split_blocks(blocks, limit=4000):
    msgs, cur, keys = [], "", []
    for b in blocks:
        text = _truncate(b.text, limit)
        if cur and len(cur) + 2 + len(text) > limit:
            msgs.append(Message(cur, keys))
            cur, keys = "", []
        cur = cur + "\n\n" + text if cur else text
        keys = keys + list(b.keys)
    if cur:
        msgs.append(Message(cur, keys))
    return msgs


def first_run_summary(channel, count):
    return (f"First run: found {int(count)} {esc(channel)} items. They are recorded as already seen "
            "and will not be listed one by one; you will be notified only about new ones.")


def source_warning(name, status, detail):
    return f"Source <b>{esc(name)}</b> status: <b>{esc(status)}</b>\n{esc(detail)}"


class TelegramSender:
    def __init__(self, token, session=None, sleep=time.sleep, clock=time.monotonic):
        self._token = token
        self._session = session or requests
        self._sleep = sleep
        self._clock = clock
        self._last = None

    def _clean(self, text):
        text = str(text)
        return text.replace(self._token, "***") if self._token else text

    def _throttle(self):
        if self._last is not None:
            wait = 1.0 - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)

    def send(self, chat_id, html_text):
        payload = {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self._session.post(API.format(self._token), json=payload, timeout=TIMEOUT)
            except Exception as e:
                self._last = self._clock()
                raise TelegramError(f"Telegram request failed ({type(e).__name__})") from None
            self._last = self._clock()
            try:
                data = resp.json()
            except Exception:
                data = {}
            if resp.status_code == 200 and data.get("ok"):
                return
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                wait = (data.get("parameters") or {}).get("retry_after", 1)
                if not isinstance(wait, (int, float)) or wait > MAX_RETRY_AFTER:
                    raise TelegramError("Telegram rate limit: retry_after too long")
                self._sleep(wait)
                self._last = None
                continue
            desc = self._clean(data.get("description", ""))[:200] if isinstance(data, dict) else ""
            raise TelegramError(f"Telegram HTTP {resp.status_code}: {desc}".rstrip(": "))


def send_digest(sender, chat_id, messages, on_delivered):
    done = 0
    for m in messages:
        sender.send(chat_id, m.text)
        on_delivered(m.keys)
        done += 1
    return done
