from __future__ import annotations

import traceback
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.bootstrap import ensure_bootstrap_admin
from app.routes import admin, applications, auth, jobs, companies, api
from app.scheduler import start_crawl_scheduler

app = FastAPI(title="Recruit Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

_ERROR_LOG = Path(__file__).resolve().parent / "runtime.err.log"


@app.middleware("http")
async def _log_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Persist stack traces for local debugging.
        try:
            with _ERROR_LOG.open("a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now(UTC).isoformat()}] {request.method} {request.url}\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Browsers hitting HTML pages should be redirected to /login instead of seeing JSON 401.
    accept = (request.headers.get("accept") or "").lower()
    wants_html = "text/html" in accept or "*/*" in accept

    if exc.status_code == 401 and wants_html:
        if request.url.path not in ("/login", "/logout") and not request.url.path.startswith("/static"):
            return RedirectResponse(url="/login", status_code=302)

    return await fastapi_http_exception_handler(request, exc)


@app.on_event("startup")
def _startup() -> None:
    # Creates an initial admin user if the DB is empty and BOOTSTRAP_* env vars exist.
    # This is intentionally idempotent.
    ensure_bootstrap_admin()
    # Optional local scheduler; controlled via env vars.
    start_crawl_scheduler()


app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(companies.router)
app.include_router(applications.router)
app.include_router(api.router)
app.include_router(admin.router)
