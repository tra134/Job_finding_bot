"""Seen items, last-scan time and source health, kept in one JSON file."""
import fcntl
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from finder.filters import fold
from finder.models import Contest

EMPTY_THRESHOLD = 3
CHANNELS = ("jobs", "contests")


class StateError(Exception):
    """Corrupt state file: do not silently reset it."""


class LockHeld(Exception):
    pass


def _bare_url(url):
    p = urlsplit((url or "").strip())
    return f"{p.scheme}://{p.netloc}{p.path}".lower().rstrip("/")


def item_key(item):
    if isinstance(item, Contest):
        a, b = item.name, item.organiser
    else:
        a, b = item.title, item.company
    if not fold(b):
        return fold(a) + "|" + _bare_url(item.url)
    return fold(a) + "|" + fold(b)


def _empty():
    return {"channels": {c: {"initialized": False, "seen": []} for c in CHANNELS},
            "last_scan": None, "sources": {}}


class State:
    def __init__(self, path):
        self.path = path
        self.data = _empty()
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("not an object")
                for k, v in loaded.items():
                    self.data[k] = v
                for c in CHANNELS:
                    ch = self.data["channels"].setdefault(c, {})
                    ch.setdefault("initialized", False)
                    ch.setdefault("seen", [])
                if not isinstance(self.data["sources"], dict):
                    raise ValueError("bad sources")
                self._seen = {c: set(self.data["channels"][c]["seen"]) for c in CHANNELS}
                if self.data["last_scan"] is not None:
                    self.last_scan()
            except (ValueError, TypeError, AttributeError, OSError) as e:
                raise StateError(f"cannot read state file {path}: {e}") from None
        else:
            self._seen = {c: set() for c in CHANNELS}

    def _save(self):
        for c in CHANNELS:
            self.data["channels"][c]["seen"] = sorted(self._seen[c])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def is_initialized(self, channel):
        return bool(self.data["channels"][channel]["initialized"])

    def mark_initialized(self, channel):
        self.data["channels"][channel]["initialized"] = True
        self._save()

    def is_seen(self, channel, key):
        return key in self._seen[channel]

    def mark_seen(self, channel, keys):
        self._seen[channel].update(keys)
        self._save()

    def last_scan(self):
        raw = self.data["last_scan"]
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            raise StateError("bad last_scan value") from None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    def record_scan(self, when):
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self.data["last_scan"] = when.astimezone(timezone.utc).isoformat()
        self._save()

    def scan_due(self, now, min_hours=3):
        last = self.last_scan()
        return last is None or now - last >= timedelta(hours=min_hours)

    def update_source(self, name, status):
        if status == "skipped":
            return False
        s = self.data["sources"].setdefault(
            name, {"failing": False, "warned": False, "empties": 0})
        if status == "ok":
            s.update(failing=False, warned=False, empties=0)
        elif status == "empty":
            s["empties"] += 1
            if s["empties"] >= EMPTY_THRESHOLD:
                s["failing"] = True
        elif status in ("blocked", "error"):
            s["empties"] = 0
            s["failing"] = True
        else:
            return False
        self._save()
        return s["failing"] and not s["warned"]

    def mark_warned(self, name):
        s = self.data["sources"].get(name)
        if s is not None:
            s["warned"] = True
            self._save()


class RunLock:
    def __init__(self, path):
        self.path = path
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise LockHeld(f"another run holds {self.path}") from None
        self.fd = fd
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        self.fd = None
