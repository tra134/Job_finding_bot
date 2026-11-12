import re

from bs4 import BeautifulSoup

from ..models import Job
from .common import text

NAME = "TopCV"


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for c in soup.select(".job-item-search-result"):
        a = c.select_one("h3.title a")
        if not a:
            continue
        url = (a.get("href") or "").split("?")[0]
        jobs.append(Job(
            title=text(c.select_one("h3.title a span")) or text(a),
            company=text(c.select_one(".company-name")), url=url, source=NAME,
            salary=text(c.select_one(".title-salary")),
            location=text(c.select_one(".address, .city-text")),
            posted=text(c.select_one(".label-update, .time")),
            experience=text(c.select_one(".exp span, .exp"))))
    return jobs


def total_pages(html):
    m = re.search(r"/\s*(\d+)\s*trang", html)
    return int(m.group(1)) if m else 1


def _pages(client, base, max_pages):
    jobs = []
    for page in range(1, max_pages + 1):
        sep = "&" if "?" in base else "?"
        html = client.get(f"{base}{sep}page={page}").text
        found = parse(html)
        jobs += found
        if not found or page >= total_pages(html):
            break
    return jobs


def fetch(client):
    jobs = []
    for slug in ("thuc-tap", "intern"):
        jobs += _pages(client, f"https://www.topcv.vn/tim-viec-lam-{slug}-tai-da-nang-kl8", 3)
    jobs += _pages(client, "https://www.topcv.vn/tim-viec-lam-tieng-nhat-tai-da-nang-kl8", 2)
    jobs += _pages(client, "https://www.topcv.vn/tim-viec-lam-intern", 2)
    return jobs
