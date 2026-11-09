from bs4 import BeautifulSoup

from ..models import Job
from .common import abs_url, text

NAME = "CareerLink"
BASE = "https://www.careerlink.vn"


def _leaf(card, sel):
    """Innermost element matching sel (the outer one also holds neighbouring text)."""
    els = [e for e in card.select(sel) if not e.select(sel)]
    return els[0] if els else None


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for c in soup.select('[data-testid="job-result-row"]'):
        a = c.select_one('a[class*="__jobLink"]')
        if not a:
            continue
        sal_leaf = _leaf(c, '[class*="__salary"]')
        outer = c.select_one('[class*="__salary"]')
        salary = text(sal_leaf)
        level = text(outer).replace(salary, "", 1).strip(" |") if outer is not sal_leaf else ""
        jobs.append(Job(
            title=text(c.select_one('[class*="__name"]')) or text(a),
            company=text(c.select_one('a[class*="__company"]')),
            location=text(_leaf(c, '[class*="__location"]')),
            url=abs_url(BASE, a.get("href")), source=NAME, salary=salary, level=level))
    return jobs


def fetch(client):
    jobs = []
    for kw in ("thuc+tap", "intern"):
        for page in (1, 2, 3):
            found = parse(client.get(f"{BASE}/vieclam/list?keyword={kw}&location_ids=DN"
                                     f"&order=date&sort=desc&page={page}").text)
            jobs += found
            if not found:
                break
    for kw in ("intern+developer", "thuc+tap+lap+trinh"):
        for page in (1, 2):
            found = parse(client.get(f"{BASE}/vieclam/list?keyword={kw}"
                                     f"&order=date&sort=desc&page={page}").text)
            jobs += found
            if not found:
                break
    return jobs
