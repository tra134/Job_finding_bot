"""Record types shared by sources, filters and output."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Job:
    title: str
    company: str
    location: str            # free text as shown by the source
    url: str
    source: str
    salary: str = ""
    posted: str = ""         # display text, may be relative ("3 ngay truoc")
    deadline: Optional[date] = None
    level: str = ""          # e.g. VietnamWorks jobLevel
    sources: list = field(default_factory=list)   # all sources that listed it (after de-dup)

    def __post_init__(self):
        if not self.sources:
            self.sources = [self.source]
