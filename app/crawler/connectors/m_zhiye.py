from __future__ import annotations

from urllib.parse import urlencode, urlparse

from app.crawler.http import get_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _base(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


def _as_int(v: object, default: int) -> int:
    try:
        i = int(v)  # type: ignore[arg-type]
        return i
    except Exception:
        return default


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Beisen Zhiye mobile portal connector (m.zhiye.com).

    Many央企/国企 portals powered by Beisen expose a public JSON endpoint:
    - GET /JobAd/_SearchJobAd?pi=1&ps=10&jc=1&c1=-1&c2=-1&ky=&c=-1&in=1

    This connector is intentionally light:
    - No login
    - No full snapshots
    - Stores structured fields + short excerpt (Duty) + official click-through URL (detail.html)

    Config keys:
    - base_url: str (required)   # e.g. https://cnnc.m.zhiye.com
    - company_name: str (required)
    - jc: int (default 1)        # 1 社招, 2 校招, 3 实习
    - page_size: int (default 20, max 50)
    - max_pages: int (default 20)
    - ky: str (optional)         # keyword
    - api_keywords: [str] (optional)  # union across keywords
    - c1/c2/c: int (default -1)  # category filters used by the site
    - proxy: str (optional)
    """

    base_url = _base(str(config.get("base_url") or ""))
    if not base_url:
        raise ValueError("m_zhiye requires config.base_url, e.g. https://cnnc.m.zhiye.com")

    company_name = str(config.get("company_name") or "").strip()
    if not company_name:
        raise ValueError("m_zhiye requires config.company_name")

    effective_proxy = proxy or (str(config.get("proxy") or "").strip() or None)

    jc = _as_int(config.get("jc"), 1)
    page_size = min(max(_as_int(config.get("page_size"), 20), 1), 50)
    max_pages = max(_as_int(config.get("max_pages"), 20), 1)

    c1 = _as_int(config.get("c1"), -1)
    c2 = _as_int(config.get("c2"), -1)
    c = _as_int(config.get("c"), -1)

    ky = str(config.get("ky") or "").strip()
    api_keywords = config.get("api_keywords") or []
    api_keywords = [str(x).strip() for x in api_keywords if str(x).strip()]
    keywords = api_keywords or ([ky] if ky else [""])

    out: list[RawJob] = []
    for kw in keywords:
        for page in range(1, max_pages + 1):
            params = {
                "pi": page,
                "ps": page_size,
                "jc": jc,
                "c1": c1,
                "c2": c2,
                "ky": kw,
                "c": c,
                "in": 1,
            }
            url = f"{base_url}/JobAd/_SearchJobAd?" + urlencode(params)
            data = get_json(url, proxy=effective_proxy, timeout=60)
            if not isinstance(data, dict):
                break

            items = data.get("DataResult") or []
            if not isinstance(items, list) or not items:
                break

            for it in items:
                if not isinstance(it, dict):
                    continue

                ad_id = it.get("JobAdId")
                title = str(it.get("JobAdName") or "").strip()
                if not ad_id or not title:
                    continue

                # Official click-through details page (still JS rendered, but stable).
                detail_url = f"{base_url}/detail.html?adId={ad_id}&jc={jc}&c1={c1}&c2={c2}&ky={kw}&c={c}"

                # Company/sub-organization: Department is often the sub-company name.
                dept = str(it.get("Department") or "").strip() or None
                org = str(it.get("OrgName") or "").strip() or None
                comp = dept or org or company_name

                city = str(it.get("LocIdName") or "").strip() or None
                published_at = parse_dt(str(it.get("ToPostDate") or "").strip() or None)

                excerpt = clamp_excerpt(str(it.get("Duty") or "").strip() or None)
                salary_text = str(it.get("Salary") or "").strip() or None

                seniority = str(it.get("YearsofWorkingStr") or it.get("YearsofWorking") or "").strip() or None

                out.append(
                    RawJob(
                        source_url=detail_url,
                        title=title,
                        company_name=comp,
                        city=city,
                        published_at=published_at,
                        excerpt=excerpt,
                        department=dept,
                        seniority=seniority,
                        salary_text=salary_text,
                        tags=[],
                    )
                )

    # De-dup by source_url.
    seen = set()
    deduped: list[RawJob] = []
    for rj in out:
        if rj.source_url in seen:
            continue
        seen.add(rj.source_url)
        deduped.append(rj)
    return deduped

