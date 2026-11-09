import json
import re

from ..models import Job
from .common import parse_dmy

NAME = "TopDev"
URL = "https://topdev.vn/jobs/search?keyword=intern"
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
ROW = re.compile(rb"([0-9a-f]+):(?:(T)([0-9a-f]+),|[\[{])")
REF = re.compile(r"\$([0-9a-f]+)((?::[^:]+)*)$")


def _lines(html):
    data = "".join(json.loads(m.group(1)) for m in PUSH.finditer(html)).encode()
    lines, pos = {}, 0
    while pos < len(data):
        m = ROW.match(data, pos)
        if not m:
            nl = data.find(b"\n", pos)
            pos = len(data) if nl < 0 else nl + 1
            continue
        if m.group(2):
            pos = m.end() + int(m.group(3), 16)
            continue
        nl = data.find(b"\n", m.end())
        end = len(data) if nl < 0 else nl
        try:
            lines[m.group(1).decode()] = json.loads(data[m.end() - 1:end])
        except ValueError:
            pass
        pos = end + 1
    return lines


def _resolve(lines, ref):
    m = REF.match(ref)
    try:
        o = lines[m.group(1)]
        for p in m.group(2).split(":")[1:]:
            o = o[3 if p == "props" else int(p)] if isinstance(o, list) else o[p]
        return o
    except (AttributeError, KeyError, IndexError, ValueError, TypeError):
        return None


def _walk(o, out):
    if isinstance(o, dict):
        if "detail_url" in o and "title" in o:
            out.append(o)
            return
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


def _str(v):
    return v.strip() if isinstance(v, str) else ""


def parse(html):
    lines = _lines(html)
    found = []
    _walk(list(lines.values()), found)
    jobs, seen = [], set()
    for d in found:
        url = _str(d.get("detail_url")).split("?")[0]
        title = _str(d.get("title"))
        if not title or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        company = d.get("company")
        if isinstance(company, str):
            company = _resolve(lines, company)
        company = _str(company.get("display_name")) if isinstance(company, dict) else ""
        addr = d.get("addresses") if isinstance(d.get("addresses"), dict) else {}
        salary = d.get("salary") if isinstance(d.get("salary"), dict) else {}
        sal = _str(salary.get("value"))
        if sal.lower() == "negotiable":
            sal = ""
        pub = d.get("published") if isinstance(d.get("published"), dict) else {}
        exp = d.get("expires") if isinstance(d.get("expires"), dict) else {}
        jobs.append(Job(
            title=title, company=company, location=_str(addr.get("address_region_list")),
            url=url, source=NAME, salary=sal, posted=_str(pub.get("date")),
            deadline=parse_dmy(_str(exp.get("date")))))
    return jobs


def fetch(client):
    return parse(client.get(URL).text)
