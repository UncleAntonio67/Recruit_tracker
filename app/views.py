from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import re

from fastapi.templating import Jinja2Templates
from markupsafe import escape

templates = Jinja2Templates(directory="app/templates")

_TZ_SH = timezone(timedelta(hours=8))


def _coerce_dt(value: object) -> datetime | None:
    """Best-effort coercion for template formatting.

    Defensive: legacy imports or scraped data can occasionally store strings or
    naive datetimes. Templates should not raise 500 due to a single bad record.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            # Support common ISO-like strings (including a trailing "Z").
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def fmt_dt(value: object, fmt: str = "%Y-%m-%d %H:%M") -> str:
    dt = _coerce_dt(value)
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    # Asia/Shanghai (UTC+8) without extra dependencies.
    dt = dt.astimezone(_TZ_SH)
    return dt.strftime(fmt)


templates.env.filters["fmt_dt"] = fmt_dt


def fmt_dt_local(value: object) -> str:
    """Format for <input type="datetime-local"> (no timezone suffix)."""

    dt = _coerce_dt(value)
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(_TZ_SH)
    return dt.strftime("%Y-%m-%dT%H:%M")


templates.env.filters["fmt_dt_local"] = fmt_dt_local


def fmt_source_type(value: str | None) -> str:
    if not value:
        return "-"
    from app.ui_options import SOURCE_TYPE_LABELS

    v = str(value).strip()
    return SOURCE_TYPE_LABELS.get(v, v)


templates.env.filters["fmt_source_type"] = fmt_source_type


def fmt_source_kind(value: str | None) -> str:
    if not value:
        return "-"
    from app.ui_options import SOURCE_KIND_LABELS

    v = str(value).strip()
    return SOURCE_KIND_LABELS.get(v, v)


templates.env.filters["fmt_source_kind"] = fmt_source_kind


def job_sections(excerpt: str | None) -> list[dict]:
    """Best-effort: split a job excerpt into readable sections.

    We do not store full-page snapshots. This only formats the saved excerpt text.
    """

    if not excerpt:
        return []

    try:
        text = str(excerpt).replace("\r\n", "\n").replace("\r", "\n").strip()
    except Exception:
        return []
    if not text:
        return []

    # Normalize some common full-width punctuation.
    text = text.replace("\uFF1A", ":")  # ：
    header_map: list[tuple[str, list[str]]] = [
        (
            "\u5c97\u4f4d\u804c\u8d23",
            [
                "\u5c97\u4f4d\u804c\u8d23",
                "\u5de5\u4f5c\u804c\u8d23",
                "\u804c\u8d23",
                "\u4e3b\u8981\u804c\u8d23",
                "\u5de5\u4f5c\u5185\u5bb9",
                "\u804c\u4f4d\u63cf\u8ff0",
            ],
        ),
        (
            "\u4efb\u804c\u8981\u6c42",
            [
                "\u4efb\u804c\u8981\u6c42",
                "\u5c97\u4f4d\u8981\u6c42",
                "\u804c\u4f4d\u8981\u6c42",
                "\u4efb\u804c\u8d44\u683c",
                "\u4efb\u804c\u8d44\u683c\u8981\u6c42",
                "\u8981\u6c42",
            ],
        ),
        ("\u52a0\u5206\u9879", ["\u52a0\u5206\u9879", "\u4f18\u5148", "\u4f18\u5148\u8003\u8651"]),
        ("\u798f\u5229\u4e0e\u5176\u4ed6", ["\u798f\u5229", "\u85aa\u916c\u798f\u5229", "\u5176\u4ed6", "\u5de5\u4f5c\u5730\u70b9"]),
    ]

    def match_header(line: str) -> str | None:
        s = line.strip()
        if not s:
            return None
        # Heuristic: short line that contains a known header keyword.
        if len(s) > 40:
            return None
        for title, keys in header_map:
            for k in keys:
                if k in s:
                    return title
        return None

    # Common bullet patterns:
    # - "-", "*", "•"
    # - "1.", "1)"
    # - circled numbers ①②③...
    bullet_re = re.compile(r"^\s*(?:[-*]|\u2022|\d+[.)]|[\u2460-\u2473])\s*")

    sections: list[dict] = []
    cur = {"title": "\u6982\u8981", "items": []}

    try:
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            h = match_header(line)
            if h:
                # Flush current section if it has content.
                if cur["items"]:
                    sections.append(cur)
                cur = {"title": h, "items": []}
                continue
            line = bullet_re.sub("", line).strip()
            if not line:
                continue
            cur["items"].append(line)
    except Exception:
        # Keep pages renderable even if a single weird excerpt breaks parsing.
        return []

    if cur["items"]:
        sections.append(cur)

    # Escape items for safe rendering in templates.
    out: list[dict] = []
    for sec in sections:
        items = [str(escape(x)) for x in sec["items"][:200]]
        out.append({"title": sec["title"], "items": items})
    return out


templates.env.filters["job_sections"] = job_sections

