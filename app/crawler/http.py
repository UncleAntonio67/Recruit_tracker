from __future__ import annotations

import gzip
import json
import shutil
import subprocess
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


def _curl_request_bytes(
    url: str,
    *,
    method: str,
    data: bytes | None,
    proxy: str | None,
    timeout: int,
    headers: dict[str, str],
) -> bytes:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")

    cmd = [
        curl,
        "--silent",
        "--show-error",
        "--location",
        "--max-redirs",
        "8",
        "--compressed",
        "--request",
        method.upper(),
        "--connect-timeout",
        str(max(5, min(timeout, 30))),
        "--max-time",
        str(timeout),
    ]
    if proxy:
        cmd.extend(["--proxy", proxy])
    for k, v in headers.items():
        cmd.extend(["--header", f"{k}: {v}"])
    if data is not None:
        cmd.extend(["--data-binary", "@-"])
    cmd.append(url)

    proc = subprocess.run(cmd, input=data, capture_output=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore").strip() or f"curl exit {proc.returncode}"
        raise RuntimeError(stderr)
    return proc.stdout


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
    try:
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
    except Exception as e:
        msg = str(e).lower()
        retryable = any(
            token in msg
            for token in [
                "unsafe_legacy_renegotiation_disabled",
                "unexpected_eof_while_reading",
                "redirect error",
                "temporarily unavailable",
                "certificate_verify_failed",
            ]
        )
        if not retryable:
            raise
        return _curl_request_bytes(
            url,
            method=method,
            data=data,
            proxy=proxy,
            timeout=timeout,
            headers=hdrs,
        )


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
