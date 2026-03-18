from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship()


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, unique=True, index=True)
    parent_company_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )    # Organization type: 央企/国企/民企/研究所/银行/互联网大厂/...
    company_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Industry sector: 能源与电力/电池与新能源/银行与金融科技/科技与软件/...
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Headquarters / core R&D location (free text, e.g. 北京/上海/深圳/全国).
    hq_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Focus hiring directions (tech): free text, keep short (e.g. 后端/数据/架构/项目管理/电池研发/BMS).
    focus_directions: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Official recruitment / application entrypoint (网申入口).
    recruitment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    company_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Salary info is best-effort; many sources don't provide it.
    salary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Salary range normalized to "k RMB per month" when parseable (e.g. 20-35k).
    salary_min_k: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    salary_max_k: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    company: Mapped[Company | None] = relationship()


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    job_posting_id: Mapped[str] = mapped_column(Text, ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(Text)  # official/import/...
    # Connector kind used to fetch this posting (tencent/kuaishou/iguopin/jd/rss/html_list/...).
    source_kind: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    job_posting: Mapped[JobPosting] = relationship()


class CrawlSource(Base):
    __tablename__ = "crawl_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(Text)  # greenhouse/lever/rss/html_list
    name: Mapped[str] = mapped_column(Text, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    owner_user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    job_posting_id: Mapped[str | None] = mapped_column(Text, ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True, index=True)

    company_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_text: Mapped[str] = mapped_column(Text)
    city_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    stage: Mapped[str] = mapped_column(Text, nullable=False, default="not_applied", server_default="not_applied", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_user_id])
    job_posting: Mapped[JobPosting | None] = relationship()


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(Text, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship()




