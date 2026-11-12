"""Luma (lu.ma) public discover feed: events near Da Nang, Hanoi and Ho Chi Minh City.

Luma lists every kind of meetup. All events are returned (so a quiet week is not
"empty"), with is_contest set only for contest-like names (hackathon, challenge,
cuộc thi, semi-final...); contest_filters drops the rest.
"""
from ..contest_filters import CONTEST_WORDS, classify_mode, detect_topic
from ..filters import fold
from ..http_client import BlockedError, FetchError
from ..models import Contest
from .common import parse_iso

NAME = "Luma"
API = ("https://api.lu.ma/discover/get-paginated-events"
       "?latitude={lat}&longitude={lon}&pagination_limit=50")
EVENT_URL = "https://luma.com/{}"
CITIES = {  # Da Nang first: it is the main target
    "Da Nang": (16.054, 108.202),
    "Hanoi": (21.028, 105.854),
    "Ho Chi Minh City": (10.776, 106.700),
}


def _place(geo):
    geo = geo or {}
    return ", ".join(p for p in (geo.get("region") or geo.get("city_state") or "",
                                 geo.get("country") or "") if p)


def parse(data):
    out = []
    for x in data.get("entries", []):
        e = x.get("event") or {}
        name = e.get("name") or ""
        if not e.get("url"):
            continue
        geo = e.get("geo_address_info") or {}
        where = f"{geo.get('full_address') or ''} {geo.get('region') or ''}"
        online = e.get("location_type") == "online"
        start = (e.get("start_at") or "")[:10]
        out.append(Contest(
            name=name, organiser=(x.get("calendar") or {}).get("name") or "",
            mode=classify_mode(where, online), location=_place(geo) or "online",
            url=EVENT_URL.format(e["url"]), source=NAME, topic=detect_topic(name),
            event_date=start, ended=parse_iso((e.get("end_at") or "")[:10]),
            vietnam_open=True, is_contest=bool(CONTEST_WORDS.search(fold(name)))))
    return out


def fetch(client):
    """One request per city; one failed city should not lose the others."""
    out, errors = [], []
    for lat, lon in CITIES.values():
        try:
            out += parse(client.get(API.format(lat=lat, lon=lon)).json())
        except BlockedError:
            raise
        except FetchError as e:
            errors.append(e)
    if errors and len(errors) == len(CITIES):
        raise errors[0]
    return out
