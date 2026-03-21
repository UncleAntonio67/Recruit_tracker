from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Application, ApplicationEvent, User
from app.views import templates

router = APIRouter(prefix="/applications", tags=["applications"])

from app.ui_options import city_filter_options

CITY_OPTIONS = city_filter_options()

STAGE_LABELS = {
    # legacy english -> cn
    "not_applied": "未投递",
    "applied": "已投递",
    "screening": "简历筛选",
    "test": "笔试",
    "interview1": "一面",
    "interview2": "二面",
    "interview3": "三面",
    "hr": "HR面",
    "offer": "Offer",
    "rejected": "拒绝",
    "dropped": "放弃",
}

STAGES = [
    "未投递",
    "已投递",
    "简历筛选",
    "笔试",
    "一面",
    "二面",
    "三面",
    "HR面",
    "Offer",
    "拒绝",
    "放弃",
    "已入职",
]

CHANNEL_OPTIONS = [
    "官网网申",
    "国聘",
    "Boss",
    "前程无忧(51job)",
    "Indeed",
    "内推",
    "猎头",
    "公众号",
    "邮件",
    "其他",
]

EVENT_TYPES = [
    "投递",
    "电话沟通",
    "简历筛选",
    "笔试",
    "一面",
    "二面",
    "三面",
    "HR面",
    "Offer",
    "拒绝",
    "跟进",
    "入职",
]

EVENT_RESULTS = ["通过", "未通过", "待定"]

_TZ_SH = timezone(timedelta(hours=8))


def _parse_dt_local(value: str | None) -> datetime | None:
    """Parse <input type=datetime-local> into a UTC datetime.

    Browsers submit datetime-local without timezone. We interpret it as Asia/Shanghai.
    """

    if not value or not str(value).strip():
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ_SH)
    return dt.astimezone(UTC)


