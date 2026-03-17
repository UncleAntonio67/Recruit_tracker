from __future__ import annotations

from app.crawler.http import post_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _as_city(district_list: object) -> str | None:
    if not isinstance(district_list, list):
        return None
    names: list[str] = []
    for it in district_list:
        if not isinstance(it, dict):
            continue
        name = (it.get("area_cn") or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return None
    return "/".join(names)[:120]


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Guopin (iguopin.com) jobs connector (China SOE / large enterprises aggregator).

    Uses the public JSON API:
    - https://gp-api.iguopin.com/api/jobs/v1/list

    Notes:
    - This is an aggregator covering many SOEs and large enterprises. Use include/exclude keyword filters in runner
      to keep only relevant roles.

    Config keys:
    - company_name: str (default: 国聘网)
    - api_base: str (default: https://gp-api.iguopin.com)
    - page_size: int (default: 50)
    - max_pages: int (default: 40)
    - keyword: str (optional)
    - api_keywords: [str] (optional)  # run multiple keyword searches then union results
    - proxy: str (optional)
    """

    company_name = (config.get("company_name") or "国聘网").strip() or "国聘网"
    api_base = (config.get("api_base") or "https://gp-api.iguopin.com").strip().rstrip("/")

    page_size = int(config.get("page_size") or 50)
    if page_size <= 0:
        page_size = 50
    page_size = min(page_size, 100)

    max_pages = int(config.get("max_pages") or 40)
    if max_pages <= 0:
        max_pages = 40

    keyword = (config.get("keyword") or "").strip()
    api_keywords = config.get("api_keywords") or []
    api_keywords = [str(x).strip() for x in api_keywords if str(x).strip()]

    effective_proxy = proxy or config.get("proxy")

    # If keyword search is configured, we union results across keywords.
    keywords = api_keywords or ([keyword] if keyword else [""])

    out: list[RawJob] = []
    for kw in keywords:
        for page in range(1, max_pages + 1):
            payload = {"page": page, "page_size": page_size}
            if kw:
                payload["keyword"] = kw

            data = post_json(f"{api_base}/api/jobs/v1/list", payload, proxy=effective_proxy, timeout=60)
            root = data.get("data") if isinstance(data, dict) else None
            items = (root or {}).get("list") if isinstance(root, dict) else None
            if not items or not isinstance(items, list):
                break

            for it in items:
                if not isinstance(it, dict):
                    continue
                job_id = (it.get("job_id") or "").strip()
                title = (it.get("job_name") or "").strip()
                comp = (it.get("company_name") or "").strip() or company_name
                if not job_id or not title:
                    continue

                out.append(
                    RawJob(
                        source_url=f"https://www.iguopin.com/job?id={job_id}",
                        title=title,
                        company_name=comp,
                        city=_as_city(it.get("district_list")),
                        published_at=parse_dt(it.get("update_time") or it.get("create_time")),
                        department=(it.get("department_cn") or it.get("department") or None),
                        seniority=(it.get("experience_cn") or None),
                        excerpt=clamp_excerpt(it.get("contents") or None),
                        tags=[],
                    )
                )

    # De-dup by url (job_id) in case API repeats across pages/keywords.
    seen = set()
    deduped: list[RawJob] = []
    for rj in out:
        if rj.source_url in seen:
            continue
        seen.add(rj.source_url)
        deduped.append(rj)
    return deduped

