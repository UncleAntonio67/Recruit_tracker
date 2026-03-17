from __future__ import annotations

from datetime import UTC, datetime

from app.crawler.http import get_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt


def fetch(company: str, company_name: str | None = None, proxy: str | None = None) -> list[RawJob]:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    data = get_json(url, proxy=proxy)

    out: list[RawJob] = []
    for j in data or []:
        job_url = j.get("hostedUrl") or j.get("applyUrl")
        title = j.get("text")
        if not job_url or not title:
            continue

        categories = j.get("categories") or {}
        loc = categories.get("location") if isinstance(categories, dict) else None

        published_at = None
        created_at = j.get("createdAt")
        if created_at:
            try:
                published_at = datetime.fromtimestamp(int(created_at) / 1000, tz=UTC)
            except Exception:
                published_at = None

        desc = j.get("descriptionPlain") or j.get("description")
        excerpt = clamp_excerpt(desc)

        out.append(
            RawJob(
                source_url=job_url,
                title=title,
                company_name=company_name,
                city=loc,
                published_at=published_at,
                excerpt=excerpt,
                department=categories.get("team") if isinstance(categories, dict) else None,
                tags=[],
            )
        )

    return out
