from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.crawler.utils import find_salary_text, parse_dt, parse_salary_k
from app.crawler.prefill import prefill_from_url
from app.db import get_db
from app.models import Application, Company, JobPosting, JobSource, User
from app.views import templates

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _company_query_tokens(text: str) -> list[str]:
    """Expand common group suffix variants to improve matching.

    Keep Chinese literals as unicode escapes to avoid Windows console encoding pitfalls.
    """

    s = (text or "").strip()
    if not s:
        return []

    toks = [s]
    suffixes = [
        "\u96c6\u56e2\u6709\u9650\u516c\u53f8",  # 集团有限公司
        "\u96c6\u56e2\u80a1\u4efd\u6709\u9650\u516c\u53f8",  # 集团股份有限公司
        "\u96c6\u56e2",  # 集团
        "\u6709\u9650\u516c\u53f8",  # 有限公司
        "\u80a1\u4efd\u6709\u9650\u516c\u53f8",  # 股份有限公司
    ]
    for suf in suffixes:
        if s.endswith(suf) and len(s) > len(suf):
            toks.append(s[: -len(suf)].strip())
            break

    # "一汽（红旗）" -> "一汽", "红旗"
    lpar = "\uff08"  # （
    rpar = "\uff09"  # ）
    if lpar in s and rpar in s:
        left = s.split(lpar, 1)[0].strip()
        mid = s.split(lpar, 1)[1].split(rpar, 1)[0].strip()
        if left:
            toks.append(left)
        if mid:
            toks.append(mid)

    seen = set()
    out: list[str] = []
    for t in toks:
        tt = t.strip()
        if not tt or tt in seen:
            continue
        seen.add(tt)
        out.append(tt)
    return out


def _city_options(db: Session) -> list[str]:
    city_rows = db.execute(
        select(JobPosting.city, func.count(JobPosting.id))
        .where(JobPosting.city.is_not(None))
        .group_by(JobPosting.city)
        .order_by(func.count(JobPosting.id).desc())
        .limit(300)
    ).all()
    counts: dict[str, int] = {}
    for raw_city, n in city_rows:
        if not raw_city:
            continue
        s = str(raw_city).strip()
        if not s:
            continue
        for part in s.replace(",", "/").replace("\uff0c", "/").split("/"):
            c = part.strip()
            if not c or len(c) > 20:
                continue
            counts[c] = counts.get(c, 0) + int(n or 1)

    preferred = ["北京", "上海", "广州", "深圳"]
    others = sorted([c for c in counts.keys() if c not in preferred], key=lambda x: (-counts.get(x, 0), x))
    return preferred + others[:40]


@router.get("", response_class=HTMLResponse)
def jobs_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(default=None),
    city: str | None = Query(default=None),
    company: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    since_days: int = Query(default=180, ge=1, le=3650),
    published_from: str | None = Query(default=None),
    published_to: str | None = Query(default=None),
    salary_min_k: int | None = Query(default=None, ge=0, le=1000),
    salary_max_k: int | None = Query(default=None, ge=0, le=1000),
    salary_only: int | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=5000),
) -> HTMLResponse:
    page_size = 200

    fetch_cap = 2000
    fetch_limit = min(fetch_cap, max(page_size, page * page_size) + 1)

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
        toks = _company_query_tokens(company)
        if toks:
            conds.append(or_(*[Company.name.ilike(f"%{t}%") for t in toks]))
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
            conds.append(exists(select(1).where(and_(JobSource.job_posting_id == JobPosting.id, JobSource.source_name == sn))))
    if source_type:
        st = source_type.strip()
        if st:
            conds.append(exists(select(1).where(and_(JobSource.job_posting_id == JobPosting.id, JobSource.source_type == st))))

    # Salary filtering (k RMB/month). Many sources won't have salaries, so these are optional filters.
    if salary_only:
        conds.append(or_(JobPosting.salary_min_k.is_not(None), JobPosting.salary_max_k.is_not(None), JobPosting.salary_text.is_not(None)))
    if salary_min_k is not None:
        v = int(salary_min_k)
        conds.append(
            or_(
                and_(JobPosting.salary_min_k.is_not(None), JobPosting.salary_min_k >= v),
                and_(JobPosting.salary_max_k.is_not(None), JobPosting.salary_max_k >= v),
            )
        )
    if salary_max_k is not None:
        v = int(salary_max_k)
        conds.append(
            or_(
                and_(JobPosting.salary_min_k.is_not(None), JobPosting.salary_min_k <= v),
                and_(JobPosting.salary_max_k.is_not(None), JobPosting.salary_max_k <= v),
            )
        )

    if conds:
        stmt = stmt.where(and_(*conds))

    rows = db.execute(stmt).all()
    items = [{"job": job, "company": comp} for job, comp in rows]

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
                "company": company or "",
                "industry": industry or "",
                "source_name": source_name or "",
                "source_type": source_type or "",
                "since_days": str(since_days or ""),
                "published_from": published_from or "",
                "published_to": published_to or "",
                "salary_min_k": "" if salary_min_k is None else str(salary_min_k),
                "salary_max_k": "" if salary_max_k is None else str(salary_max_k),
                "salary_only": "1" if salary_only else "",
            },
            "options": {
                "industries": industries,
                "source_names": source_names,
                "source_types": source_types,
                "cities": _city_options(db),
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
    url: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    prefill = {}
    if url and str(url).strip():
        try:
            prefill = prefill_from_url(str(url).strip())
        except Exception:
            prefill = {"source_url": str(url).strip()}
    return templates.TemplateResponse("import_job.html", {"request": request, "user": user, "prefill": prefill})


@router.post("/import")
def import_post(
    request: Request,
    title: str = Form(...),
    city: str | None = Form(default=None),
    company_name: str | None = Form(default=None),
    salary_text: str | None = Form(default=None),
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
        if name:
            comp = db.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
            if not comp:
                comp = Company(name=name)
                db.add(comp)
                db.flush()

    job = JobPosting(
        company_id=comp.id if comp else None,
        title=title.strip(),
        city=city.strip() if city else None,
        salary_text=(salary_text.strip() if salary_text and salary_text.strip() else None),
        published_at=parse_dt(published_at) if published_at else None,
        excerpt=(excerpt.strip()[:600] if excerpt else None),
        status="active",
    )
    # Normalize salary fields when possible.
    if job.salary_text:
        mn, mx = parse_salary_k(job.salary_text)
        job.salary_min_k = mn
        job.salary_max_k = mx
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
        stage="未投递",
        priority=3,
    )
    db.add(app)
    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)
