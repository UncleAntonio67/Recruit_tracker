from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from app.crawler.http import get_text
from app.crawler.job_types import RawJob


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_a = False
        self._href: str | None = None
        self._text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        href = None
        for k, v in attrs:
            if k.lower() == "href" and v:
                href = v
                break
        if not href:
            return
        self._in_a = True
        self._href = href
        self._text_parts = []

    def handle_endtag(self, tag: str):
        if tag.lower() != "a":
            return
        if not self._in_a or not self._href:
            self._in_a = False
            self._href = None
            self._text_parts = []
            return
        text = "".join(self._text_parts).strip()
        if text:
            self.links.append((self._href, text))
        self._in_a = False
        self._href = None
        self._text_parts = []

    def handle_data(self, data: str):
        if self._in_a and data:
            self._text_parts.append(data)


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """Experimental generic HTML list scraper (dependency-free).

    It extracts all anchor links and then filters them.

    Required config keys:
    - list_url: str

    Optional config keys:
    - base_url: str
    - company_name: str
    - city: str
    - url_contains: [str]
    - url_excludes: [str]
    - title_contains: [str]
    - title_excludes: [str]
    - max_items: int
    - source_type: str
    - proxy: str (e.g. http://127.0.0.1:7890)
    """

    list_url = config["list_url"]
    base_url = config.get("base_url") or list_url

    effective_proxy = proxy or config.get("proxy")
    html = get_text(list_url, proxy=effective_proxy)

    p = _LinkParser()
    p.feed(html)

    url_contains = config.get("url_contains") or []
    url_excludes = config.get("url_excludes") or []
    title_contains = config.get("title_contains") or []
    title_excludes = config.get("title_excludes") or []
    max_items = int(config.get("max_items") or 200)

    out: list[RawJob] = []
    for href, text in p.links:
        u = urljoin(base_url, href)

        if url_contains and not any(x in u for x in url_contains):
            continue
        if any(x in u for x in url_excludes):
            continue

        t = " ".join(text.split())
        if title_contains and not any(x.lower() in t.lower() for x in title_contains):
            continue
        if any(x.lower() in t.lower() for x in title_excludes):
            continue

        out.append(
            RawJob(
                source_url=u,
                title=t,
                company_name=config.get("company_name"),
                city=config.get("city"),
                tags=[],
            )
        )
        if len(out) >= max_items:
            break

    return out
