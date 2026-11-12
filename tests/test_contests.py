import json
from datetime import date
from pathlib import Path

import pytest

from finder import contest_filters as cf
from finder.models import Contest
from finder.sources import devpost, luma, mlh

TODAY = date(2026, 11, 9)
F = Path(__file__).parent / "fixtures" / "contests"


def c(name="AI Hackathon", mode="online", topic="AI", **kw):
    d = dict(name=name, organiser="Org", mode=mode, location="Online",
             url="https://x.test/1", source="S", topic=topic)
    d.update(kw)
    return Contest(**d)


def test_global_online_rejected_even_with_topic():
    x = c()
    assert cf.is_global(x) and not cf.accept(x, TODAY)


def test_vietnam_online_with_topic_accepted():
    assert cf.accept(c(vietnam_open=True), TODAY)
    assert not cf.accept(c(vietnam_open=True, topic=""), TODAY)


def test_hanoi_hcmc_need_topic():
    assert cf.accept(c(mode="vietnam", topic="Fintech"), TODAY)
    assert not cf.accept(c(mode="vietnam", topic=""), TODAY)


def test_non_contest_event_rejected():
    assert not cf.accept(c(mode="da nang", is_contest=False), TODAY)


def test_online_without_topic_rejected():
    assert not cf.accept(c(topic=""), TODAY)


def test_vietnam_online_not_global():
    assert not cf.is_global(c(vietnam_open=True))


def test_da_nang_in_person_accepted_even_without_topic():
    assert cf.accept(c(mode="da nang", topic=""), TODAY)


def test_in_person_elsewhere_rejected():
    assert not cf.accept(c(mode="other"), TODAY)


def test_finished_or_closed_rejected():
    assert not cf.accept(c(ended=date(2026, 11, 1)), TODAY)
    assert not cf.accept(c(reg_deadline=date(2026, 11, 8)), TODAY)
    assert not cf.accept(c(closed=True), TODAY)


def test_unsafe_url_rejected():
    assert not cf.accept(c(url="javascript:alert(1)"), TODAY)


def test_classify_mode():
    assert cf.classify_mode("Online", False) == "online"
    assert cf.classify_mode("Da Nang, Vietnam", False) == "da nang"
    assert cf.classify_mode("Atlanta, GA", False) == "other"
    assert cf.classify_mode("Atlanta, GA", True) == "online"
    assert cf.classify_mode("Thanh Xuân, Hà Nội, Vietnam", False) == "vietnam"
    assert cf.classify_mode("Thành phố Hồ Chí Minh, Vietnam", False) == "vietnam"


@pytest.mark.parametrize("name,topic", [
    ("PayPal AI Hackathon", "AI"), ("LLM Agents Challenge", "AI"),
    ("Blockchain Buildathon", "Blockchain"), ("Cloud Run Hackathon", "Cloud"),
    ("Art Contest", ""),
])
def test_topic(name, topic):
    assert cf.detect_topic(name) == topic


def test_devpost_theme_mapping():
    assert cf.detect_topic("Some Event", ["Blockchain", "Open Ended"]) == "Blockchain"


def test_select_dedups_and_sorts_da_nang_first():
    out = cf.select([c("A", vietnam_open=True), c("A", vietnam_open=True),
                     c("C", mode="vietnam"), c("B", mode="da nang")], TODAY)
    assert [x.name for x in out] == ["B", "C", "A"]


def test_luma_parse_keeps_all_events_and_flags_contests():
    data = {"entries": [
        {"calendar": {"name": "Codex"}, "event": {
            "name": "Codex Community Hackathon - Hanoi", "url": "l0ro71hq",
            "location_type": "offline", "start_at": "2026-11-14T02:00:00.000Z",
            "end_at": "2026-11-14T12:00:00.000Z",
            "geo_address_info": {"region": "Hà Nội", "country": "Vietnam",
                                 "full_address": "79 Ngụy Như Kon Tum, Thanh Xuân, Hà Nội"}}},
        {"calendar": {"name": "FES"}, "event": {
            "name": "ĐÀ NẴNG | Vòng Bán Kết FPT Tích Tịch Tình Tang 2026", "url": "f6nae1v7",
            "location_type": "offline", "start_at": "2026-11-29T01:00:00.000Z",
            "geo_address_info": {"region": "Đà Nẵng", "full_address": "Ngũ Hành Sơn, Đà Nẵng"}}},
        {"event": {"name": "Sake Mahjong Night", "url": "a1swbrsj", "location_type": "offline",
                   "geo_address_info": {"region": "Hồ Chí Minh"}}},
        {"event": {"name": "No link Hackathon"}},
    ]}
    items = luma.parse(data)
    assert [(i.mode, i.topic, i.is_contest) for i in items] == [
        ("vietnam", "AI", True), ("da nang", "", True), ("vietnam", "", False)]
    assert items[0].url == "https://luma.com/l0ro71hq" and items[0].ended == date(2026, 11, 14)
    assert [i.name for i in cf.select(items, TODAY)] == [items[1].name, items[0].name]


@pytest.mark.parametrize("text,end", [
    ("Oct 01 - Nov 12, 2026", date(2026, 11, 12)),
    ("Nov 08 - 15, 2026", date(2026, 11, 15)),
    ("Jul 16, 2026 - Jan 15, 2027", date(2027, 1, 15)),
    ("garbage", None),
])
def test_devpost_dates(text, end):
    assert devpost.parse_end_date(text) == end


def test_devpost_parse_synthetic():
    data = {"hackathons": [{"title": "X AI Hack", "organization_name": "Org", "open_state": "open",
                            "displayed_location": {"location": "Online"},
                            "themes": [{"name": "Machine Learning/AI"}], "url": "https://x.devpost.com/",
                            "submission_period_dates": "Oct 01 - Nov 12, 2026"}]}
    x = devpost.parse(data)[0]
    assert (x.mode, x.topic, x.ended) == ("online", "AI", date(2026, 11, 12))


def test_devpost_fixture():
    p = F / "devpost.txt"
    if not p.exists():
        pytest.skip("fixture missing")
    items = devpost.parse(json.loads(p.read_text()))
    assert items and all(i.url.startswith("http") for i in items)


def test_mlh_synthetic_digital_and_physical():
    page = {"props": {"upcomingEvents": [
        {"name": "Cloud Hack", "formatType": "digital", "location": "", "websiteUrl": "https://h.test/",
         "endsAt": "2026-12-01T00:00:00Z", "dateRange": "NOV 30 - DEC 1"},
        {"name": "Emory Hacks", "formatType": "physical", "location": "Atlanta, GA",
         "websiteUrl": "https://e.test/", "endsAt": "2026-11-15T00:00:00Z"}]}}
    html = f'<script data-page="app" type="application/json">{json.dumps(page)}</script>'
    items = mlh.parse(html)
    assert [i.mode for i in items] == ["online", "other"]
    assert cf.select(items, TODAY) == []     # global online and abroad: both dropped


def test_mlh_fixture():
    p = F / "mlh.txt"
    if not p.exists():
        pytest.skip("fixture missing")
    assert mlh.parse(p.read_text())
