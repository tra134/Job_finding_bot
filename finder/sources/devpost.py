import re
from datetime import date, datetime

from ..contest_filters import VIETNAM, classify_mode, detect_topic
from ..filters import fold
from ..models import Contest

NAME = "Devpost"
API = "https://devpost.com/api/hackathons?status[]=open&challenge_type[]=online&page={}"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_end_date(text):
    """'Oct 01 - Nov 12, 2026' -> 2026-11-12; 'Nov 08 - 15, 2026' -> 2026-11-15."""
    m = re.search(r"(?:([A-Za-z]{3})[a-z]*\s+)?(\d{1,2}),\s*(\d{4})\s*$", text or "")
    if not m:
        return None
    mon = m.group(1)
    if not mon:
        # month omitted on the last part, so it equals the first month in the range
        first = re.match(r"\s*([A-Za-z]{3})", text)
        mon = first.group(1) if first else None
    mon = MONTHS.get((mon or "").lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(2)))
    except ValueError:
        return None


def parse(data):
    out = []
    for h in data.get("hackathons", []):
        loc = (h.get("displayed_location") or {}).get("location", "")
        themes = [t.get("name", "") for t in h.get("themes") or [] if isinstance(t, dict)]
        dates = h.get("submission_period_dates", "")
        end = parse_end_date(dates)
        text = f"{h.get('title', '')} {loc}"
        out.append(Contest(
            name=h.get("title", ""), organiser=h.get("organization_name", "") or "",
            mode=classify_mode(loc, False), location=loc, url=h.get("url", ""), source=NAME,
            topic=detect_topic(h.get("title", ""), themes), reg_deadline=end,
            event_date=dates, ended=end, vietnam_open=bool(VIETNAM.search(fold(text))),
            closed=h.get("open_state") not in (None, "open")))
    return out


def fetch(client):
    out, page = [], 1
    while page <= 8:
        data = client.get(API.format(page)).json()
        found = parse(data)
        out += found
        total = data.get("meta", {}).get("total_count", 0)
        per = data.get("meta", {}).get("per_page", 9) or 9
        if not found or page * per >= total:
            break
        page += 1
    return out
