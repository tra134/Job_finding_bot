from bs4 import BeautifulSoup

from ..models import Job
from .common import abs_url, parse_dmy, text

NAME = "CareerViet"
BASE = "https://careerviet.vn"


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for c in soup.select(".job-item"):
        a = c.select_one("h2 a.job_link")
        if not a:
            continue
        loc = c.select_one(".location")
        t = text(c.select_one(".time"))
        # .time holds the application deadline ("Han nop"), not the posted date.
        deadline = parse_dmy(t.split("Cập nhật")[0]) if "Hạn nộp" in t else None
        jobs.append(Job(
            title=a.get("title") or text(a), company=text(c.select_one("a.company-name")),
            location=(loc.get("title") if loc and loc.get("title") else text(loc)),
            url=abs_url(BASE, a.get("href")), source=NAME,
            salary=text(c.select_one(".salary")), deadline=deadline))
    return jobs


def fetch(client):
    jobs = []
    # Pagination was not worked out (plan section 8): page 1 only.
    for slug in ("thuc-tap", "intern"):
        jobs += parse(client.get(f"{BASE}/viec-lam/{slug}-tai-da-nang-kl511-vi.html").text)
    jobs += parse(client.get(f"{BASE}/viec-lam/intern-developer-k-vi.html").text)
    return jobs
