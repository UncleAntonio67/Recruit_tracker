from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import CrawlSource, User
from app.security import hash_password
from app.views import templates

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_class=HTMLResponse)
def users_list(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": admin, "users": users})


@router.get("/users/new", response_class=HTMLResponse)
def user_new_page(
    request: Request,
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse("admin_user_new.html", {"request": request, "user": admin})


@router.post("/users/new")
def user_new_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RedirectResponse:
    u = db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()
    if u:
        return templates.TemplateResponse(
            "admin_user_new.html",
            {"request": request, "user": admin, "error": "用户名已存在"},
            status_code=400,
        )

    new_u = User(
        username=username.strip(),
        password_hash=hash_password(password),
        is_admin=bool(is_admin),
    )
    db.add(new_u)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@router.get("/sources", response_class=HTMLResponse)
def sources_list(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    sources = db.execute(select(CrawlSource).order_by(CrawlSource.created_at.desc())).scalars().all()
    return templates.TemplateResponse("admin_sources.html", {"request": request, "user": admin, "sources": sources})


@router.get("/sources/new", response_class=HTMLResponse)
def sources_new_page(
    request: Request,
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    kinds = ["tencent", "kuaishou", "iguopin", "jd", "greenhouse", "lever", "rss", "html_list"]
    default_config = '{\n  "company_name": "",\n  "...": ""\n}'
    return templates.TemplateResponse(
        "admin_source_new.html",
        {"request": request, "user": admin, "kinds": kinds, "default_config": default_config},
    )


@router.post("/sources/new")
def sources_new_post(
    request: Request,
    kind: str = Form(...),
    name: str = Form(...),
    enabled: str | None = Form(default=None),
    config_json: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RedirectResponse:
    try:
        cfg = json.loads(config_json) if config_json.strip() else {}
    except Exception:
        kinds = ["tencent", "kuaishou", "iguopin", "jd", "greenhouse", "lever", "rss", "html_list"]
        return templates.TemplateResponse(
            "admin_source_new.html",
            {"request": request, "user": admin, "kinds": kinds, "error": "config_json 不是合法 JSON", "config_json": config_json},
            status_code=400,
        )

    exists = db.execute(select(CrawlSource).where(CrawlSource.name == name.strip())).scalar_one_or_none()
    if exists:
        kinds = ["tencent", "kuaishou", "iguopin", "jd", "greenhouse", "lever", "rss", "html_list"]
        return templates.TemplateResponse(
            "admin_source_new.html",
            {"request": request, "user": admin, "kinds": kinds, "error": "名称已存在", "config_json": config_json},
            status_code=400,
        )

    s = CrawlSource(kind=kind.strip(), name=name.strip(), enabled=bool(enabled), config=cfg)
    db.add(s)
    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=302)


@router.post("/sources/{source_id}/toggle")
def sources_toggle(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RedirectResponse:
    s = db.get(CrawlSource, source_id)
    if s:
        s.enabled = not bool(s.enabled)
        db.add(s)
        db.commit()
    return RedirectResponse(url="/admin/sources", status_code=302)


@router.post("/crawl/run")
def crawl_run_now(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    from app.crawler.runner import run

    stats = run(db, since_days=180)
    return templates.TemplateResponse("admin_crawl_result.html", {"request": request, "user": admin, "stats": stats})


