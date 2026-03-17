from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from app.crawler.http import request_bytes
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"<[^>]+>", " ", str(text))
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _post_form_json(url: str, form: dict[str, str | int], *, proxy: str | None) -> object:
    body = urlencode({k: str(v) for k, v in form.items()}).encode("utf-8")
    raw = request_bytes(
        url,
        method="POST",
        data=body,
        proxy=proxy,
        timeout=60,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "recruit-tracker/0.1",
            "Referer": "https://zhaopin.jd.com/web/job/job_info_list/3",
        },
    )
    # JD uses JSON but some endpoints return plain numbers; we only call the list endpoint here.
    return json.loads(raw.decode("utf-8", errors="ignore"))


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """JD (京东) official jobs connector.

    Uses endpoints discovered from the official frontend bundle:
    - POST https://zhaopin.jd.com/web/job/job_list

    Config keys:
    - company_name: str (default: 京东)
    - base_url: str (default: https://zhaopin.jd.com)
    - recruit_type: int (default: 3)   # 3 = 社招 in their site routes
    - page_size: int (default: 50)
    - max_pages: int (default: 40)
    - proxy: str (optional)
    """

    company_name = (config.get("company_name") or "京东").strip() or "京东"
    base_url = (config.get("base_url") or "https://zhaopin.jd.com").strip().rstrip("/")

    recruit_type = int(config.get("recruit_type") or 3)
    page_size = int(config.get("page_size") or 50)
    if page_size <= 0:
        page_size = 50
    page_size = min(page_size, 100)

    max_pages = int(config.get("max_pages") or 40)
    if max_pages <= 0:
        max_pages = 40

    effective_proxy = proxy or config.get("proxy")

    out: list[RawJob] = []

    for page in range(1, max_pages + 1):
        url = f"{base_url}/web/job/job_list"
        data = _post_form_json(
            url,
            # The official frontend uses `pageIndex` for paging (not `page`).
            {"pageIndex": page, "pageSize": page_size, "recruitType": recruit_type},
            proxy=effective_proxy,
        )

        if not isinstance(data, list) or not data:
            break

        for it in data:
            if not isinstance(it, dict):
                continue

            title = (it.get("positionName") or it.get("positionNameOpen") or "").strip()
            pos_id = it.get("positionId") or it.get("id")
            if not title or not pos_id:
                continue

            city = (it.get("workCity") or None)
            published_at = parse_dt(it.get("formatPublishTime") or it.get("publishTime") or None)

            excerpt = _strip_html(it.get("qualification") or None)
            excerpt = clamp_excerpt(excerpt)

            # Direct job page exists (the HTML is rendered by JS, still a valid official click-through).
            source_url = f"{base_url}/web/job/job_info/{pos_id}"

            out.append(
                RawJob(
                    source_url=source_url,
                    title=title,
                    company_name=company_name,
                    city=str(city).strip() if city else None,
                    published_at=published_at,
                    excerpt=excerpt,
                    tags=[],
                )
            )

    # De-dup by source_url
    seen = set()
    deduped: list[RawJob] = []
    for rj in out:
        if rj.source_url in seen:
            continue
        seen.add(rj.source_url)
        deduped.append(rj)
    return deduped
