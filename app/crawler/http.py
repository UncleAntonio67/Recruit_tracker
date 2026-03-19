from __future__ import annotations

import gzip
import json
import zlib
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

_DEFAULT_HEADERS = {
    "User-Agent": "recruit-tracker/0.1",
    "Accept-Encoding": "gzip, deflate",
}


def _opener(proxy: str | None):
    if proxy:
        # Expect proxy like http://127.0.0.1:7890
        return build_opener(ProxyHandler({"http": proxy, "https": proxy}))
    return build_opener()


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    proxy: str | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> bytes:
    op = _opener(proxy)
    hdrs = dict(_DEFAULT_HEADERS)
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()})

    req = Request(url, headers=hdrs, data=data, method=method.upper())
    with op.open(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                return gzip.decompress(raw)
            except Exception:
                return raw
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except Exception:
                try:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
                except Exception:
                    return raw
        return raw


def get_text(
    url: str,
    proxy: str | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> str:
    data = request_bytes(url, proxy=proxy, timeout=timeout, headers=headers)
    return data.decode("utf-8", errors="ignore")


def get_json(
    url: str,
    proxy: str | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
):
    text = get_text(url, proxy=proxy, timeout=timeout, headers=headers)
    # Some domestic ATS endpoints return JSON with UTF-8 BOM.
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    return json.loads(text)


def post_json(
    url: str,
    payload: dict | list | None = None,
    *,
    proxy: str | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
):
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()})
    raw = request_bytes(url, method="POST", data=body, proxy=proxy, timeout=timeout, headers=hdrs)
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    return json.loads(text)


def post_form(
    url: str,
    payload: dict | None = None,
    *,
    proxy: str | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
):
    """POST x-www-form-urlencoded and decode JSON response.

    Hotjob/Wecruit and some domestic ATS backends expect form posts rather than JSON.
    """

    body = urlencode(payload or {}).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json, text/plain, */*"}
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()})
    raw = request_bytes(url, method="POST", data=body, proxy=proxy, timeout=timeout, headers=hdrs)
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    return json.loads(text)
