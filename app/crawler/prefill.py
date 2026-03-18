from __future__ import annotations

import os
import re
from urllib.parse import urlparse

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
    # Very lightweight meta parser to keep deps minimal.
    # Example: <meta property="og:title" content="...">
    pat = rf"<meta[^>]+{key}\s*=\s*[\"']{re.escape(value)}[\"'][^>]+content\s*=\s*[\"']([^\"']+)[\"']"
    m = re.search(pat, html, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip() or None


def _guess_city(html: str) -> str | None:
    for pat in [
        r"(?:工作地点|工作地|地点)\s*[:：]\s*([^\n<]{1,30})",
        r"(?:城市)\s*[:：]\s*([^\n<]{1,30})",
    ]:
        m = re.search(pat, html)
        if m:
            s = re.sub(r"\s+", " ", m.group(1)).strip()
            if s:
                return s[:30]
    return None


def _guess_published_date(html: str) -> str | None:
    # Try a few common formats; return ISO date string if detected.
    m = re.search(r"(?:发布时间|发布于|更新时间)\s*[:：]\s*(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})", html)
    if not m:
        return None
    raw = m.group(1).replace(".", "-").replace("/", "-")
    dt = parse_dt(raw)
    if not dt:
        return None
    return dt.date().isoformat()


def prefill_from_url(url: str, *, proxy: str | None = None) -> dict:
    """Best-effort URL prefill. No full snapshot is stored."""

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

    # Keep excerpt short and compliant.
    excerpt = clamp_excerpt(og_desc or desc)
    salary_text = find_salary_text(html)

    # Very rough company guess: split by separators.
    company_name = None
    t = title
    for sep in [" - ", " | ", "-", "|", "_"]:
        if sep in t:
            parts = [p.strip() for p in t.split(sep) if p.strip()]
            if len(parts) >= 2:
                # Heuristic: company usually appears in one end.
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
