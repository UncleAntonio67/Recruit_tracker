from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def ensure_bootstrap_admin() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_username or not settings.bootstrap_admin_password:
        return

    db = SessionLocal()
    try:
        try:
            existing = db.execute(select(User.id).limit(1)).first()
        except SQLAlchemyError:
            # Likely migrations haven't been applied yet.
            return

        if existing:
            return

        user = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_admin=True,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()
