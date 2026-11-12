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
    r"cong nghe thong tin", r"it", r"cntt", r"business analysts?", r"tu dong hoa",
])
ENGINEER = re.compile(r"(?<![\w])engineers?(?![\w])")
ENGINEER_CONTEXT = _rx([
    r"software", r"data", r"ai", r"ml", r"devops", r"cloud", r"security", r"qa", r"qc",
    r"test", r"embedded", r"firmware", r"iot", r"mobile", r"web", r"backend", r"frontend",
    r"platform", r"sre", r"system", r"network", r"it",
])

NON_TECH = _rx([
    r"sales", r"business development", r"recruiters?", r"recruitment", r"hr", r"nhan su",
    r"marketing", r"content", r"kinh doanh", r"ke toan", r"accounting", r"ban hang",
    r"giao vien", r"gia su", r"tro giang", r"teachers?", r"tutors?",
])
SENIOR = _rx([r"senior", r"manager", r"lead", r"leaders?", r"head of", r"management trainee",
              r"fast track", r"general manager"])
# IT roles whose core skill is a language (mostly Japanese outsourcing in Da Nang).
LANG_IT_ROLE = _rx([r"brse", r"bridge (?:system |software )?engineers?", r"ky su cau noi",
                    r"it comtor", r"comtor it", r"phien dich it", r"bien dich it",
                    r"it interpreter", r"it translator"])
LABOUR_EXPORT = [re.compile(p) for p in [
    r"(di|sang|tai|lam viec tai) (nhat ban|nhat|han quoc|dai loan|duc)",
    r"thuc tap sinh (ky nang )?(nhat ban|han quoc|dai loan|duc)",
    r"xuat khau lao dong", r"\bxkld\b", r"ky thuat sinh",
]]

# Entry-level markers for non-intern postings (fresher roles asking for a language).
ENTRY = _rx([r"fresher", r"entry level", r"moi tot nghiep", r"no experience",
             r"khong (?:can|yeu cau) kinh nghiem", r"chua co kinh nghiem"])

# Language skills: (label, pattern). Japanese also reports the JLPT level (N1-N5).
LANGS = [
    ("Japanese", _rx([r"tieng nhat", r"japanese", r"jlpt", r"n[1-5]", r"brse",
                      r"bridge (?:system |software )?engineers?", r"comtor", r"nihongo"])),
    ("English", _rx([r"tieng anh", r"english", r"ielts", r"toeic", r"toefl"])),
    ("Korean", _rx([r"tieng han", r"korean", r"topik"])),
    ("Chinese", _rx([r"tieng trung", r"chinese", r"mandarin", r"hsk"])),
]
JLPT = re.compile(r"(?<![\w])n([1-5])(?![\w])")
FLUENT = re.compile(r"fluent|fluency|thanh thao|thong thao|luu loat|business level")


def detect_langs(text):
    """'... tieng Nhat N3 ... English fluent' -> ['Japanese N3', 'English (fluent)']."""
    t = fold(text)
    out = []
    for name, rx in LANGS:
        m = rx.search(t)
        if not m:
            continue
        if name == "Japanese":
            levels = sorted(set(JLPT.findall(t)))
            if levels:   # N5 is the easiest; the largest number is the minimum asked for
                name += f" N{levels[-1]}"
        elif name == "English":
            near = t[max(0, m.start() - 60):m.end() + 60]
            if FLUENT.search(near):
                name += " (fluent)"
        out.append(name)
    return out


def job_langs(job: Job):
    return detect_langs(f"{job.title} {job.details}")


YEARS = re.compile(r"(\d+)(?:\s*-\s*\d+)?\s*(?:\+\s*)?(?:nam|years?)")
NO_EXPERIENCE = _rx([r"khong yeu cau", r"duoi 1 nam", r"no experience", r"chua co kinh nghiem",
                     r"khong can kinh nghiem"])


def years_required(job: Job):
    """Minimum years of experience asked for; 0 for none/under 1 year; None if unknown."""
    exp = fold(job.experience)
    if not exp:
        return None
    if NO_EXPERIENCE.search(exp):
        return 0
    m = YEARS.search(exp)
    return int(m.group(1)) if m else None


def is_entry_level(job: Job) -> bool:
    """Intern, fresher, or under 1 year of experience. A stated 1+ years wins
    over a 'fresher' label (some posts say 'Fresher/Entry level' but want 2 years)."""
    if is_internship(job):
        return True
    years = years_required(job)
    if years is not None:
        return years < 1
    return bool(ENTRY.search(fold(f"{job.title} {job.level}")))


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


def wanted(job: Job) -> bool:
    """Tech internships, plus IT jobs that use a language (mainly Japanese):
    All of these must be entry level: intern, fresher, or under 1 year of experience.
    - a bridge role in the title (BrSE, IT comtor...);
    - a tech title that names a language, e.g. 'Java Developer (Japanese N2)';
    - a tech job whose requirements ask for a language (English
      only when fluent: plain English is in almost every posting).
    General language jobs ('Nhan vien tieng Nhat') are not IT and are not wanted."""
    title = fold(job.title)
    if is_internship(job) and is_technical(job.title):
        return True
    if not is_entry_level(job):
        return False
    if LANG_IT_ROLE.search(title):
        return True
    if is_technical(job.title) and detect_langs(job.title):
        return True
    asked = [l for l in detect_langs(job.details) if l != "English"]
    return is_technical(job.title) and bool(asked)


def accept(job: Job, today: date) -> bool:
    return (wanted(job) and not is_excluded(job)
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
