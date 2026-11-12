from datetime import date

import pytest

from finder import filters
from finder.models import Job

TODAY = date(2026, 11, 9)


def job(title, location="Đà Nẵng", level="", deadline=None, company="X", url="https://x.test/1",
        source="S"):
    return Job(title=title, company=company, location=location, url=url, source=source,
               level=level, deadline=deadline)


@pytest.mark.parametrize("title,ok", [
    ("Software Engineer Intern", True),
    ("Thực tập sinh lập trình Java", True),
    ("Backend Trainee", True),
    ("Internal Tools Developer", False),            # 'internal' is not 'intern'
    ("International Developer", False),
    ("Junior Developer", False),
])
def test_internship(title, ok):
    assert filters.is_internship(job(title)) is ok


def test_vietnamworks_level_accepts():
    assert filters.is_internship(job("Developer", level="Intern/Student"))


@pytest.mark.parametrize("title,ok", [
    ("Web Intern", True), ("AI Research Intern", True), ("QA Intern", True),
    ("Thực tập sinh kiểm thử phần mềm", True), ("Java Intern", True),
    ("Data Analyst Intern", True), ("Software Engineer Intern", True),
    ("Mobile Engineer Intern", True), ("IT Intern", True),
    ("IT Intern - Digital & Data Services", True), ("Business Analyst (Intern)", True),
    ("Thực tập sinh CNTT", True), ("Audit Intern", False), ("Admin Intern", False),
    ("Intern Waiter", False), ("Maid Intern", False),    # 'ai'/'web' inside words
    ("Mechanical Engineer Intern", False),
    ("Accounting Intern", False),
])
def test_technical(title, ok):
    assert filters.is_technical(title) is ok


@pytest.mark.parametrize("title", [
    "Sales Intern (IT products)", "HR Intern", "Marketing Developer Intern",
    "Nhân sự IT thực tập", "Kế toán thực tập", "Senior Developer Intern",
    "Management Trainee Software", "Fast Track Developer Intern",
    "Thực tập sinh kỹ năng Nhật Bản", "Thực tập sinh đi Nhật Bản lập trình",
    "Kỹ thuật sinh lập trình", "Xuất khẩu lao động thực tập",
])
def test_excluded(title):
    assert filters.is_excluded(job(title))


def test_japanese_language_alone_not_excluded():
    assert not filters.is_excluded(job("Software Intern (tiếng Nhật)"))


def test_expired_rejected():
    j = job("Java Intern", deadline=date(2026, 11, 1))
    assert not filters.accept(j, TODAY)
    assert filters.accept(job("Java Intern", deadline=date(2026, 11, 30)), TODAY)


def test_non_http_url_rejected():
    assert not filters.accept(job("Java Intern", url="javascript:alert(1)"), TODAY)


def test_tiers():
    assert filters.tier(job("Java Intern", "Đà Nẵng")) == 1
    assert filters.tier(job("Java Intern", "Ha Noi - Da Nang")) == 1
    assert filters.tier(job("Java Intern (Remote)", "Hà Nội")) == 2
    assert filters.tier(job("Java Intern", "Remote")) == 2
    assert filters.tier(job("Java Intern", "Hồ Chí Minh")) == 3


def test_multi_city():
    assert filters.is_multi_city(job("x", "Đà Nẵng & 2 nơi khác"))
    assert filters.is_multi_city(job("x", "Ha Noi - Ho Chi Minh - Da Nang"))
    assert not filters.is_multi_city(job("x", "Đà Nẵng"))


def test_select_dedups_across_sources_and_groups():
    jobs = [job("Java Intern", source="A"), job("Java  Intern", source="B"),
            job("Python Intern", "Hà Nội"), job("Sales Intern"), job("Web Intern", "Remote")]
    g = filters.select(jobs, TODAY)
    assert len(g[1]) == 1 and g[1][0].sources == ["A", "B"]
    assert len(g[2]) == 1 and len(g[3]) == 1


def test_parse_areas():
    assert filters.parse_areas(None) == {1, 2, 3}
    assert filters.parse_areas("") == {1, 2, 3}
    assert filters.parse_areas("danang") == {1}
    assert filters.parse_areas(" DaNang , remote ") == {1, 2}
    assert filters.parse_areas("danang,remote,other") == {1, 2, 3}
    with pytest.raises(ValueError, match="hanoi"):
        filters.parse_areas("danang,hanoi")


@pytest.mark.parametrize("text,langs", [
    ("Yêu cầu tiếng Nhật N3 trở lên, ưu tiên N2", ["Japanese N3"]),
    ("English fluent communication", ["English (fluent)"]),
    ("Giao tiếp tiếng Anh cơ bản", ["English"]),
    ("BrSE Fresher", ["Japanese"]),
    ("Tiếng Nhật N2, tiếng Anh lưu loát", ["Japanese N2", "English (fluent)"]),
    ("Room N10, Python", []),
])
def test_detect_langs(text, langs):
    assert filters.detect_langs(text) == langs


def ljob(title, level="", details="", experience=""):
    j = job(title, level=level)
    j.details, j.experience = details, experience
    return j


@pytest.mark.parametrize("j,ok", [
    (ljob("Bridge System Engineer (BrSE) - Fresher"), True),
    (ljob("Kỹ sư cầu nối (BrSE)", experience="Dưới 1 năm"), True),
    (ljob("BrSE", level="Internship/Fresher"), True),                 # ITviec tags
    (ljob("Fullstack – Tiếng Nhật Từ N3", experience="Không yêu cầu"), True),
    (ljob("Java Developer", level="Fresher/Entry level", details="Tiếng Nhật N3"), True),
    (ljob("Java Developer", experience="no experience", details="Tiếng Nhật N3"), True),
    (ljob("Python Intern", details="English fluent"), True),
    (ljob("QA Executive", level="Fresher/Entry level", details="English fluent"), True),
    (ljob("Kỹ sư cầu nối (BrSE) - Đà Nẵng"), False),                 # level unknown
    (ljob("Bridge System Engineer (Japanese N1/N2)", experience="2 năm"), False),
    (ljob("Java Developer", level="Fresher/Entry level", experience="2 years",
          details="Tiếng Nhật N3"), False),                         # stated years win
    (ljob("QA Executive", level="Fresher/Entry level", details="English"), False),
    (ljob("Nhân Viên Tiếng Nhật - Không Cần Kinh Nghiệm"), False),  # not an IT job
    (ljob("Senior BrSE (Tiếng Nhật)"), False),
    (ljob("[Danang] PMO/ Project Leader (Japanese N2)", level="Fresher"), False),
    (ljob("Thực tập sinh Nhật Bản"), False),                        # labour export
])
def test_language_roles(j, ok):
    assert filters.accept(j, TODAY) is ok


@pytest.mark.parametrize("exp,years", [
    ("Không yêu cầu", 0), ("Dưới 1 năm", 0), ("1 năm", 1), ("2 years", 2),
    ("no experience", 0), ("", None), ("Trên 3 năm", 3),
])
def test_years_required(exp, years):
    j = job("x")
    j.experience = exp
    assert filters.years_required(j) == years
