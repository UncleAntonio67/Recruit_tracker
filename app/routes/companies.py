from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Company, User
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
    has_entry: int | None = Query(default=1),
) -> HTMLResponse:
    stmt = select(Company).order_by(Company.name.asc())

    conds = []
    if q:
        conds.append(Company.name.ilike(f"%{q.strip()}%"))
    if industry:
        conds.append(Company.industry == industry.strip())
    if company_type:
        conds.append(Company.company_type == company_type.strip())
    if hq:
        conds.append(Company.hq_location.ilike(f"%{hq.strip()}%"))
    if has_entry:
        conds.append(Company.recruitment_url.is_not(None))
        conds.append(Company.recruitment_url != "")

    if conds:
        stmt = stmt.where(and_(*conds))

    companies = db.execute(stmt).scalars().all()

    # For filter dropdowns.
    industries = [r[0] for r in db.execute(select(Company.industry).where(Company.industry.is_not(None)).distinct()).all()]
    industries = sorted([x for x in industries if x])
    types = [r[0] for r in db.execute(select(Company.company_type).where(Company.company_type.is_not(None)).distinct()).all()]
    types = sorted([x for x in types if x])

    return templates.TemplateResponse(
        "companies_list.html",
        {
            "request": request,
            "user": user,
            "companies": companies,
            "filters": {
                "q": q or "",
                "industry": industry or "",
                "company_type": company_type or "",
                "hq": hq or "",
                "has_entry": "1" if has_entry else "",
            },
            "industry_options": industries,
            "company_type_options": types,
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
    c.hq_location = hq_location.strip() if hq_location and hq_location.strip() else None
    c.focus_directions = focus_directions.strip() if focus_directions and focus_directions.strip() else None
    c.website = website.strip() if website and website.strip() else None
    c.recruitment_url = recruitment_url.strip() if recruitment_url and recruitment_url.strip() else None
    db.add(c)
    db.commit()
    return RedirectResponse(url=f"/companies/{c.id}", status_code=302)
