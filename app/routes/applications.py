from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Application, ApplicationEvent, User
from app.views import templates

router = APIRouter(prefix="/applications", tags=["applications"])

STAGES = [
    "not_applied",
    "applied",
    "screening",
    "test",
    "interview1",
    "interview2",
    "interview3",
    "hr",
    "offer",
    "rejected",
    "dropped",
]


@router.get("", response_class=HTMLResponse)
def applications_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(default=None),
    stage: str | None = Query(default=None),
) -> HTMLResponse:
    stmt = (
        select(Application)
        .where(Application.owner_user_id == user.id)
        .order_by(Application.updated_at.desc())
        .limit(200)
    )
    conds = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Application.title_text.ilike(like), Application.company_text.ilike(like)))
    if stage:
        conds.append(Application.stage == stage)
    if conds:
        stmt = stmt.where(and_(*conds))

    apps = db.execute(stmt).scalars().all()
    return templates.TemplateResponse(
        "applications_list.html",
        {
            "request": request,
            "user": user,
            "apps": apps,
            "filters": {"q": q or "", "stage": stage or ""},
            "stages": STAGES,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def application_new_page(
    request: Request,
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "application_new.html",
        {"request": request, "user": user, "stages": STAGES},
    )


@router.post("/new")
def application_new_post(
    request: Request,
    title_text: str = Form(...),
    company_text: str | None = Form(default=None),
    city_text: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    channel: str | None = Form(default=None),
    stage: str = Form(default="not_applied"),
    priority: int = Form(default=3),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    stage_s = stage.strip()
    now = datetime.now(UTC)

    app = Application(
        owner_user_id=user.id,
        job_posting_id=None,
        company_text=company_text.strip() if company_text else None,
        title_text=title_text.strip(),
        city_text=city_text.strip() if city_text else None,
        source_url=source_url.strip() if source_url else None,
        channel=channel.strip() if channel else None,
        stage=stage_s,
        priority=int(priority),
        created_at=now,
        updated_at=now,
        applied_at=(now if stage_s == "applied" else None),
    )
    db.add(app)
    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)


@router.get("/{app_id}", response_class=HTMLResponse)
def application_detail(
    request: Request,
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return templates.TemplateResponse("404.html", {"request": request, "user": user}, status_code=404)

    events = (
        db.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == app.id)
            .order_by(ApplicationEvent.created_at.desc())
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        "application_detail.html",
        {"request": request, "user": user, "app": app, "events": events, "stages": STAGES},
    )


@router.post("/{app_id}/update")
def application_update(
    request: Request,
    app_id: str,
    stage: str = Form(...),
    priority: int = Form(...),
    company_text: str | None = Form(default=None),
    city_text: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    channel: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    stage_s = stage.strip()
    app.stage = stage_s
    if stage_s == "applied" and app.applied_at is None:
        app.applied_at = datetime.now(UTC)

    app.priority = int(priority)
    app.company_text = company_text.strip() if company_text else None
    app.city_text = city_text.strip() if city_text else None
    app.source_url = source_url.strip() if source_url else None
    app.channel = channel.strip() if channel else None

    app.updated_at = datetime.now(UTC)
    db.add(app)
    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)


@router.post("/{app_id}/events")
def application_add_event(
    request: Request,
    app_id: str,
    event_type: str = Form(...),
    occurred_at: str | None = Form(default=None),
    result: str | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    dt = None
    if occurred_at:
        try:
            dt = datetime.fromisoformat(occurred_at)
        except ValueError:
            dt = None

    ev = ApplicationEvent(
        application_id=app.id,
        event_type=event_type.strip(),
        occurred_at=dt,
        result=(result.strip() if result else None),
        note=(note.strip() if note else None),
    )
    db.add(ev)

    app.updated_at = datetime.now(UTC)
    db.add(app)

    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)
