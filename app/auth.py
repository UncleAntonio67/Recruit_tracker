from __future__ import annotations

from datetime import UTC
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserSession
from app.security import token_hash, utcnow

SESSION_COOKIE = "rt_session"


def _get_client_ip(request: Request) -> str | None:
    # Cloud Run typically forwards via X-Forwarded-For.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    rt_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if not rt_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    th = token_hash(rt_session)
    stmt = (
        select(User, UserSession)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == th)
    )
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user, sess = row

    now = utcnow()
    exp = sess.expires_at
    if exp.tzinfo is None:
        # SQLite commonly returns naive datetimes even if stored with tz info.
        exp = exp.replace(tzinfo=UTC)

    if user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if sess.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if exp <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Opportunistically store latest ip/ua.
    ip = _get_client_ip(request)
    ua = request.headers.get("user-agent")
    changed = False
    if ip and sess.ip != ip:
        sess.ip = ip
        changed = True
    if ua and sess.user_agent != ua:
        sess.user_agent = ua
        changed = True
    if changed:
        db.add(sess)
        db.commit()

    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user
