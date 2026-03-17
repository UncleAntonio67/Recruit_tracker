from __future__ import annotations

from urllib.parse import urlencode

from app.crawler.http import get_json
from app.crawler.job_types import RawJob
from app.crawler.utils import parse_dt


_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://zhaopin.kuaishou.cn/",
    "X-Requested-With": "XMLHttpRequest",
}


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Kuaishou (快手) official jobs connector.

    Uses a public endpoint (no login) that powers the official site:
    - GET https://zhaopin.kuaishou.cn/recruit/e/api/v1/open/job/referral/list2

    Config keys:
    - company_name: str (default: 快手)
    - base_url: str (default: https://zhaopin.kuaishou.cn/recruit/e)
    - page_size: int (default: 50)
    - max_pages: int (default: 60)
    - keyword: str (optional)
    - position_nature_code: str (optional)  # e.g. C001/C002...
    - position_category_code: str (optional)
    - work_location_code: str (optional)    # e.g. Beijing/Shanghai/Guangzhou/Shenzhen
    - proxy: str (optional)

    Notes:
    - The API provides `updateTime` and location info; detailed JD text is not fetched (keeps it light and compliant).
    - The official job page is a SPA route; we still store it as source_url for click-through.
    """

    company_name = (config.get("company_name") or "快手").strip() or "快手"
    base_url = (config.get("base_url") or "https://zhaopin.kuaishou.cn/recruit/e").rstrip("/")

    page_size = int(config.get("page_size") or 50)
    if page_size <= 0:
        page_size = 50
    page_size = min(page_size, 100)

    max_pages = int(config.get("max_pages") or 60)
    if max_pages <= 0:
        max_pages = 60

    effective_proxy = proxy or config.get("proxy")

    keyword = (config.get("keyword") or "").strip()
    position_nature_code = (config.get("position_nature_code") or "").strip()
    position_category_code = (config.get("position_category_code") or "").strip()
    work_location_code = (config.get("work_location_code") or "").strip()

    out: list[RawJob] = []

    for page in range(1, max_pages + 1):
        params: dict[str, str | int] = {
            "pageNum": page,
            "pageSize": page_size,
        }
        if keyword:
            params["keyword"] = keyword
        if position_nature_code:
            params["positionNatureCode"] = position_nature_code
        if position_category_code:
            params["positionCategoryCode"] = position_category_code
        if work_location_code:
            params["workLocationCode"] = work_location_code

        url = base_url + "/api/v1/open/job/referral/list2?" + urlencode(params)
        data = get_json(url, proxy=effective_proxy, timeout=30, headers=_DEFAULT_HEADERS)

        if not isinstance(data, dict) or data.get("code") != 0:
            # Stop early; treat as empty.
            break

        result = data.get("result") or {}
        items = result.get("list") or []
        if not items:
            break

        for it in items:
            if not isinstance(it, dict):
                continue

            job_id = it.get("id")
            title = it.get("name")
            if not job_id or not title:
                continue

            work_locations = it.get("workLocations") or []
            city = None
            if isinstance(work_locations, list) and work_locations:
                first = work_locations[0]
                if isinstance(first, dict) and first.get("name"):
                    city = str(first.get("name"))

            published_at = parse_dt(it.get("updateTime"))

            # Route observed in the frontend bundle: /official/:type/job-info/:id
            # This is an official click-through URL for users.
            source_url = f"{base_url}/official/social/job-info/{job_id}"

            out.append(
                RawJob(
                    source_url=source_url,
                    title=str(title).strip(),
                    company_name=company_name,
                    city=city,
                    published_at=published_at,
                    excerpt=None,
                    tags=[],
                )
            )

    return out
