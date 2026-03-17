from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.crawler.utils import KEYWORD_TAGS, parse_dt
from app.db import get_db
from app.models import Application, Company, JobPosting, JobSource, User
from app.views import templates

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_class=HTMLResponse)
def jobs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(default=None),
    city: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    company: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    since_days: int = Query(default=180, ge=1, le=3650),
    published_from: str | None = Query(default=None),
    published_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=5000),
) -> HTMLResponse:
    page_size = 200

    # Tag filtering stays in Python for SQLite portability.
    fetch_cap = 2000
    fetch_limit = min(fetch_cap, max(page_size, page * page_size * (3 if tag else 1)) + 1)

    stmt = (
        select(JobPosting, Company)
        .outerjoin(Company, Company.id == JobPosting.company_id)
        .where(JobPosting.status == "active")
        .order_by(func.coalesce(JobPosting.published_at, JobPosting.last_seen_at).desc())
        .limit(fetch_limit)
    )

    conds = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(JobPosting.title.ilike(like), Company.name.ilike(like), JobPosting.excerpt.ilike(like)))
    if city:
        # Use contains matching to support multi-city fields like "北京/上海".
        conds.append(JobPosting.city.ilike(f"%{city.strip()}%"))
    if company:
        conds.append(Company.name.ilike(f"%{company.strip()}%"))
    if industry:
        conds.append(Company.industry == industry.strip())

    if since_days:
        cutoff = datetime.now(UTC) - timedelta(days=int(since_days))
        conds.append(func.coalesce(JobPosting.published_at, JobPosting.last_seen_at) >= cutoff)

    pf = parse_dt(published_from) if published_from else None
    pt = parse_dt(published_to) if published_to else None
    if pf:
        conds.append(JobPosting.published_at.is_not(None))
        conds.append(JobPosting.published_at >= pf)
    if pt:
        # Make date-only inputs inclusive by treating end as [to, to+1d).
        if pt.hour == 0 and pt.minute == 0 and pt.second == 0 and pt.microsecond == 0:
            pt = pt + timedelta(days=1)
        conds.append(JobPosting.published_at.is_not(None))
        conds.append(JobPosting.published_at < pt)

    if source_name:
        sn = source_name.strip()
        if sn:
            conds.append(
                exists(select(1).where(and_(JobSource.job_posting_id == JobPosting.id, JobSource.source_name == sn)))
            )
    if source_type:
        st = source_type.strip()
        if st:
            conds.append(
                exists(select(1).where(and_(JobSource.job_posting_id == JobPosting.id, JobSource.source_type == st)))
            )

    if conds:
        stmt = stmt.where(and_(*conds))

    rows = db.execute(stmt).all()
    items = [{"job": job, "company": comp} for job, comp in rows]

    # Tag filtering is done in Python for SQLite portability.
    if tag:
        known_tag_keys = {t for t, _kws in KEYWORD_TAGS}
        parts = [x.strip() for x in (tag or "").replace("，", ",").split(",") if x.strip()]

        def _resolve_tag_key(token: str) -> str:
            tok = token.strip()
            if not tok:
                return ""
            low = tok.lower()
            if tok in known_tag_keys:
                return tok
            if low in known_tag_keys:
                return low
            for tag_key, kws in KEYWORD_TAGS:
                for kw in kws:
                    if low == str(kw).strip().lower():
                        return tag_key
            return tok

        want = [_resolve_tag_key(p) for p in parts]
        want = [w for w in want if w]
        if want:
            items = [it for it in items if any(w in (it["job"].tags or []) for w in want)]

    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    has_next = len(items) > (start + page_size)
    has_prev = page > 1
    prev_url = str(request.url.include_query_params(page=page - 1)) if has_prev else ""
    next_url = str(request.url.include_query_params(page=page + 1)) if has_next else ""

    industries = [r[0] for r in db.execute(select(Company.industry).where(Company.industry.is_not(None)).distinct()).all()]
    industries = sorted([x for x in industries if x])
    source_names = [r[0] for r in db.execute(select(JobSource.source_name).where(JobSource.source_name.is_not(None)).distinct()).all()]
    source_names = sorted([x for x in source_names if x])
    source_types = [r[0] for r in db.execute(select(JobSource.source_type).where(JobSource.source_type.is_not(None)).distinct()).all()]
    source_types = sorted([x for x in source_types if x])

    return templates.TemplateResponse(
        "jobs_list.html",
        {
            "request": request,
            "user": user,
            "items": page_items,
            "filters": {
                "q": q or "",
                "city": city or "",
                "tag": tag or "",
                "company": company or "",
                "industry": industry or "",
                "source_name": source_name or "",
                "source_type": source_type or "",
                "since_days": str(since_days or ""),
                "published_from": published_from or "",
                "published_to": published_to or "",
            },
            "options": {
                "industries": industries,
                "source_names": source_names,
                "source_types": source_types,
                "since_days": [7, 30, 90, 180, 365, 730],
            },
            "page": page,
            "has_next": has_next,
            "has_prev": has_prev,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )


@router.get("/import", response_class=HTMLResponse)
def import_page(
    request: Request,
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse("import_job.html", {"request": request, "user": user})


@router.post("/import")
def import_post(
    request: Request,
    title: str = Form(...),
    city: str | None = Form(default=None),
    company_name: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    source_url: str = Form(...),
    published_at: str | None = Form(default=None),
    excerpt: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    src_url = source_url.strip()

    existing = db.execute(select(JobSource).where(JobSource.source_url == src_url)).scalar_one_or_none()
    if existing:
        return RedirectResponse(url=f"/jobs/{existing.job_posting_id}", status_code=302)

    comp = None
    if company_name:
        name = company_name.strip()
        comp = db.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
        if not comp:
            comp = Company(name=name)
            db.add(comp)
            db.flush()

    job = JobPosting(
        company_id=comp.id if comp else None,
        title=title.strip(),
        city=city.strip() if city else None,
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
        published_at=parse_dt(published_at) if published_at else None,
        excerpt=(excerpt.strip()[:600] if excerpt else None),
        status="active",
    )
    db.add(job)
    db.flush()

    src = JobSource(
        job_posting_id=job.id,
        source_type="import",
        source_name="manual",
        source_url=src_url,
    )
    db.add(src)
    db.commit()

    return RedirectResponse(url=f"/jobs/{job.id}", status_code=302)


@router.get("/{job_id}", response_class=HTMLResponse)
def job_detail(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    job = db.get(JobPosting, job_id)
    if not job:
        return templates.TemplateResponse("404.html", {"request": request, "user": user}, status_code=404)

    comp = db.get(Company, job.company_id) if job.company_id else None
    sources = db.execute(select(JobSource).where(JobSource.job_posting_id == job.id)).scalars().all()

    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "user": user, "job": job, "company": comp, "sources": sources},
    )


@router.post("/{job_id}/apply")
def create_application_from_job(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    channel: str | None = Form(default=None),
) -> RedirectResponse:
    job = db.get(JobPosting, job_id)
    if not job:
        return RedirectResponse(url="/jobs", status_code=302)

    comp = db.get(Company, job.company_id) if job.company_id else None
    src_url = db.execute(select(JobSource.source_url).where(JobSource.job_posting_id == job.id)).scalar_one_or_none()

    app = Application(
        owner_user_id=user.id,
        job_posting_id=job.id,
        company_text=comp.name if comp else None,
        title_text=job.title,
        city_text=job.city,
        source_url=src_url,
        channel=channel.strip() if channel else None,
        stage="not_applied",
        priority=3,
    )
    db.add(app)
    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)
