from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

from app.crawler.http import get_text
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, sha1


class _JobBlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._div_depth = 0
        self._buf: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        start = self.get_starttag_text() or f"<{tag}>"
        if self._div_depth == 0 and tag.lower() == "div":
            class_value = ""
            for key, value in attrs:
                if key.lower() == "class" and value:
                    class_value = str(value)
                    break
            classes = {x.strip() for x in class_value.split() if x.strip()}
            if "s_f6c2" in classes:
                self._div_depth = 1
                self._buf = [start]
                return

        if self._div_depth > 0:
            if tag.lower() == "div":
                self._div_depth += 1
            self._buf.append(start)

    def handle_endtag(self, tag: str) -> None:
        if self._div_depth <= 0:
            return
        self._buf.append(f"</{tag}>")
        if tag.lower() == "div":
            self._div_depth -= 1
        if self._div_depth == 0:
            self.blocks.append("".join(self._buf))
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._div_depth > 0 and data:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._div_depth > 0:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._div_depth > 0:
            self._buf.append(f"&#{name};")


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _match_first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, flags=re.I | re.S)
    if not m:
        return None
    return _strip_html(m.group(1))


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    """EVE Energy social recruitment page connector.

    The public page is server-rendered and contains each social-hiring position
    in a repeated `div.s_f6c2` block with full description and an apply link.
    """

    page_url = (
        str(config.get("page_url") or "").strip()
        or str(config.get("list_url") or "").strip()
        or "https://www.evebattery.com/social-recruitment"
    )
    company_name = str(config.get("company_name") or "亿纬锂能").strip() or "亿纬锂能"
    effective_proxy = proxy or (str(config.get("proxy") or "").strip() or None)

    html = get_text(page_url, proxy=effective_proxy, timeout=60)
    parser = _JobBlockParser()
    parser.feed(html)

    out: list[RawJob] = []
    seen_urls: set[str] = set()
    for block in parser.blocks:
        title = _match_first(r"<h6[^>]*>(.*?)</h6>", block)
        if not title:
            continue

        info_values = re.findall(r'<div[^>]+class="[^"]*s_f6c2rnr[^"]*"[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        city = None
        meta_parts: list[str] = []
        for raw_info in info_values:
            info = _strip_html(raw_info)
            if not info:
                continue
            meta_parts.append(info)
            if "工作地点" in info and "：" in info:
                city = info.split("：", 1)[1].strip() or None

        desc_html = _match_first(r'<div[^>]+class="[^"]*s_f6c2botbjq[^"]*"[^>]*>(.*?)</div>', block) or ""
        excerpt_parts = [x for x in meta_parts if x]
        if desc_html:
            excerpt_parts.append(desc_html)
        excerpt = clamp_excerpt("\n".join(excerpt_parts))

        apply_url = _match_first(r'<a[^>]+href="([^"]+)"', block)
        stable_id = sha1(f"{title}|{city or ''}")[:16]
        source_url = f"{page_url}#job-{stable_id}"
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        tags = []
        if apply_url and apply_url != source_url:
            tags.append(f"apply:{apply_url}")

        out.append(
            RawJob(
                source_url=source_url,
                title=title,
                company_name=company_name,
                city=city,
                excerpt=excerpt,
                tags=tags,
            )
        )

    return out
