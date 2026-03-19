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

CITY_OPTIONS = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "苏州",
    "武汉",
    "成都",
    "西安",
    "天津",
    "重庆",
    "厦门",
    "长沙",
    "合肥",
    "青岛",
    "济南",
    "郑州",
    "大连",
    "沈阳",
    "宁波",
    "无锡",
    "福州",
    "珠海",
    "东莞",
    "佛山",
    "全国",
    "远程",
]

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
            "stage_labels": STAGE_LABELS,
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
    stage: str = Form(default="未投递"),
    priority: int = Form(default=3),
    applied_at: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    stage_s = _normalize_stage(stage)
    now = datetime.now(UTC)

    applied_dt = None
    if applied_at and str(applied_at).strip():
        try:
            applied_dt = datetime.fromisoformat(str(applied_at).strip())
        except ValueError:
            applied_dt = None

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
        applied_at=(applied_dt or (now if stage_s == "已投递" else None)),
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
    applied_at: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    stage_s = _normalize_stage(stage)
    app.stage = stage_s
    if applied_at and str(applied_at).strip():
        try:
            app.applied_at = datetime.fromisoformat(str(applied_at).strip())
        except ValueError:
            pass
    if stage_s == "已投递" and app.applied_at is None:
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
    scheduled_at: str | None = Form(default=None),
    result: str | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    app = db.get(Application, app_id)
    if not app or app.owner_user_id != user.id:
        return RedirectResponse(url="/applications", status_code=302)

    occurred_dt = None
    if occurred_at and str(occurred_at).strip():
        try:
            occurred_dt = datetime.fromisoformat(str(occurred_at).strip())
        except ValueError:
            occurred_dt = None

    scheduled_dt = None
    if scheduled_at and str(scheduled_at).strip():
        try:
            scheduled_dt = datetime.fromisoformat(str(scheduled_at).strip())
        except ValueError:
            scheduled_dt = None

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
