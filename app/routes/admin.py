from __future__ import annotations

import os
import json

from datetime import timedelta

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
    crawl_interval_hours = int((os.environ.get("CRAWL_INTERVAL_HOURS") or "0").strip() or 0)
    items = []
    for s in sources:
        next_run_at = None
        if crawl_interval_hours > 0 and s.last_run_at is not None:
            try:
                next_run_at = s.last_run_at + timedelta(hours=crawl_interval_hours)
            except Exception:
                next_run_at = None
        items.append({"source": s, "next_run_at": next_run_at})
    return templates.TemplateResponse(
        "admin_sources.html",
        {
            "request": request,
            "user": admin,
            "items": items,
            "crawl_interval_hours": crawl_interval_hours,
            "crawl_mode": (os.environ.get("CRAWL_MODE") or "official").strip() or "official",
            "crawl_since_days": int((os.environ.get("CRAWL_SINCE_DAYS") or "180").strip() or 180),
        },
    )


@router.get("/sources/new", response_class=HTMLResponse)
def sources_new_page(
    request: Request,
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    kinds = ["tencent", "kuaishou", "iguopin", "jd", "m_zhiye", "hotjob", "greenhouse", "lever", "rss", "html_list", "url_list"]
    default_config = '{\n  "company_name": "",\n  "...": ""\n}'
    return templates.TemplateResponse(
        "admin_source_new.html",
        {"request": request, "user": admin, "kinds": kinds, "default_config": default_config},
    )


def _infer_official_source(company_name: str, entry_url: str, *, proxy: str | None) -> tuple[str, dict]:
    """Infer a CrawlSource kind+config from an official entrypoint URL."""

    from urllib.parse import urlparse

    u = entry_url.strip()
    p = urlparse(u)
    host = (p.netloc or "").strip().lower()

    kind = "html_list"
    cfg: dict = {
        "list_url": u,
        "company_name": company_name.strip(),
        "url_contains": ["job", "jobs", "career", "careers", "recruit", "zhaopin", "hr", "join"],
        "url_excludes": ["campus", "intern", "xiaozhao", "校园", "校招", "实习"],
        "max_items": 200,
        "source_type": "official",
    }

    # Beisen Zhiye portal: use structured API connector.
    if host.endswith(".m.zhiye.com"):
        kind = "m_zhiye"
        cfg = {"base_url": f"{p.scheme}://{p.netloc}", "company_name": company_name.strip(), "jc": 1, "page_size": 30, "max_pages": 40, "source_type": "official"}
    elif host.endswith(".zhiye.com"):
        sub = host[: -len(".zhiye.com")]
        if sub:
            kind = "m_zhiye"
            cfg = {
                "base_url": f"{p.scheme}://{sub}.m.zhiye.com",
                "company_name": company_name.strip(),
                "jc": 1,
                "page_size": 30,
                "max_pages": 40,
                "source_type": "official",
            }
    elif host.endswith(".hotjob.cn") or host == "hotjob.cn":
        kind = "hotjob"
        base = f"{p.scheme or 'https'}://{p.netloc}" if p.netloc else u
        cfg = {
            "base_url": base.replace("http://", "https://"),
            "company_name": company_name.strip(),
            "recruit_type": 2,  # 社招
            "page_size": 12,
            "max_pages": 12,
            "source_type": "official",
        }
    elif u.lower().endswith((".rss", ".xml")):
        kind = "rss"
        cfg = {"feed_url": u, "company_name": company_name.strip(), "source_type": "official"}

    if proxy and proxy.strip():
        cfg["proxy"] = proxy.strip()
    return kind, cfg


@router.post("/sources/new_simple")
def sources_new_simple_post(
    request: Request,
    company_name: str = Form(...),
    entry_url: str = Form(...),
    name: str | None = Form(default=None),
    proxy: str | None = Form(default=None),
    enabled: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RedirectResponse:
    cn = company_name.strip()
    eu = entry_url.strip()
    if not cn or not eu:
        return RedirectResponse(url="/admin/sources/new", status_code=302)

    src_name = (name or "").strip() or f"Official:{cn}"
    exists = db.execute(select(CrawlSource).where(CrawlSource.name == src_name)).scalar_one_or_none()
    if exists:
        kinds = ["tencent", "kuaishou", "iguopin", "jd", "m_zhiye", "hotjob", "greenhouse", "lever", "rss", "html_list", "url_list"]
        return templates.TemplateResponse(
            "admin_source_new.html",
            {
                "request": request,
                "user": admin,
                "kinds": kinds,
                "error": "名称已存在(简单模式)。请改名或在公司页点击“生成/更新采集源”。",
                "simple": {"company_name": cn, "entry_url": eu, "name": src_name, "proxy": (proxy or "")},
            },
            status_code=400,
        )

    kind, cfg = _infer_official_source(cn, eu, proxy=proxy)
    s = CrawlSource(kind=kind, name=src_name, enabled=bool(enabled), config=cfg)
    db.add(s)
    db.commit()
    return RedirectResponse(url="/admin/sources", status_code=302)


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
        kinds = ["tencent", "kuaishou", "iguopin", "jd", "m_zhiye", "hotjob", "greenhouse", "lever", "rss", "html_list", "url_list"]
        return templates.TemplateResponse(
            "admin_source_new.html",
            {"request": request, "user": admin, "kinds": kinds, "error": "config_json 不是合法 JSON", "config_json": config_json},
            status_code=400,
        )

    exists = db.execute(select(CrawlSource).where(CrawlSource.name == name.strip())).scalar_one_or_none()
    if exists:
        kinds = ["tencent", "kuaishou", "iguopin", "jd", "m_zhiye", "hotjob", "greenhouse", "lever", "rss", "html_list", "url_list"]
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
    since_days: int = Form(default=180),
    mode: str = Form(default="official"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    from app.crawler.runner import run

    stats = run(db, since_days=int(since_days), mode=(mode or "core"))
    return templates.TemplateResponse("admin_crawl_result.html", {"request": request, "user": admin, "stats": stats})


@router.post("/sources/{source_id}/run")
def crawl_run_one(
    request: Request,
    source_id: str,
    since_days: int = Form(default=180),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    from app.crawler.runner import run_one

    stats = run_one(db, source_id=source_id, since_days=int(since_days))
    return templates.TemplateResponse("admin_crawl_result.html", {"request": request, "user": admin, "stats": stats})


