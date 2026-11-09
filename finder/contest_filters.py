"""Section 4 rules for the Contests channel."""
import re
from datetime import date

from .filters import _rx, fold, safe_url
from .models import Contest

TOPICS = [
    ("AI", _rx([r"ai", r"a\.i", r"artificial intelligence", r"machine learning", r"ml",
                r"deep learning", r"genai", r"generative", r"agents?", r"agentic", r"llms?",
                r"gpt", r"copilot", r"chatbot", r"rag"])),
    ("Fintech", _rx([r"fintech", r"finance", r"financial", r"payments?", r"banking", r"paypal"])),
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
VIETNAM = re.compile(r"viet ?nam|ha noi|hanoi|ho chi minh|\bhcmc?\b|sai gon|saigon|da nang|danang")
DANANG = re.compile(r"da nang|danang")


def classify_mode(location: str, online: bool) -> str:
    loc = fold(location)
    if online or loc in ("online", "digital", "virtual", "worldwide") or "online" in loc:
        return "online"
    if DANANG.search(loc):
        return "da nang"
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
    if c.mode == "other":
        return False
    if c.mode == "da nang":
        return True        # in person in Da Nang: include
    return bool(c.topic)   # online: topic must match


def is_global(c: Contest) -> bool:
    return c.mode == "online" and not c.vietnam_open


def select(contests, today: date):
    seen, out = set(), []
    for c in contests:
        k = (fold(c.name), c.mode)
        if k in seen or not accept(c, today):
            continue
        seen.add(k)
        out.append(c)
    out.sort(key=lambda c: (c.mode != "da nang", c.ended or date.max))
    return out
