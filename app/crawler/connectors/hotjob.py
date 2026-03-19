from __future__ import annotations

import re
from urllib.parse import urlparse

from app.crawler.http import get_json, post_form
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _origin(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


def _suite_key_from_link(link: str) -> str | None:
    # Example: https://sec.hotjob.cn/SU60de.../pb/index.html#/
    m = re.search(r"/(SU[0-9a-fA-F]{10,})/", link or "")
    if not m:
        return None
    return m.group(1)


def _resolve_suite_key(origin: str, *, sld: str, proxy: str | None) -> str | None:
    # POST https://<host>/wecruit/common/getSLD  (form: sld=<host>)
    # Returns: { data: { linkData: { link: "https://<host>/SU.../pb/index.html#/" }}, state:"200" }
    u = f"{origin}/wecruit/common/getSLD"
    res = post_form(u, {"sld": sld}, proxy=proxy, timeout=30)
    if not isinstance(res, dict):
        return None
    if str(res.get("state") or "") != "200":
        return None
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    link_data = data.get("linkData") if isinstance(data.get("linkData"), dict) else {}
    link = (link_data.get("wtLink") or link_data.get("link") or "").strip()
    if not link:
        return None
    return _suite_key_from_link(link)


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Hotjob (大易/微招聘, hotjob.cn) connector.

    Many央企/国企/大型集团使用 hotjob.cn 作为“招聘官网”入口，实际后端为 wecruit 接口。

    We rely on public endpoints (no login) and store only structured fields + short excerpt.

    Config keys:
    - base_url: str (required)         # e.g. https://sec.hotjob.cn
    - company_name: str (optional)
    - sld: str (optional)              # default: host of base_url, e.g. sec.hotjob.cn
    - suite_key: str (optional)        # e.g. SU60de8350...
    - recruit_type: int (default 2)    # 2 社招, 1 校招, 12 实习, 13 高层次/海外(因站点不同略有差异)
    - page_size: int (default 12)
    - max_pages: int (default 10)
    - include_keywords/exclude_keywords/city_allowlist: handled globally in runner
    - proxy: str (optional)
    """

    base_url = _origin(str(config.get("base_url") or ""))
    if not base_url:
        raise ValueError("hotjob requires config.base_url, e.g. https://sec.hotjob.cn")

    p = urlparse(base_url)
    host = (p.netloc or "").strip()
    if not host:
        raise ValueError("hotjob base_url host missing")

    effective_proxy = proxy or (str(config.get("proxy") or "").strip() or None)

    suite_key = (str(config.get("suite_key") or "")).strip()
    if not suite_key:
        sld = (str(config.get("sld") or "")).strip() or host
        suite_key = _resolve_suite_key(base_url, sld=sld, proxy=effective_proxy) or ""
    if not suite_key:
        raise ValueError("hotjob: failed to resolve suite_key (SU...) from base_url/sld")

    recruit_type = int(config.get("recruit_type") or 2)
    page_size = int(config.get("page_size") or 12)
    if page_size <= 0:
        page_size = 12
    page_size = min(page_size, 50)

    max_pages = int(config.get("max_pages") or 10)
    if max_pages <= 0:
        max_pages = 10

    company_name = (str(config.get("company_name") or "")).strip() or None

    # Job list endpoint (public):
    # GET /wecruit/positionInfo/listPosition/<SU...>?recruitType=2&pageNo=1&pageSize=12
    out: list[RawJob] = []
    for page in range(1, max_pages + 1):
        list_url = f"{base_url}/wecruit/positionInfo/listPosition/{suite_key}?recruitType={recruit_type}&pageNo={page}&pageSize={page_size}"
        root = get_json(list_url, proxy=effective_proxy, timeout=60)
        if not isinstance(root, dict) or str(root.get("state") or "") != "200":
            break

        data = root.get("data") if isinstance(root.get("data"), dict) else {}
        page_form = data.get("pageForm") if isinstance(data.get("pageForm"), dict) else {}
        items = page_form.get("pageData") if isinstance(page_form.get("pageData"), list) else []
        if not items:
            break

        for it in items:
            if not isinstance(it, dict):
                continue
            post_id = (it.get("postId") or "").strip()
            title = (it.get("postName") or "").strip()
            comp = (it.get("company") or "").strip() or company_name
            city = (it.get("workPlaceStr") or "").strip() or None
            published_at = parse_dt((it.get("publishDate") or it.get("publishFirstDate") or "").strip() or None)

            if not post_id or not title:
                continue

            # Detail endpoint expects form POST:
            # POST /wecruit/positionInfo/listPositionDetail/SU<currentSuiteKey>  postId=<id>
            current_suite_key = (it.get("currentSuiteKey") or "").strip()
            excerpt = None
            dept = None
            seniority = None
            try:
                if current_suite_key:
                    detail_url = f"{base_url}/wecruit/positionInfo/listPositionDetail/SU{current_suite_key}"
                    detail = post_form(detail_url, {"postId": post_id}, proxy=effective_proxy, timeout=60)
                    if isinstance(detail, dict) and str(detail.get("state") or "") == "200":
                        dd = detail.get("data") if isinstance(detail.get("data"), dict) else {}
                        # Common fields: workContent / serviceCondition / applyPositionContent / orgName
                        org_name = (dd.get("orgName") or "").strip()
                        if org_name:
                            dept = org_name
                        work_content = (dd.get("workContent") or "").strip()
                        service_cond = (dd.get("serviceCondition") or "").strip()
                        excerpt = clamp_excerpt("\n".join([x for x in [work_content, service_cond] if x]))
            except Exception:
                excerpt = excerpt

            # Click-through URL (SPA route):
            # The front-end uses query params: ?postType=<recruitType>&postId=<postId>
            source_url = f"{base_url}/{suite_key}/pb/index.html#/posDetail?postType={recruit_type}&postId={post_id}"

            out.append(
                RawJob(
                    source_url=source_url,
                    title=title,
                    company_name=comp,
                    city=city,
                    published_at=published_at,
                    excerpt=excerpt,
                    department=dept,
                    seniority=seniority,
                    salary_text=None,
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

