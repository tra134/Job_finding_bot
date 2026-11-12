"""Plain-text digest for --dry-run (Telegram formatting comes in a later milestone)."""
from urllib.parse import quote

from .filters import is_multi_city, job_langs

TIER_TITLES = {1: "📍 Da Nang", 2: "🏠 Remote", 3: "🏙️ Hanoi / HCMC / other cities"}
OTHER_CAP = 10


def search_links():
    q = quote
    return [
        ("Facebook posts", "https://www.facebook.com/search/posts?q=" + q("tuyển thực tập sinh IT Đà Nẵng")),
        ("Facebook groups", "https://www.facebook.com/search/groups?q=" + q("việc làm IT Đà Nẵng")),
        ("Indeed", "https://vn.indeed.com/jobs?q=" + q("intern developer") + "&l=" + q("Đà Nẵng")),
        ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=" + q("software intern")
         + "&location=" + q("Da Nang, Vietnam")),
    ]


def render_job(j):
    tag = " (multi-city)" if is_multi_city(j) else ""
    parts = [j.title, j.company, (j.location or "location unknown") + tag,
             j.salary or "salary n/a", "/".join(j.sources)]
    langs = job_langs(j)
    if langs:
        parts.append("lang: " + ", ".join(langs))
    return " | ".join(parts) + "\n    " + j.url


def render_jobs(groups):
    out = []
    for t in (1, 2, 3):
        if t not in groups:  # area turned off by JOB_AREAS
            continue
        jobs = groups[t]
        out.append(f"{TIER_TITLES[t]} ({len(jobs)})")
        shown = jobs[:OTHER_CAP] if t == 3 else jobs
        out += ["  - " + render_job(j) for j in shown]
        if t == 3 and len(jobs) > OTHER_CAP:
            out.append(f"  +{len(jobs) - OTHER_CAP} more")
        out.append("")
    out.append("Search yourself (links only, never requested by this tool):")
    out += [f"  {n}: {u}" for n, u in search_links()]
    return "\n".join(out)
