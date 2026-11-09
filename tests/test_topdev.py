import json
from datetime import date
from pathlib import Path

import pytest

from finder.sources import topdev

F = Path(__file__).parent / "fixtures"


def job(**kw):
    d = {"title": "Backend Intern", "detail_url": "https://topdev.vn/detail-jobs/x-1?src=a",
         "company": {"display_name": "Acme"},
         "addresses": {"address_region_list": "Da Nang"},
         "salary": {"value": "Negotiable"}, "published": {"date": "01-11-2026"},
         "expires": {"date": "11-11-2026"}}
    d.update(kw)
    return d


def test_parse_synthetic_and_company_reference():
    flight = ("9:T5,hello7:" + json.dumps({"jobs": [job(company="$5:0:company"),
                                                    job(detail_url="javascript:x")]})
              + "\n5:" + json.dumps([{"company": {"display_name": "RefCo"}}]))
    html = "<script>self.__next_f.push([1,%s])</script>" % json.dumps(flight)
    jobs = topdev.parse(html)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "RefCo" and j.url == "https://topdev.vn/detail-jobs/x-1"
    assert j.salary == "" and j.deadline == date(2026, 11, 11) and j.source == topdev.NAME


def test_parse_empty():
    assert topdev.parse("<html></html>") == []


def test_parse_fixture():
    p = F / "topdev.html"
    if not p.exists():
        pytest.skip("fixture topdev.html not present")
    jobs = topdev.parse(p.read_text())
    assert jobs
    for j in jobs:
        assert j.title and j.url.startswith("https://") and j.source == topdev.NAME
