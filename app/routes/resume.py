from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import ResumeProfile, User
from app.views import templates

router = APIRouter(prefix="/resume", tags=["resume"])


def _get_or_create_profile(db: Session, user: User) -> ResumeProfile:
    p = db.execute(select(ResumeProfile).where(ResumeProfile.owner_user_id == user.id)).scalar_one_or_none()
    if p:
        return p
    p = ResumeProfile(owner_user_id=user.id, links={})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("", response_class=HTMLResponse)
def resume_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTMLResponse:
    profile = _get_or_create_profile(db, user)
    return templates.TemplateResponse("resume.html", {"request": request, "user": user, "profile": profile})


@router.post("")
def resume_update(
    request: Request,
    full_name: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    email: str | None = Form(default=None),
    city: str | None = Form(default=None),
    summary: str | None = Form(default=None),
    skills: str | None = Form(default=None),
    experience: str | None = Form(default=None),
    projects: str | None = Form(default=None),
    education: str | None = Form(default=None),
    links_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    p = _get_or_create_profile(db, user)

    p.full_name = (full_name or "").strip() or None
    p.phone = (phone or "").strip() or None
    p.email = (email or "").strip() or None
    p.city = (city or "").strip() or None

    p.summary = (summary or "").strip() or None
    p.skills = (skills or "").strip() or None
    p.experience = (experience or "").strip() or None
    p.projects = (projects or "").strip() or None
    p.education = (education or "").strip() or None

    if links_json and links_json.strip():
        try:
            obj = json.loads(links_json)
            if isinstance(obj, dict):
                p.links = obj
        except Exception:
            # Ignore invalid JSON; keep previous.
            pass

    p.updated_at = datetime.now(UTC)
    db.add(p)
    db.commit()
    return RedirectResponse(url="/resume", status_code=302)

