"""Section 3 rules: internship + technical + exclusions + tiers."""
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from .models import Job


def fold(text):
    """Lowercase, strip Vietnamese diacritics (d-stroke -> d)."""
    text = (text or "").replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _rx(words):
    return re.compile(r"(?<![\w])(?:" + "|".join(words) + r")(?![\w])")


INTERN = _rx([r"interns?", r"internships?", r"trainees?", r"thuc tap"])
LEVEL_INTERN = "intern/student"

TECH = _rx([
    r"software", r"developers?", r"programmers?", r"backend", r"back-end", r"frontend",
    r"front-end", r"fullstack", r"full-stack", r"full stack", r"web", r"mobile", r"android",
    r"ios", r"flutter", r"react", r"reactjs", r"node", r"nodejs", r"java", r"javascript",
    r"typescript", r"python", r"golang", r"\.net", r"dotnet", r"php", r"devops", r"cloud",
    r"sre", r"qa", r"qc", r"testers?", r"automation test", r"data engineers?",
    r"data analysts?", r"data scientists?", r"ai", r"machine learning", r"ml", r"embedded",
    r"iot", r"cyber ?security", r"lap trinh", r"phat trien phan mem", r"kiem thu",
    r"cong nghe thong tin",
])
ENGINEER = re.compile(r"(?<![\w])engineers?(?![\w])")
ENGINEER_CONTEXT = _rx([
    r"software", r"data", r"ai", r"ml", r"devops", r"cloud", r"security", r"qa", r"qc",
    r"test", r"embedded", r"firmware", r"iot", r"mobile", r"web", r"backend", r"frontend",
    r"platform", r"sre", r"system", r"network", r"it",
])

NON_TECH = _rx([
    r"sales", r"business development", r"recruiters?", r"recruitment", r"hr", r"nhan su",
    r"marketing", r"content", r"kinh doanh", r"ke toan", r"accounting",
])
SENIOR = _rx([r"senior", r"manager", r"lead", r"management trainee", r"fast track",
              r"general manager"])
LABOUR_EXPORT = [re.compile(p) for p in [
    r"(di|sang|tai|lam viec tai) (nhat ban|nhat|han quoc|dai loan|duc)",
    r"thuc tap sinh (ky nang )?(nhat ban|han quoc|dai loan|duc)",
    r"xuat khau lao dong", r"\bxkld\b", r"ky thuat sinh",
]]

DANANG = re.compile(r"\bda nang\b")
REMOTE = re.compile(r"\bremote\b|lam viec tu xa|work from home|\bwfh\b")
OTHER_CITIES = re.compile(r"ha noi|ho chi minh|\bhcm\b|sai gon|hai phong|can tho|hue|nha trang|"
                          r"binh duong|dong nai|quang nam|quang ngai|noi khac")


def is_internship(job: Job) -> bool:
    if fold(job.level) == LEVEL_INTERN:
        return True
    return bool(INTERN.search(fold(job.title)) or INTERN.search(fold(job.level)))


def is_technical(title: str) -> bool:
    t = fold(title)
    if TECH.search(t):
        return True
    return bool(ENGINEER.search(t) and ENGINEER_CONTEXT.search(t))


def is_excluded(job: Job) -> bool:
    t = fold(job.title)
    if NON_TECH.search(t) or SENIOR.search(t):
        return True
    return any(p.search(t) for p in LABOUR_EXPORT)


def is_expired(job: Job, today: date) -> bool:
    return job.deadline is not None and job.deadline < today


def tier(job: Job):
    """1 = Da Nang, 2 = remote, 3 = other cities."""
    loc = fold(job.location)
    if DANANG.search(loc):
        return 1
    if REMOTE.search(loc) or REMOTE.search(fold(job.title)):
        return 2
    return 3


AREAS = {"danang": 1, "remote": 2, "other": 3}


def parse_areas(value):
    """JOB_AREAS from .env, e.g. "danang,remote" -> {1, 2}. Empty/unset -> all tiers."""
    names = [n.strip().lower() for n in (value or "").split(",") if n.strip()]
    if not names:
        return set(AREAS.values())
    bad = [n for n in names if n not in AREAS]
    if bad:
        raise ValueError(f"Unknown JOB_AREAS value(s): {', '.join(bad)}. "
                         f"Use any of: {', '.join(AREAS)}")
    return {AREAS[n] for n in names}


def is_multi_city(job: Job) -> bool:
    loc = fold(job.location)
    return bool(DANANG.search(loc) and (OTHER_CITIES.search(loc) or re.search(r"[,&;]| - ", loc)))


def accept(job: Job, today: date) -> bool:
    return (is_internship(job) and is_technical(job.title) and not is_excluded(job)
            and not is_expired(job, today) and safe_url(job.url))


def safe_url(url: str) -> bool:
    return urlsplit(url or "").scheme in ("http", "https")


def dedup_key(job: Job):
    return (fold(job.title), fold(job.company))


def select(jobs, today: date):
    """Filter, de-duplicate across sources, and group by tier."""
    seen = {}
    for j in jobs:
        if not accept(j, today):
            continue
        k = dedup_key(j)
        if k in seen:
            if j.source not in seen[k].sources:
                seen[k].sources.append(j.source)
            continue
        seen[k] = j
    groups = {1: [], 2: [], 3: []}
    for j in seen.values():
        groups[tier(j)].append(j)
    return groups
