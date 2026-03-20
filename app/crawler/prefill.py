from __future__ import annotations

import json
import os
import re

from app.crawler.http import get_text
from app.crawler.utils import clamp_excerpt, find_salary_text, parse_dt
from app.ui_options import CORE_CITIES


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


def _normalize_city_core(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    for c in CORE_CITIES:
        if c in s:
            return c
    return None


def _extract_jsonld_jobposting(html: str) -> dict:
    """Extract JobPosting fields from JSON-LD when available.

    This improves prefill accuracy for many official career sites.
    """

    out: dict = {}
    if not html:
        return out

    # Match <script type="application/ld+json"> ... </script>
    for m in re.finditer(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
        raw = (m.group(1) or "").strip()
        if not raw or len(raw) > 2_000_000:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        # Normalize to a list of candidate objects.
        candidates = []
        if isinstance(data, dict):
            candidates = [data]
            if isinstance(data.get("@graph"), list):
                candidates += [x for x in data.get("@graph") if isinstance(x, dict)]
        elif isinstance(data, list):
            candidates = [x for x in data if isinstance(x, dict)]

        def is_jobposting(obj: dict) -> bool:
            t = obj.get("@type")
            if isinstance(t, str) and t.lower() == "jobposting":
                return True
            if isinstance(t, list) and any(isinstance(x, str) and x.lower() == "jobposting" for x in t):
                return True
            return False

        for obj in candidates:
            if not is_jobposting(obj):
                continue
            title = obj.get("title") or obj.get("name")
            if title and isinstance(title, str):
                out["title"] = title.strip()[:120]

            org = obj.get("hiringOrganization") or obj.get("organization") or {}
            if isinstance(org, dict):
                cn = org.get("name")
                if cn and isinstance(cn, str):
                    out["company_name"] = cn.strip()[:80]

            date_posted = obj.get("datePosted") or obj.get("dateCreated")
            if date_posted and isinstance(date_posted, str):
                dt = parse_dt(date_posted.strip())
                if dt:
                    out["published_at"] = dt.date().isoformat()

            # Location: support both list/dict.
            loc = obj.get("jobLocation")
            locs = []
            if isinstance(loc, dict):
                locs = [loc]
            elif isinstance(loc, list):
                locs = [x for x in loc if isinstance(x, dict)]
            for L in locs:
                addr = L.get("address") or {}
                if isinstance(addr, dict):
                    city = addr.get("addressLocality") or addr.get("addressRegion") or addr.get("streetAddress")
                    if city and isinstance(city, str):
                        out["city"] = city.strip()[:30]
                        break
            if "city" in out:
                break

            desc = obj.get("description")
            if desc and isinstance(desc, str):
                out["excerpt"] = clamp_excerpt(desc)
            break

    return out


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

    jl = _extract_jsonld_jobposting(html)

    og_title = _meta_content(html, key="property", value="og:title")
    og_desc = _meta_content(html, key="property", value="og:description")
    desc = _meta_content(html, key="name", value="description")
    title = (jl.get("title") or og_title or _html_title(html) or "").strip()

    city = jl.get("city") or _guess_city(html)
    city = _normalize_city_core(city) or city

    published_at = jl.get("published_at") or _guess_published_date(html)

    excerpt = jl.get("excerpt") or clamp_excerpt(og_desc or desc)
    salary_text = find_salary_text(html)

    # Rough company guess: split by separators in <title>.
    company_name = jl.get("company_name") or None
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
