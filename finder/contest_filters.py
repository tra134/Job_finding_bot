"""Section 4 rules for the Contests channel."""
import re
from datetime import date

from .filters import _rx, fold, safe_url
from .models import Contest

TOPICS = [
    ("AI", _rx([r"ai", r"a\.i", r"artificial intelligence", r"machine learning", r"ml",
                r"deep learning", r"genai", r"generative", r"agents?", r"agentic", r"llms?",
                r"gpt", r"copilot", r"chatbot", r"rag", r"codex", r"tri tue nhan tao"])),
    ("Fintech", _rx([r"fintech", r"finance", r"financial", r"payments?", r"banking", r"paypal",
                     r"tai chinh", r"ngan hang", r"thanh toan"])),
    ("Blockchain", _rx([r"blockchain", r"web3", r"crypto", r"defi", r"ethereum", r"solana"])),
    ("Data", _rx([r"data", r"databases?", r"sql", r"nosql", r"analytics", r"mongodb"])),
    ("Cloud", _rx([r"cloud", r"aws", r"azure", r"gcp", r"serverless", r"devops", r"kubernetes"])),
    ("Security", _rx([r"security", r"cyber", r"cybersecurity", r"hacking", r"ctf", r"pentest"])),
    ("Software", _rx([r"software", r"developer", r"coding", r"code", r"programming", r"api",
                      r"open source", r"engineering"])),
]
THEME_MAP = {  # Devpost theme names (folded) -> topic
    "machine learning/ai": "AI", "blockchain": "Blockchain", "fintech": "Fintech",
    "databases": "Data", "cybersecurity": "Security", "devops": "Cloud",
    "developer tools": "Software", "web": "Software", "mobile": "Software",
    "open ended": "Software", "low/no code": "Software", "iot": "Software",
}
CONTEST_WORDS = _rx([r"hackathons?", r"buildathon", r"ideathon", r"datathon",
                     r"contests?", r"competitions?", r"challenges?", r"olympiad", r"ctf",
                     r"cuoc thi", r"hoi thi", r"vong loai", r"ban ket", r"chung ket"])
VIETNAM = re.compile(r"viet ?nam|ha noi|hanoi|ho chi minh|\bhcmc?\b|sai gon|saigon|da nang|danang")
DANANG = re.compile(r"da nang|danang")
BIG_CITIES = re.compile(r"ha noi|hanoi|ho chi minh|\bhcmc?\b|sai gon|saigon")


def classify_mode(location: str, online: bool) -> str:
    loc = fold(location)
    if online or loc in ("online", "digital", "virtual", "worldwide") or "online" in loc:
        return "online"
    if DANANG.search(loc):
        return "da nang"
    if BIG_CITIES.search(loc):
        return "vietnam"
    return "other"


def detect_topic(name: str, themes=()):
    for t in themes:
        mapped = THEME_MAP.get(fold(t))
        if mapped and mapped != "Software":
            return mapped
    text = fold(name)
    for topic, rx in TOPICS:
        if topic == "Software":
            continue
        if rx.search(text):
            return topic
    for t in themes:
        if THEME_MAP.get(fold(t)) == "Software":
            return "Software"
    if dict(TOPICS)["Software"].search(text):
        return "Software"
    return ""


def accept(c: Contest, today: date) -> bool:
    if not safe_url(c.url) or c.closed:
        return False
    if c.ended is not None and c.ended < today:
        return False
    if c.reg_deadline is not None and c.reg_deadline < today:
        return False
    if not c.is_contest or c.mode == "other":
        return False
    if c.mode == "da nang":
        return True        # in person in Da Nang: any topic
    if c.mode == "vietnam":
        return bool(c.topic)                   # Hanoi / HCMC: AI, fintech, ... only
    return bool(c.topic) and c.vietnam_open    # online: only if open to / aimed at Vietnam


def is_global(c: Contest) -> bool:
    return c.mode == "online" and not c.vietnam_open


MODE_LABEL = {"da nang": "Da Nang", "vietnam": "Hanoi/HCMC", "online": "online"}
MODE_ORDER = {"da nang": 0, "vietnam": 1, "online": 2}


def select(contests, today: date):
    seen, out = set(), []
    for c in contests:
        k = (fold(c.name), c.mode)
        if k in seen or not accept(c, today):
            continue
        seen.add(k)
        out.append(c)
    out.sort(key=lambda c: (MODE_ORDER.get(c.mode, 9), c.ended or date.max))
    return out
