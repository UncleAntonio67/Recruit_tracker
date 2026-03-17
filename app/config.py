from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        # Local-first default. For Cloud Run + Neon, set DATABASE_URL explicitly.
        self.database_url = os.environ.get("DATABASE_URL", "").strip() or "sqlite:///./recruit_tracker.db"

        self.env = os.environ.get("ENV", "dev").strip().lower()
        self.cookie_secure = self.env in ("prod", "production")

        self.bootstrap_admin_username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "").strip()
        self.bootstrap_admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()


def get_settings() -> Settings:
    # Settings are cheap here; kept as function to avoid import-time surprises in migrations/tests.
    return Settings()
