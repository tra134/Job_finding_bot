from urllib.parse import quote

from .contest_filters import MODE_LABEL, is_global


def search_links():
    return [("Facebook", "https://www.facebook.com/search/posts?q=" + quote("cuộc thi hackathon sinh viên"))]


def render_contest(c):
    flag = "🌍 " if is_global(c) else ""
    fmt = MODE_LABEL.get(c.mode, c.mode)
    return (f"{flag}{c.name} | {c.organiser or 'organiser unknown'} | {fmt} | "
            f"topic: {c.topic or 'unknown'} | deadline (end of submission period): "
            f"{c.reg_deadline.isoformat() if c.reg_deadline else 'unknown'} | "
            f"event: {c.event_date or 'unknown'} | {c.source}\n    {c.url}")


def render_contests(contests):
    out = [f"Contests ({len(contests)})"]
    out += ["  - " + render_contest(c) for c in contests]
    out.append("")
    out.append("Search yourself (link only, never requested by this tool):")
    out += [f"  {n}: {u}" for n, u in search_links()]
    return "\n".join(out)
