from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.crawler.prefill import prefill_from_url
from app.models import User

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/prefill")
def api_prefill(
    url: str = Query(..., min_length=6, max_length=2000),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    info = prefill_from_url(url)
    # Keep payload small and predictable.
    allow = {"source_url", "title", "company_name", "city", "published_at", "excerpt", "salary_text"}
    out = {k: v for k, v in (info or {}).items() if k in allow}
    return JSONResponse(out)

