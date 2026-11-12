from ..http_client import BlockedError, FetchError
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


SEARCHES = [("", DA_NANG_CITY, 4), ("intern", None, 2), ("thuc tap", None, 2)]


def fetch(client):
    """Run every search; one timed-out search should not throw away the others."""
    jobs, errors = [], []
    for query, city, pages in SEARCHES:
        try:
            jobs += _search(client, query, city, pages)
        except BlockedError:
            raise                      # host refused us: stop, report as blocked
        except FetchError as e:
            errors.append(e)
    if errors and not jobs:
        raise errors[0]
    return jobs
