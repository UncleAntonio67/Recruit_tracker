from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Company, CrawlSource, User
from app.ui_options import HQ_LOCATION_OPTIONS
from app.views import templates

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_class=HTMLResponse)
def companies_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    company_type: str | None = Query(default=None),
    hq: str | None = Query(default=None),
    # Keep as string because checkbox forms can submit empty/multiple values; avoid 422.
    has_entry: str | None = Query(default="1"),
    page: int = Query(default=1, ge=1, le=5000),
    show_import: str | None = Query(default=None),
) -> HTMLResponse:
    page_size = 100
    stmt = select(Company).order_by(Company.name.asc())

    conds = []
    if q:
        conds.append(Company.name.ilike(f"%{q.strip()}%"))
    if industry:
        conds.append(Company.industry == industry.strip())
    if company_type:
        conds.append(Company.company_type == company_type.strip())
    if hq:
        hv = hq.strip()
        if hv == "其他":
            # Best-effort: anything that doesn't mention the core cities or 全国/远程.
            core = ["北京", "上海", "广州", "深圳", "全国", "远程"]
            conds.append(Company.hq_location.is_not(None))
            conds.append(Company.hq_location != "")
            for c in core:
                conds.append(~Company.hq_location.ilike(f"%{c}%"))
        else:
            conds.append(Company.hq_location.ilike(f"%{hv}%"))
    he = (has_entry or "").strip()
    if he == "1":
        conds.append(Company.recruitment_url.is_not(None))
        conds.append(Company.recruitment_url != "")

    if conds:
        stmt = stmt.where(and_(*conds))

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))

    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size + 1)).scalars().all()
    companies = rows[:page_size]
    has_next = len(rows) > page_size
    has_prev = page > 1
    prev_url = str(request.url.include_query_params(page=page - 1)) if has_prev else ""
    next_url = str(request.url.include_query_params(page=page + 1)) if has_next else ""

    # For filter dropdowns.
    industries = [r[0] for r in db.execute(select(Company.industry).where(Company.industry.is_not(None)).distinct()).all()]
    industries = sorted([x for x in industries if x])
    types = [r[0] for r in db.execute(select(Company.company_type).where(Company.company_type.is_not(None)).distinct()).all()]
    types = sorted([x for x in types if x])

    sources_summary = None
    sources_recent = []
    if user and user.is_admin:
        total_sources = int(db.execute(select(func.count()).select_from(select(CrawlSource.id).subquery())).scalar_one() or 0)
        enabled_sources = int(
            db.execute(select(func.count()).select_from(select(CrawlSource.id).where(CrawlSource.enabled == True).subquery())).scalar_one()  # noqa: E712
            or 0
        )
        ok_sources = int(
            db.execute(
                select(func.count()).select_from(
                    select(CrawlSource.id).where(and_(CrawlSource.last_status == "ok", CrawlSource.enabled == True)).subquery()  # noqa: E712
                )
            ).scalar_one()
            or 0
        )
        error_sources = int(
            db.execute(
                select(func.count()).select_from(
                    select(CrawlSource.id).where(and_(CrawlSource.last_status == "error", CrawlSource.enabled == True)).subquery()  # noqa: E712
                )
            ).scalar_one()
            or 0
        )
        last_run_at = db.execute(select(func.max(CrawlSource.last_run_at))).scalar_one()

        sources_summary = {
            "total": total_sources,
            "enabled": enabled_sources,
            "ok": ok_sources,
            "error": error_sources,
            "last_run_at": last_run_at,
        }
        sources_recent = db.execute(select(CrawlSource).order_by(CrawlSource.created_at.desc()).limit(12)).scalars().all()

    return templates.TemplateResponse(
        "companies_list.html",
        {
            "request": request,
            "user": user,
            "companies": companies,
            "show_import": bool((show_import or "").strip()),
            "filters": {
                "q": q or "",
                "industry": industry or "",
                "company_type": company_type or "",
                "hq": hq or "",
                "has_entry": "1" if he == "1" else "",
            },
            "industry_options": industries,
            "company_type_options": types,
            "hq_options": HQ_LOCATION_OPTIONS,
            "sources_summary": sources_summary,
            "sources_recent": sources_recent,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )


@router.get("/{company_id}", response_class=HTMLResponse)
def company_detail(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    c = db.get(Company, company_id)
    if not c:
        return templates.TemplateResponse("404.html", {"request": request, "user": user}, status_code=404)

    return templates.TemplateResponse(
        "company_detail.html",
        {
            "request": request,
            "user": user,
            "company": c,
            "hq_options": HQ_LOCATION_OPTIONS,
        },
    )


@router.post("/{company_id}")
def company_update(
    request: Request,
    company_id: str,
    name: str = Form(...),
    company_type: str | None = Form(default=None),
    industry: str | None = Form(default=None),
    hq_location: str | None = Form(default=None),
    hq_location_other: str | None = Form(default=None),
    focus_directions: str | None = Form(default=None),
    website: str | None = Form(default=None),
    recruitment_url: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    c = db.get(Company, company_id)
    if not c:
        return RedirectResponse(url="/companies", status_code=302)

    c.name = name.strip()
    c.company_type = company_type.strip() if company_type and company_type.strip() else None
    c.industry = industry.strip() if industry and industry.strip() else None
    picked_hq = (hq_location_other or "").strip() or (hq_location or "").strip() or ""
    c.hq_location = picked_hq if picked_hq else None
    c.focus_directions = focus_directions.strip() if focus_directions and focus_directions.strip() else None
    c.website = website.strip() if website and website.strip() else None
    c.recruitment_url = recruitment_url.strip() if recruitment_url and recruitment_url.strip() else None
    db.add(c)
    db.commit()
    return RedirectResponse(url=f"/companies/{c.id}", status_code=302)


@router.post("/{company_id}/seed_source")
def company_seed_source(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    """Create/update a CrawlSource for this company's official entrypoint.

    This lets the user maintain a company list and "逐个"补齐官网入口后，一键生成采集源。
    """

    c = db.get(Company, company_id)
    if not c:
        return RedirectResponse(url="/companies", status_code=302)
    if not c.recruitment_url or not c.recruitment_url.strip():
        return RedirectResponse(url=f"/companies/{c.id}", status_code=302)

    rec_url = c.recruitment_url.strip()
    src_name = f"Official:{c.name}"

    kind = "html_list"
    cfg: dict = {
        "list_url": rec_url,
        "company_name": c.name,
        "url_contains": ["job", "jobs", "career", "careers", "recruit", "zhaopin", "hr", "join"],
        "url_excludes": ["campus", "intern", "xiaozhao", "校园", "校招", "实习"],
        "title_contains": ["后端", "前端", "全栈", "开发", "工程师", "架构", "数据", "算法", "测试", "金融科技", "新能源", "储能", "锂电", "电池", "化工", "研发", "项目"],
        "max_items": 200,
        "source_type": "official",
    }

    # If it's a Beisen Zhiye portal, prefer the structured API connector.
    try:
        from urllib.parse import urlparse

        p = urlparse(rec_url)
        host = (p.netloc or "").strip()
        if host.endswith(".m.zhiye.com"):
            kind = "m_zhiye"
            cfg = {"base_url": f"{p.scheme}://{host}", "company_name": c.name, "jc": 1, "page_size": 30, "max_pages": 40, "source_type": "official"}
        elif host.endswith(".zhiye.com"):
            sub = host[: -len(".zhiye.com")]
            if sub:
                kind = "m_zhiye"
                cfg = {
                    "base_url": f"{p.scheme}://{sub}.m.zhiye.com",
                    "company_name": c.name,
                    "jc": 1,
                    "page_size": 30,
                    "max_pages": 40,
                    "source_type": "official",
                }
        elif host.endswith(".hotjob.cn") or host == "hotjob.cn":
            # Hotjob official portal (wecruit public endpoints).
            kind = "hotjob"
            base = f"{p.scheme or 'https'}://{host}" if host else rec_url
            cfg = {
                "base_url": base.replace("http://", "https://"),
                "company_name": c.name,
                "recruit_type": 2,  # 社招
                "page_size": 12,
                "max_pages": 12,
                "source_type": "official",
            }
    except Exception:
        pass

    existing = db.execute(select(CrawlSource).where(CrawlSource.name == src_name)).scalar_one_or_none()
    if existing:
        existing.kind = kind
        existing.enabled = True
        existing.config = cfg
        db.add(existing)
    else:
        db.add(CrawlSource(kind=kind, name=src_name, enabled=True, config=cfg))

    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=302)
