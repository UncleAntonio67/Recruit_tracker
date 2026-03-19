from __future__ import annotations

from app.crawler.job_types import RawJob
from app.crawler.prefill import prefill_from_url
from app.crawler.utils import parse_dt


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Fetch a fixed list of job URLs and prefill structured fields.

    This is the compliant way to track jobs from platforms that don't provide stable public APIs
    (Boss/51job/Indeed, etc.): user supplies explicit URLs they have access to.

    Config keys:
    - urls: [str] (required)
    - proxy: str (optional)
    """

    urls = config.get("urls") or []
    urls = [str(u).strip() for u in urls if str(u).strip()]
    if not urls:
        return []

    effective_proxy = proxy or config.get("proxy")

    out: list[RawJob] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)

        info = prefill_from_url(u, proxy=effective_proxy)
        title = (info.get("title") or "").strip()
        if not title:
            continue

        out.append(
            RawJob(
                source_url=u,
                title=title,
                company_name=(info.get("company_name") or config.get("company_name") or None),
                city=(info.get("city") or config.get("city") or None),
                published_at=parse_dt(info.get("published_at")) if info.get("published_at") else None,
                excerpt=(info.get("excerpt") or None),
                salary_text=(info.get("salary_text") or None),
                tags=[],
            )
        )

    return out
