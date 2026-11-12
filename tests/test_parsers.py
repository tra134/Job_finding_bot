"""Parser tests run against saved pages in tests/fixtures/ (kept out of git).
They are skipped when a fixture is missing."""
import json
from datetime import date
from pathlib import Path

import pytest

from finder.sources import careerviet, itviec, topcv, vietnamworks

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


class _VWClient:
    """Fails the first search request, answers the rest with one posting."""
    def __init__(self, fail_all=False, blocked=False):
        self.calls, self.fail_all, self.blocked = 0, fail_all, blocked

    def post_json(self, url, payload):
        from finder.http_client import BlockedError, FetchError
        self.calls += 1
        if self.blocked:
            raise BlockedError("403")
        if self.fail_all or self.calls == 1:
            raise FetchError("timeout")
        hit = {"jobTitle": f"Intern {payload['query']}", "companyName": "Co",
               "jobUrl": "https://www.vietnamworks.com/x", "approvedOn": "2026-11-01"}
        return type("R", (), {"json": lambda self: {"data": [hit], "meta": {"nbPages": 1}}})()


def test_vietnamworks_keeps_results_when_one_search_fails():
    jobs = vietnamworks.fetch(_VWClient())
    assert [j.title for j in jobs] == ["Intern intern", "Intern thuc tap"]


def test_vietnamworks_raises_when_every_search_fails():
    from finder.http_client import BlockedError, FetchError
    with pytest.raises(FetchError):
        vietnamworks.fetch(_VWClient(fail_all=True))
    with pytest.raises(BlockedError):
        vietnamworks.fetch(_VWClient(blocked=True))


def test_vietnamworks_details_from_requirements_and_skills():
    data = {"data": [{"jobTitle": "Fresher Java", "jobUrl": "https://www.vietnamworks.com/x",
                      "approvedOn": "2026-11-01", "jobRequirement": "<p>Tiếng Nhật N3 &amp; Java</p>",
                      "skills": [{"skillName": "English"}]}]}
    data["data"][0]["yearsOfExperience"] = 0
    j = vietnamworks.parse(data)[0]
    assert "Tiếng Nhật N3 & Java" in j.details and "English" in j.details
    assert j.experience == "no experience"
