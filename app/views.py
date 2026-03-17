from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def fmt_dt(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return "-"
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    # Asia/Shanghai (UTC+8) without extra dependencies.
    dt = dt.astimezone(timezone(timedelta(hours=8)))
    return dt.strftime(fmt)


templates.env.filters["fmt_dt"] = fmt_dt

