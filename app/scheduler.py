from __future__ import annotations

import logging
import os
import random
import threading
import time

from app.crawler.runner import run as run_crawl
from app.db import SessionLocal

log = logging.getLogger(__name__)

_started = False


def _get_int(name: str, default: int) -> int:
    v = str(os.getenv(name, "")).strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def start_crawl_scheduler() -> None:
    """Start a simple in-process crawl scheduler.

    This is intentionally dependency-free for local/dev use.

    Env vars:
    - CRAWL_INTERVAL_HOURS: int, 0 disables (recommended for Cloud Run; use Cloud Scheduler there)
    - CRAWL_SINCE_DAYS: int (default 180)
    - CRAWL_INITIAL_DELAY_SEC: int (default 30)
    - CRAWL_JITTER_SEC: int (default 30)  # random extra delay before each run
    """

    global _started
    if _started:
        return

    interval_hours = _get_int("CRAWL_INTERVAL_HOURS", 0)
    if interval_hours <= 0:
        return

    since_days = _get_int("CRAWL_SINCE_DAYS", 180)
    initial_delay = max(0, _get_int("CRAWL_INITIAL_DELAY_SEC", 30))
    jitter = max(0, _get_int("CRAWL_JITTER_SEC", 30))
    mode = (os.getenv("CRAWL_MODE") or "core").strip() or "core"

    def _loop() -> None:
        if initial_delay:
            time.sleep(initial_delay)
        while True:
            # Prevents synchronized runs when multiple instances exist.
            if jitter:
                time.sleep(random.randint(0, jitter))

            try:
                db = SessionLocal()
                try:
                    stats = run_crawl(db, since_days=since_days, mode=mode)
                    log.info("scheduled crawl finished: %s", stats)
                finally:
                    db.close()
            except Exception:
                log.exception("scheduled crawl failed")

            time.sleep(interval_hours * 3600)

    t = threading.Thread(target=_loop, name="crawl-scheduler", daemon=True)
    t.start()
    _started = True
    log.info("crawl scheduler started: every %sh since_days=%s", interval_hours, since_days)
