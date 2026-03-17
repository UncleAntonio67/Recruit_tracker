from __future__ import annotations

import xml.etree.ElementTree as ET

from app.crawler.http import get_text
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt


def _first_text(el: ET.Element, tags: list[str]) -> str | None:
    for t in tags:
        child = el.find(t)
        if child is not None and child.text:
            return child.text.strip()
    return None


def fetch(feed_url: str, company_name: str | None = None, proxy: str | None = None) -> list[RawJob]:
    xml = get_text(feed_url, proxy=proxy)
    root = ET.fromstring(xml)

    out: list[RawJob] = []

    # RSS 2.0: channel/item
    for item in root.findall(".//item"):
        link = _first_text(item, ["link"])
        title = _first_text(item, ["title"])
        if not link or not title:
            continue

        pub = _first_text(item, ["pubDate", "date"])
        published_at = parse_dt(pub)
        desc = _first_text(item, ["description"])

        out.append(
            RawJob(
                source_url=link,
                title=title,
                company_name=company_name,
                published_at=published_at,
                excerpt=clamp_excerpt(desc),
                tags=[],
            )
        )

    # Atom: entry
    if not out:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            if title_el is None or not (title_el.text or "").strip():
                continue
            title = title_el.text.strip()

            link = None
            for link_el in entry.findall("atom:link", ns):
                href = link_el.attrib.get("href")
                if href:
                    link = href
                    break
            if not link:
                continue

            upd_el = entry.find("atom:updated", ns)
            published_at = parse_dt(upd_el.text.strip() if upd_el is not None and upd_el.text else None)

            sum_el = entry.find("atom:summary", ns)
            excerpt = clamp_excerpt(sum_el.text.strip() if sum_el is not None and sum_el.text else None)

            out.append(
                RawJob(
                    source_url=link,
                    title=title,
                    company_name=company_name,
                    published_at=published_at,
                    excerpt=excerpt,
                    tags=[],
                )
            )

    return out
