from ..models import Job
from .common import parse_iso

NAME = "VietnamWorks"
URL = "https://ms.vietnamworks.com/job-search/v1.0/search"
DA_NANG_CITY = "17"


def parse(data):
    jobs = []
    for h in data.get("data", []):
        # contactName / emailAddress are deliberately never read.
        locs = ", ".join(l.get("cityNameVI", "") for l in h.get("workingLocations") or []
                         if isinstance(l, dict))
        jobs.append(Job(
            title=h.get("jobTitle", ""), company=h.get("companyName", ""), location=locs,
            url=h.get("jobUrl", ""), source=NAME, salary=h.get("prettySalary", "") or "",
            posted=h.get("approvedOn", "")[:10], deadline=parse_iso(h.get("expiredOn")),
            level=h.get("jobLevel", "") or ""))
    return jobs


def _search(client, query, city, max_pages):
    jobs, page = [], 0
    while page < max_pages:
        flt = [{"field": "workingLocations.cityId", "value": city}] if city else []
        data = client.post_json(URL, {"query": query, "hitsPerPage": 50, "page": page,
                                      "filter": flt, "ranges": [], "order": []}).json()
        jobs += parse(data)
        page += 1
        if page >= data.get("meta", {}).get("nbPages", 0):
            break
    return jobs


def fetch(client):
    jobs = _search(client, "", DA_NANG_CITY, 4)
    jobs += _search(client, "intern", None, 2)
    jobs += _search(client, "thuc tap", None, 2)
    return jobs