def _normalize_stage(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return "未投递"
    return STAGE_LABELS.get(s, s)


@router.get("", response_class=HTMLResponse)
def applications_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    city: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    # Keep as string because <select> submits empty value as "" which would 422 for int Query params.
    priority: str | None = Query(default=None),
    applied_from: str | None = Query(default=None),
    applied_to: str | None = Query(default=None),
    selected: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=5000),
) -> HTMLResponse:
    page_size = 50
    stmt = (
        select(Application)
        .where(Application.owner_user_id == user.id)
        .order_by(Application.updated_at.desc())
    )
    conds = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(Application.title_text.ilike(like), Application.company_text.ilike(like)))
    if stage:
        want = _normalize_stage(stage)
        legacy = None
        # If the DB stored legacy english values, allow them in filtering.
        for eng, cn in STAGE_LABELS.items():
            if cn == want:
                legacy = eng
                break
        if legacy:
            conds.append(or_(Application.stage == want, Application.stage == legacy))
        else:
            conds.append(Application.stage == want)
    if city:
        # Application city may come from a job posting like "北京/上海", so use contains match.
        conds.append(Application.city_text.ilike(f"%{city.strip()}%"))
    if channel:
        conds.append(Application.channel == channel.strip())
    if priority is not None:
        pv = str(priority).strip()
        if pv:
            try:
                n = int(pv)
            except Exception:
                n = None
            if n is not None and 1 <= n <= 5:
                conds.append(Application.priority == n)

    af = _parse_dt_local(applied_from) if applied_from else None
    at = _parse_dt_local(applied_to) if applied_to else None
    if af:
        conds.append(Application.applied_at.is_not(None))
        conds.append(Application.applied_at >= af)
    if at:
        # Inclusive end: add 1 day when user supplies a date-only value (rare here),
        # or keep exact datetime when time is present.
        conds.append(Application.applied_at.is_not(None))
        conds.append(Application.applied_at <= at)
    if conds:
        stmt = stmt.where(and_(*conds))

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page_v = max(1, min(int(page), total_pages))

    rows = db.execute(stmt.offset((page_v - 1) * page_size).limit(page_size + 1)).scalars().all()
    apps = rows[:page_size]
    has_next = len(rows) > page_size
    has_prev = page_v > 1
    prev_url = str(request.url.include_query_params(page=page_v - 1)) if has_prev else ""
    next_url = str(request.url.include_query_params(page=page_v + 1)) if has_next else ""

    selected_app = None
    selected_events = []
    selected_id = (selected or "").strip()
    if selected_id:
        try:
            cand = db.get(Application, selected_id)
        except Exception:
            cand = None
        if cand and cand.owner_user_id == user.id:
            # Opportunistic migration of legacy stage values to Chinese display values.
            if cand.stage in STAGE_LABELS:
                cand.stage = STAGE_LABELS[cand.stage]
                db.add(cand)
                db.commit()
            selected_app = cand
            selected_events = (
                db.execute(
                    select(ApplicationEvent)
                    .where(ApplicationEvent.application_id == cand.id)
                    .order_by(
                        ApplicationEvent.occurred_at.asc().nullslast(),
                        ApplicationEvent.scheduled_at.asc().nullslast(),
                        ApplicationEvent.created_at.asc(),
                    )
                )
                .scalars()
                .all()
            )

    return templates.TemplateResponse(
        "applications_list.html",
        {
            "request": request,
            "user": user,
            "apps": apps,
            "selected_app": selected_app,
            "selected_events": selected_events,
            "filters": {
                "q": q or "",
                "stage": stage or "",
                "city": city or "",
                "channel": channel or "",
                "priority": "" if priority is None else str(priority),
                "applied_from": applied_from or "",
                "applied_to": applied_to or "",
                "selected": selected_id,
            },
            "stages": STAGES,
            "stage_labels": STAGE_LABELS,
            "city_options": CITY_OPTIONS,
            "channels": CHANNEL_OPTIONS,
            "event_types": EVENT_TYPES,
            "event_results": EVENT_RESULTS,
            "page": page_v,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "prev_url": prev_url,
            "next_url": next_url,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def application_new_page(
    request: Request,
    url: str | None = Query(default=None),
    title_text: str | None = Query(default=None),
    company_text: str | None = Query(default=None),
    city_text: str | None = Query(default=None),
    source_url: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    # Optional prefill from a URL (similar to /jobs/import).
    if url and str(url).strip():
        try:
            from app.crawler.prefill import prefill_from_url

            info = prefill_from_url(str(url).strip())
            title_text = title_text or (info.get("title") or None)
            company_text = company_text or (info.get("company_name") or None)
            city_text = city_text or (info.get("city") or None)
            source_url = source_url or (info.get("source_url") or str(url).strip())
        except Exception:
            # Prefill is best-effort; don't block manual entry.
            pass

    return templates.TemplateResponse(
        "application_new.html",
        {
            "request": request,
            "user": user,
            "stages": STAGES,
            "channels": CHANNEL_OPTIONS,
            "city_options": CITY_OPTIONS,
            "prefill": {
                "title_text": (title_text or ""),
                "company_text": (company_text or ""),
                "city_text": (city_text or ""),
                "source_url": (source_url or ""),
                "channel": (channel or ""),
                "stage": _normalize_stage(stage),
            },
        },
    )


@router.post("/new")
def application_new_post(
    request: Request,
    title_text: str = Form(...),
    company_text: str | None = Form(default=None),
    city_text: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    channel: str | None = Form(default=None),
    channel_select: str | None = Form(default=None),
    channel_other: str | None = Form(default=None),
    stage: str = Form(default="未投递"),
    priority: int = Form(default=3),
    applied_at: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    stage_s = _normalize_stage(stage)
    now = datetime.now(UTC)

    applied_dt = _parse_dt_local(applied_at)

    picked_channel = (channel_other or "").strip() or (channel_select or "").strip() or (channel or "").strip() or None

    app = Application(
        owner_user_id=user.id,
        job_posting_id=None,
        company_text=company_text.strip() if company_text else None,
        title_text=title_text.strip(),
        city_text=city_text.strip() if city_text else None,
        source_url=source_url.strip() if source_url else None,
        channel=picked_channel,
        stage=stage_s,
        priority=int(priority),
        created_at=now,
        updated_at=now,
        applied_at=(applied_dt or (now if stage_s == "已投递" else None)),
    )
    db.add(app)
    db.commit()

    # If user says "已投递", create a first timeline event automatically.
    if app.stage == "已投递" and app.applied_at:
        ev = ApplicationEvent(
            application_id=app.id,
            event_type="投递",
            occurred_at=app.applied_at,
            result=None,
            note=None,
        )
        db.add(ev)
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
    # Opportunistic migration of legacy stage values to Chinese display values.
    if app.stage in STAGE_LABELS:
        app.stage = STAGE_LABELS[app.stage]
        db.add(app)
        db.commit()

    events = (
        db.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == app.id)
            .order_by(
                ApplicationEvent.occurred_at.asc().nullslast(),
                ApplicationEvent.scheduled_at.asc().nullslast(),
                ApplicationEvent.created_at.asc(),
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        "application_detail.html",
        {
            "request": request,
            "user": user,
            "app": app,
            "events": events,
            "stages": STAGES,
            "stage_labels": STAGE_LABELS,
            "channels": CHANNEL_OPTIONS,
            "city_options": CITY_OPTIONS,
            "event_types": EVENT_TYPES,
            "event_results": EVENT_RESULTS,
        },
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
    channel_select: str | None = Form(default=None),
    channel_other: str | None = Form(default=None),
    applied_at: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    stage_s = _normalize_stage(stage)
    app.stage = stage_s
    applied_dt = _parse_dt_local(applied_at)
    if applied_dt:
        app.applied_at = applied_dt
    if stage_s == "已投递" and app.applied_at is None:
        app.applied_at = datetime.now(UTC)

    app.priority = int(priority)
    app.company_text = company_text.strip() if company_text else None
    app.city_text = city_text.strip() if city_text else None
    app.source_url = source_url.strip() if source_url else None
    picked_channel = (channel_other or "").strip() or (channel_select or "").strip() or (channel or "").strip() or None
    app.channel = picked_channel

    app.updated_at = datetime.now(UTC)
    db.add(app)
    db.commit()

    # Auto-create "投递" event if missing.
    if app.stage == "已投递" and app.applied_at:
        existing = (
            db.execute(
                select(ApplicationEvent.id).where(
                    and_(ApplicationEvent.application_id == app.id, ApplicationEvent.event_type == "投递")
                )
            )
            .scalar_one_or_none()
        )
        if not existing:
            db.add(
                ApplicationEvent(
                    application_id=app.id,
                    event_type="投递",
                    occurred_at=app.applied_at,
                    result=None,
                    note=None,
                )
            )
            db.commit()

    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)


@router.post("/{app_id}/events")
def application_add_event(
    request: Request,
    app_id: str,
    event_type: str = Form(...),
    occurred_at: str | None = Form(default=None),
    scheduled_at: str | None = Form(default=None),
    result: str | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    occurred_dt = _parse_dt_local(occurred_at)
    scheduled_dt = _parse_dt_local(scheduled_at)

    ev = ApplicationEvent(
        application_id=app.id,
        event_type=event_type.strip(),
        scheduled_at=scheduled_dt,
        occurred_at=occurred_dt,
        result=(result.strip() if result else None),
        note=(note.strip() if note else None),
    )
    db.add(ev)

    app.updated_at = datetime.now(UTC)
    db.add(app)

    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)


@router.post("/{app_id}/events/{event_id}/update")
def application_update_event(
    request: Request,
    app_id: str,
    event_id: str,
    event_type: str = Form(...),
    occurred_at: str | None = Form(default=None),
    scheduled_at: str | None = Form(default=None),
    result: str | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    ev = db.get(ApplicationEvent, event_id)
    if not ev or ev.application_id != app.id:
        return RedirectResponse(url=f"/applications/{app.id}", status_code=302)

    ev.event_type = (event_type or "").strip() or ev.event_type
    ev.occurred_at = _parse_dt_local(occurred_at)
    ev.scheduled_at = _parse_dt_local(scheduled_at)
    ev.result = (result.strip() if result and result.strip() else None)
    ev.note = (note.strip() if note and note.strip() else None)

    app.updated_at = datetime.now(UTC)
    db.add(ev)
    db.add(app)
    db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)


@router.post("/{app_id}/events/{event_id}/delete")
def application_delete_event(
    request: Request,
    app_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    ev = db.get(ApplicationEvent, event_id)
    if ev and ev.application_id == app.id:
        db.delete(ev)
        app.updated_at = datetime.now(UTC)
        db.add(app)
        db.commit()
    return RedirectResponse(url=f"/applications/{app.id}", status_code=302)
