from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None

    v = str(value).strip()
    if not v:
        return None

    # epoch seconds
    if re.fullmatch(r"\d{10}", v):
        try:
            return datetime.fromtimestamp(int(v), tz=UTC)
        except Exception:
            return None

    # Common Chinese date: YYYY年MM月DD日
    m = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", v)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d, tzinfo=UTC)
        except Exception:
            return None

    # ISO 8601
    try:
        iso = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        pass

    # RFC 822 / feed dates
    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def clamp_excerpt(text: str | None, max_len: int = 600) -> str | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return None
    return t[:max_len]


def sha1(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def normalize_space(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def fingerprint(company: str | None, title: str, city: str | None) -> str:
    base = "|".join([normalize_space(company), normalize_space(title), normalize_space(city)])
    return sha1(base)


KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    ("bank_tech", ["银行科技", "金融科技", "bank", "fintech", "支付", "清算", "核心系统", "风控", "反欺诈"]),
    ("new_energy", ["新能源", "储能", "光伏", "风电", "氢能", "新能源车", "ev", "充电", "电驱"]),
    ("lithium_battery", ["锂电", "锂离子", "电芯", "正极", "负极", "电解液", "隔膜", "pack", "bms", "电池"]),
    ("battery_rnd", ["电池研发", "材料研发", "工艺研发", "研发工程师", "lab", "实验室", "仿真", "电化学"]),
    ("project_management", ["项目管理", "pm", "项目经理", "pmp", "交付", "实施"]),
    ("architecture", ["架构", "架构师", "系统架构", "软件架构", "企业架构", "ea", "togaf", "架构管理"]),
]


def auto_tags(title: str, excerpt: str | None, base_tags: list[str] | None = None) -> list[str]:
    text = f"{title} {excerpt or ''}".lower()
    tags: list[str] = []
    if base_tags:
        tags.extend([t for t in base_tags if t])

    for tag, kws in KEYWORD_TAGS:
        for kw in kws:
            if kw.lower() in text:
                tags.append(tag)
                break

    seen = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def is_recent(published_at: datetime | None, since_days: int) -> bool:
    if not published_at:
        return True
    return published_at >= (utcnow() - timedelta(days=since_days))


def parse_salary_k(salary_text: str | None) -> tuple[int | None, int | None]:
    """Parse salary text into (min_k, max_k) where unit is k RMB per month.

    Supported examples:
    - "20-40k"
    - "20K-40K"
    - "2-4万"
    - "30k"

    Non-goals: yearly packages, stock, bonus months, etc.
    """

    if not salary_text:
        return (None, None)

    s = str(salary_text).strip()
    if not s:
        return (None, None)

    # Normalize separators
    s2 = s.replace("～", "-").replace("~", "-").replace("至", "-").replace("—", "-")

    # Range in k
    m = re.search(r"(\d{1,3})\s*-\s*(\d{1,3})\s*[kK]\b", s2)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.search(r"(\d{1,3})\s*[kK]\s*-\s*(\d{1,3})\s*[kK]\b", s2)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))

    # Range in 万
    m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s*[万wW]\b", s2)
    if m:
        a, b = int(m.group(1)) * 10, int(m.group(2)) * 10
        return (min(a, b), max(a, b))

    # Single k
    m = re.search(r"\b(\d{1,3})\s*[kK]\b", s2)
    if m:
        v = int(m.group(1))
        return (v, v)

    # Single 万
    m = re.search(r"\b(\d{1,2})\s*[万wW]\b", s2)
    if m:
        v = int(m.group(1)) * 10
        return (v, v)

    return (None, None)


def find_salary_text(text: str | None) -> str | None:
    """Extract a salary snippet from a larger text."""

    if not text:
        return None

    s = str(text)
    # Prefer explicit ranges first.
    m = re.search(r"(\d{1,3}\s*[-～~至—]\s*\d{1,3}\s*[kK])", s)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    m = re.search(r"(\d{1,2}\s*[-～~至—]\s*\d{1,2}\s*[万wW])", s)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    m = re.search(r"(\d{1,3}\s*[kK])", s)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    return None
