"""Parser tests run against saved pages in tests/fixtures/ (kept out of git).
They are skipped when a fixture is missing."""
import json
from datetime import date
from pathlib import Path

import pytest

from finder.sources import careerlink, careerviet, itviec, topcv, vietnamworks

F = Path(__file__).parent / "fixtures"


def need(name):
    p = F / name
    if not p.exists():
        pytest.skip(f"fixture {name} not present")
    return p.read_text()


def basic(jobs):
    assert jobs
    for j in jobs:
        assert j.title and j.url.startswith("http") and j.source


def test_vietnamworks():
    jobs = vietnamworks.parse(json.loads(need("vw.json")))
    basic(jobs)
    assert all(isinstance(j.deadline, (date, type(None))) for j in jobs)
    assert not any("@" in repr(j) for j in jobs)    # no recruiter email kept


def test_vietnamworks_discards_contact_data():
    data = {"data": [{"jobTitle": "T", "jobUrl": "https://v.test/1", "companyName": "C",
                      "contactName": "Jane Recruiter", "emailAddress": "jane@x.test",
                      "workingLocations": [{"cityNameVI": "Đà Nẵng"}]}]}
    j = vietnamworks.parse(data)[0]
    assert "Jane" not in repr(j) and "jane@" not in repr(j)
    assert j.location == "Đà Nẵng"


def test_topcv():
    jobs = topcv.parse(need("topcv.html"))
    basic(jobs)
    assert topcv.total_pages(need("topcv.html")) >= 1


def test_itviec():
    jobs = itviec.parse(need("itviec_all.html"))
    basic(jobs)
    assert all(j.company for j in jobs)


def test_careerviet_maps_time_to_deadline():
    jobs = careerviet.parse(need("careerviet.html"))
    basic(jobs)
    assert jobs[0].deadline == date(2026, 12, 1)
    assert jobs[0].posted == ""


def test_careerlink_separates_location_and_salary():
    jobs = careerlink.parse(need("careerlink.html"))
    basic(jobs)
    for j in jobs:
        assert "Cập nhật" not in j.location
        assert "Thực tập" not in j.salary and "Sinh viên" not in j.salary
    assert any("Thực tập" in j.level or "Sinh viên" in j.level for j in jobs)
