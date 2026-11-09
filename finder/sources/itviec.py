import re

from bs4 import BeautifulSoup

from ..models import Job
from .common import text

NAME = "ITviec"
LOC = re.compile(r"Ha Noi|Ho Chi Minh|Da Nang|Others|Remote")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for c in soup.select(".job-card"):
        a = c.select_one("h3 a")
        if not a:
            continue
        logo = c.select_one("a.logo-employer-card")
        body = text(c)
        locs = []
        for m in LOC.findall(body):
            if m not in locs:
                locs.append(m)
        posted = re.search(r"Posted\s+(.+?ago)", body)
        jobs.append(Job(
            title=text(a), company=(logo.get("title") if logo else "") or "",
            location=" - ".join(locs), url=(a.get("href") or "").split("?")[0],
            source=NAME, posted=posted.group(1) if posted else ""))
    return jobs


def fetch(client):
    jobs = []
    for base in ("https://itviec.com/it-jobs/intern/da-nang", "https://itviec.com/it-jobs/intern"):
        for page in (1, 2):
            html = client.get(base if page == 1 else f"{base}?page={page}").text
            found = parse(html)
            jobs += found
            if len(found) < 20:
                break
    return jobs
