from __future__ import annotations

from app.crawler.http import get_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def fetch(board: str, company_name: str | None = None, proxy: str | None = None) -> list[RawJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    data = get_json(url, proxy=proxy)

    out: list[RawJob] = []
    for j in data.get("jobs", []) or []:
        job_url = j.get("absolute_url") or j.get("url")
        title = j.get("title")
        if not job_url or not title:
            continue

        loc = None
        location = j.get("location") or {}
        if isinstance(location, dict):
            loc = location.get("name")

        published_at = parse_dt(j.get("updated_at") or j.get("created_at"))
        content = j.get("content")
        excerpt = clamp_excerpt(content) if isinstance(content, str) else None

        out.append(
            RawJob(
                source_url=job_url,
                title=title,
                company_name=company_name,
                city=loc,
                published_at=published_at,
                excerpt=excerpt,
                tags=[],
            )
        )

    return out
