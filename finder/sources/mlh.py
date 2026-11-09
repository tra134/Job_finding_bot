import json
from datetime import datetime

from bs4 import BeautifulSoup

from ..contest_filters import VIETNAM, classify_mode, detect_topic
from ..filters import fold
from ..models import Contest

NAME = "MLH"
URL = "https://mlh.io/seasons/2027/events"   # redirects to mlh.com (approved host)


def _date(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("script[data-page]")
    if not el or not el.string:
        return []
    events = json.loads(el.string).get("props", {}).get("upcomingEvents", [])
    out = []
    for e in events:
        loc = (e.get("location") or "").strip()
        fmt = fold(e.get("formatType", ""))
        online = fmt in ("digital", "virtual", "online")
        focus = (e.get("customFields") or {}).get("hackathon_focus") or []
        end = _date(e.get("endsAt"))
        out.append(Contest(
            name=e.get("name", ""), organiser=e.get("organizationName") or "Major League Hacking",
            mode=classify_mode(loc, online), location=loc or fmt,
            url=e.get("websiteUrl") or "", source=NAME,
            topic=detect_topic(e.get("name", ""), focus), event_date=e.get("dateRange", ""),
            ended=end, vietnam_open=bool(VIETNAM.search(fold(loc)))))
    return out


def fetch(client):
    return parse(client.get(URL).text)
