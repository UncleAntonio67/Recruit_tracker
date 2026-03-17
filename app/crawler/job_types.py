from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawJob:
    source_url: str
    title: str
    company_name: str | None = None
    city: str | None = None
    published_at: datetime | None = None
    excerpt: str | None = None
    department: str | None = None
    seniority: str | None = None
    tags: list[str] | None = None

