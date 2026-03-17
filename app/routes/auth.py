from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import User, UserSession
from app.security import new_session_token, session_expiry, token_hash, verify_password
from app.views import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url="/jobs", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not u or u.disabled_at is not None or not verify_password(password, u.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "用户名或密码错误"},
            status_code=401,
        )

    token = new_session_token()
    sess = UserSession(
        user_id=u.id,
        token_hash=token_hash(token),
        expires_at=session_expiry(),
        user_agent=request.headers.get("user-agent"),
        ip=request.headers.get("x-forwarded-for"),
    )
    db.add(sess)
    db.commit()

    settings = get_settings()
    resp = RedirectResponse(url="/jobs", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=14 * 24 * 3600,
        path="/",
    )
    return resp


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        th = token_hash(token)
        sess = db.execute(select(UserSession).where(UserSession.token_hash == th)).scalar_one_or_none()
        if sess and sess.revoked_at is None:
            sess.revoked_at = datetime.now(UTC)
            db.add(sess)
            db.commit()

    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/me", response_class=HTMLResponse)
def me(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return templates.TemplateResponse("me.html", {"request": request, "user": user})
