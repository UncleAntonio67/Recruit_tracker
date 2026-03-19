from __future__ import annotations

import os
import re

from app.crawler.http import get_text
from app.crawler.utils import clamp_excerpt, find_salary_text, parse_dt


def _proxy_from_env() -> str | None:
    return (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip() or None


def _html_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    return t or None


def _meta_content(html: str, *, key: str, value: str) -> str | None:
    # Example: <meta property="og:title" content="...">
    pat = rf"<meta[^>]+{key}\s*=\s*[\"']{re.escape(value)}[\"'][^>]+content\s*=\s*[\"']([^\"']+)[\"']"
    m = re.search(pat, html, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip() or None


def _guess_city(html: str) -> str | None:
    # Keep patterns ASCII-only via unicode escapes to avoid Windows console/codepage issues.
    # Work location is frequently labeled as: 工作地点 / 城市 / 工作地
    patterns = [
        r"(?:\u5de5\u4f5c\u5730\u70b9)\s*[:\uff1a\\s]*([^\n<]{1,30})",
        r"(?:\u57ce\u5e02)\s*[:\uff1a\\s]*([^\n<]{1,30})",
        r"(?:\u5de5\u4f5c\u5730)\s*[:\uff1a\\s]*([^\n<]{1,30})",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if not m:
            continue
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        if s:
            return s[:30]
    return None


def _guess_published_date(html: str) -> str | None:
    # Common labels: 发布时间 / 更新时间 / 更新日期
    m = re.search(
        r"(?:\u53d1\u5e03\u65f6\u95f4|\u66f4\u65b0\u65f6\u95f4|\u66f4\u65b0\u65e5\u671f)\s*[:\uff1a\\s]*(\\d{4}[-/\\.]\\d{1,2}[-/\\.]\\d{1,2})",
        html,
    )
    if not m:
        return None
    raw = m.group(1).replace(".", "-").replace("/", "-")
    dt = parse_dt(raw)
    if not dt:
        return None
    return dt.date().isoformat()


def prefill_from_url(url: str, *, proxy: str | None = None) -> dict:
    """Best-effort URL prefill.

    Compliance note:
    - We do not store full HTML snapshots.
    - Only extract a few structured fields + short excerpt.
    """

    u = (url or "").strip()
    if not u:
        return {}

    effective_proxy = proxy or _proxy_from_env()
    html = get_text(u, proxy=effective_proxy, timeout=30)

    og_title = _meta_content(html, key="property", value="og:title")
    og_desc = _meta_content(html, key="property", value="og:description")
    desc = _meta_content(html, key="name", value="description")
    title = og_title or _html_title(html) or ""

    city = _guess_city(html)
    published_at = _guess_published_date(html)

    excerpt = clamp_excerpt(og_desc or desc)
    salary_text = find_salary_text(html)

    # Rough company guess: split by separators in <title>.
    company_name = None
    t = title
    for sep in [" - ", " | ", "-", "|", "_"]:
        if sep not in t:
            continue
        parts = [p.strip() for p in t.split(sep) if p.strip()]
        if len(parts) >= 2:
            company_name = parts[-1][:80]
            t = parts[0][:120]
            break

    return {
        "source_url": u,
        "title": t[:120] if t else "",
        "company_name": company_name,
        "city": city,
        "published_at": published_at,
        "excerpt": excerpt,
        "salary_text": salary_text,
    }

