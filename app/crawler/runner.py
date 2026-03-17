from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.connectors import greenhouse, html_list, iguopin, jd, lever, rss, tencent, kuaishou
from app.crawler.job_types import RawJob
from app.crawler.utils import auto_tags, clamp_excerpt, fingerprint, is_recent, sha1, utcnow
from app.models import Company, CrawlSource, JobPosting, JobSource


def _upsert_company(db: Session, name: str | None) -> Company | None:
    if not name:
        return None
    n = name.strip()
    if not n:
        return None

    existing = db.execute(select(Company).where(Company.name == n)).scalar_one_or_none()
    if existing:
        return existing

    c = Company(name=n)
    db.add(c)
    db.flush()
    return c


def _ingest_job(db: Session, raw: RawJob, source_type: str, source_name: str | None, since_days: int) -> tuple[bool, str]:
    """Returns (created_new, job_id)."""

    if not raw.source_url or not raw.title:
        return (False, "")

    if not is_recent(raw.published_at, since_days=since_days):
        return (False, "")

    src_url = raw.source_url.strip()

    # De-dup by source url first.
    existing_src = db.execute(select(JobSource).where(JobSource.source_url == src_url)).scalar_one_or_none()
    if existing_src:
        job = db.get(JobPosting, existing_src.job_posting_id)
        if job:
            job.last_seen_at = utcnow()
            db.add(job)
        existing_src.fetched_at = utcnow()
        existing_src.content_hash = sha1((raw.excerpt or "") + (raw.title or ""))
        db.add(existing_src)
        db.commit()
        return (False, existing_src.job_posting_id)

    comp = _upsert_company(db, raw.company_name)

    fp = fingerprint(comp.name if comp else raw.company_name, raw.title, raw.city)

    job = db.execute(select(JobPosting).where(JobPosting.fingerprint == fp)).scalar_one_or_none()
    created = False

    if not job:
        job = JobPosting(
            company_id=comp.id if comp else None,
            title=raw.title.strip(),
            city=raw.city.strip() if raw.city else None,
            tags=[],
            department=raw.department,
            seniority=raw.seniority,
            published_at=raw.published_at,
            excerpt=clamp_excerpt(raw.excerpt),
            status="active",
            fingerprint=fp,
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        db.add(job)
        db.flush()
        created = True
    else:
        if not job.company_id and comp:
            job.company_id = comp.id
        if not job.city and raw.city:
            job.city = raw.city
        if not job.excerpt and raw.excerpt:
            job.excerpt = clamp_excerpt(raw.excerpt)
        if not job.published_at and raw.published_at:
            job.published_at = raw.published_at
        job.last_seen_at = utcnow()
        db.add(job)

    # Tags: merge + auto tags
    base_tags = (raw.tags or []) + (job.tags or [])
    job.tags = auto_tags(job.title, job.excerpt, base_tags=base_tags)
    db.add(job)

    js = JobSource(
        job_posting_id=job.id,
        source_type=source_type,
        source_name=source_name,
        source_url=src_url,
        fetched_at=utcnow(),
        content_hash=sha1((raw.excerpt or "") + (raw.title or "")),
    )
    db.add(js)
    db.commit()

    return (created, job.id)


def _passes_filters(raw: RawJob, cfg: dict) -> bool:
    text = f"{raw.title} {raw.excerpt or ''}".lower()

    include_kws = [str(x).lower() for x in (cfg.get("include_keywords") or []) if str(x).strip()]
    exclude_kws = [str(x).lower() for x in (cfg.get("exclude_keywords") or []) if str(x).strip()]
    city_allow = [str(x).strip() for x in (cfg.get("city_allowlist") or []) if str(x).strip()]

    if include_kws and not any(k in text for k in include_kws):
        return False
    if exclude_kws and any(k in text for k in exclude_kws):
        return False

    if city_allow and raw.city:
        if not any(a in raw.city for a in city_allow):
            return False

    return True


def run(db: Session, since_days: int = 180, only_enabled: bool = True) -> dict:
    sources_stmt = select(CrawlSource)
    if only_enabled:
        sources_stmt = sources_stmt.where(CrawlSource.enabled == True)  # noqa: E712

    sources = db.execute(sources_stmt.order_by(CrawlSource.created_at.asc())).scalars().all()

    stats = {
        "sources": len(sources),
        "jobs_created": 0,
        "jobs_seen": 0,
        "errors": 0,
        "per_source": [],
        "since_days": since_days,
        "ran_at": datetime.now(UTC).isoformat(),
    }

    for s in sources:
        created = 0
        seen = 0
        err = None

        try:
            cfg = s.config or {}
            raw_jobs: list[RawJob]

            if s.kind == "greenhouse":
                raw_jobs = greenhouse.fetch(board=cfg["board"], company_name=cfg.get("company_name") or s.name, proxy=cfg.get("proxy"))
                src_type = "official"
            elif s.kind == "lever":
                raw_jobs = lever.fetch(company=cfg["company"], company_name=cfg.get("company_name") or s.name, proxy=cfg.get("proxy"))
                src_type = "official"
            elif s.kind == "rss":
                raw_jobs = rss.fetch(feed_url=cfg["feed_url"], company_name=cfg.get("company_name") or s.name, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "official"
            elif s.kind == "html_list":
                raw_jobs = html_list.fetch(cfg, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "official"
            elif s.kind == "tencent":
                raw_jobs = tencent.fetch(cfg, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "official"
            elif s.kind == "kuaishou":
                raw_jobs = kuaishou.fetch(cfg, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "official"
            elif s.kind == "iguopin":
                raw_jobs = iguopin.fetch(cfg, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "aggregator"
            elif s.kind == "jd":
                raw_jobs = jd.fetch(cfg, proxy=cfg.get("proxy"))
                src_type = cfg.get("source_type") or "official"
            else:
                raise ValueError(f"unknown kind: {s.kind}")

            for rj in raw_jobs:
                seen += 1
                if not _passes_filters(rj, cfg):
                    continue
                c, _job_id = _ingest_job(
                    db,
                    rj,
                    source_type=src_type,
                    source_name=s.name,
                    since_days=since_days,
                )
                if c:
                    created += 1

            s.last_status = "ok"
            s.last_error = None
        except Exception as e:
            stats["errors"] += 1
            err = str(e)
            s.last_status = "error"
            s.last_error = err[:500]
        finally:
            s.last_run_at = utcnow()
            db.add(s)
            db.commit()

        stats["jobs_created"] += created
        stats["jobs_seen"] += seen
        stats["per_source"].append(
            {
                "name": s.name,
                "kind": s.kind,
                "seen": seen,
                "created": created,
                "status": s.last_status,
                "error": s.last_error,
            }
        )

    return stats




