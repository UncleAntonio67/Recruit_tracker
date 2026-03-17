from __future__ import annotations

from urllib.parse import urlencode

from app.crawler.http import get_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _fetch_pages(*, keyword: str, page_size: int, max_pages: int, area: str, language: str, proxy: str | None) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "pageIndex": page,
            "pageSize": page_size,
            "language": language,
            "area": area,
        }
        if keyword:
            params["keyword"] = keyword

        url = "https://careers.tencent.com/tencentcareer/api/post/Query?" + urlencode(params)
        data = get_json(url, proxy=proxy)
        posts = (data.get("Data") or {}).get("Posts") or []
        if not posts:
            break
        out.extend([p for p in posts if isinstance(p, dict)])

    return out


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Tencent Careers connector.

    Uses the public JSON API:
    - https://careers.tencent.com/tencentcareer/api/post/Query

    Config keys:
    - company_name: str (default: 腾讯)
    - keyword: str (optional)
    - api_keywords: [str] (optional)  # run multiple keyword searches then union results
    - page_size: int (default: 200, max: 200)
    - max_pages: int (default: 10 when api_keywords set, else 30)
    - area: str (default: cn)
    - language: str (default: zh-cn)
    - proxy: str (optional)
    """

    company_name = (config.get("company_name") or "腾讯").strip() or "腾讯"

    page_size = int(config.get("page_size") or 200)
    if page_size <= 0:
        page_size = 200
    page_size = min(page_size, 200)

    api_keywords = config.get("api_keywords") or []
    api_keywords = [str(x).strip() for x in api_keywords if str(x).strip()]

    # If we search by keyword, we can keep max_pages smaller.
    if api_keywords:
        max_pages = int(config.get("max_pages") or 10)
    else:
        max_pages = int(config.get("max_pages") or 30)
    if max_pages <= 0:
        max_pages = 10 if api_keywords else 30

    area = (config.get("area") or "cn").strip() or "cn"
    language = (config.get("language") or "zh-cn").strip() or "zh-cn"

    effective_proxy = proxy or config.get("proxy")

    keyword = (config.get("keyword") or "").strip()

    posts: list[dict] = []
    if api_keywords:
        for kw in api_keywords:
            posts.extend(_fetch_pages(keyword=kw, page_size=page_size, max_pages=max_pages, area=area, language=language, proxy=effective_proxy))
    else:
        posts = _fetch_pages(keyword=keyword, page_size=page_size, max_pages=max_pages, area=area, language=language, proxy=effective_proxy)

    # De-dup by URL
    seen = set()
    out: list[RawJob] = []
    for p in posts:
        job_url = p.get("PostURL")
        title = p.get("RecruitPostName")
        if not job_url or not title:
            continue

        u = str(job_url).strip()
        if not u or u in seen:
            continue
        seen.add(u)

        out.append(
            RawJob(
                source_url=u,
                title=str(title).strip(),
                company_name=company_name,
                city=(p.get("LocationName") or None),
                published_at=parse_dt(p.get("LastUpdateTime")),
                department=(p.get("BGName") or None),
                excerpt=clamp_excerpt(p.get("Responsibility")),
                tags=[],
            )
        )

    return out
