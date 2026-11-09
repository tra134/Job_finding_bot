import re
from datetime import date, datetime

BASE = {}


def text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_dmy(s):
    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_iso(s):
    try:
        return datetime.fromisoformat(s).date()
    except (TypeError, ValueError):
        return None


def abs_url(base, href):
    from urllib.parse import urljoin
    return urljoin(base, href or "")
