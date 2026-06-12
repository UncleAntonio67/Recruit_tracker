from __future__ import annotations

import base64
import hashlib
import json
import random
import time

from app.crawler.http import post_json
from app.crawler.job_types import RawJob
from app.crawler.utils import clamp_excerpt, parse_dt

_PBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAhbieIVi00W3W1i9hYVs1EY6iYLF936QV71fmFNtsATK3m7iEbgDNo222M2uRJ1fVFyt00O"
    "kwyJ/EzvLL7M2iWK7d3fs8OAwsJd0/tBGhFvJU9YUzGibvko3KfOiUr+CMLwrGY4cXyPUs/DHiwqVb+/JhvffKTzzpZxnmOZDY5G7q6FfLFmGueQI7"
    "h9NyqyTst1jrfJRq2QG2uDDuMNlYEjWNSHI7fg9F91xLhyNNKIO1a3dcpLi8HZEtm4mgs1+i2xH49EzVjLyFjep91nqNUrauXVr22DMGfuggeAzuRx"
    "lqo1bVNg9pC1EtcTg4GkWURf4FWngXo4ntHpGcd+hecwIDAQAB"
)
_COMPANY_LIST_URL = "https://job.10086.cn/job-app/company/getCompanyList.do"
_SEARCH_URL = "https://job.10086.cn/job-app/job/searchJobs.do"
_REFERER = "https://job.10086.cn/personal/job/?code=115"


def _read_len(buf: bytes, idx: int) -> tuple[int, int]:
    first = buf[idx]
    idx += 1
    if first < 0x80:
        return first, idx
    count = first & 0x7F
    value = 0
    for _ in range(count):
        value = (value << 8) | buf[idx]
        idx += 1
    return value, idx


def _read_tlv(buf: bytes, idx: int) -> tuple[int, bytes, int]:
    tag = buf[idx]
    idx += 1
    length, idx = _read_len(buf, idx)
    value = buf[idx : idx + length]
    return tag, value, idx + length


def _load_public_key() -> tuple[int, int]:
    raw = base64.b64decode(_PBKEY_B64)
    _, outer, _ = _read_tlv(raw, 0)
    _, _, pos = _read_tlv(outer, 0)
    _, bit_string, _ = _read_tlv(outer, pos)
    spki = bit_string[1:]
    _, seq2, _ = _read_tlv(spki, 0)
    _, modulus, pos2 = _read_tlv(seq2, 0)
    _, exponent, _ = _read_tlv(seq2, pos2)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


_RSA_N, _RSA_E = _load_public_key()


def _pkcs1_encrypt(msg: bytes) -> bytes:
    k = (_RSA_N.bit_length() + 7) // 8
    if len(msg) > k - 11:
        raise ValueError("message too long")
    ps = bytearray()
    while len(ps) < k - len(msg) - 3:
        b = 0
        while b == 0:
            b = random.randrange(1, 256)
        ps.append(b)
    em = b"\x00\x02" + bytes(ps) + b"\x00" + msg
    encrypted = pow(int.from_bytes(em, "big"), _RSA_E, _RSA_N)
    return encrypted.to_bytes(k, "big")


def _pad(num: int, width: int) -> str:
    s = str(num)
    return s[-width:] if len(s) >= width else ("0" * (width - len(s))) + s


def _conversation_id(curtime: str, referer: str) -> str:
    ts = int(curtime)
    dt = time.localtime(ts / 1000)
    seed = f"{curtime},{referer},Netscape,5.0 (Windows),Mozilla/5.0"
    rnd = _pad(int(hashlib.md5(seed.encode("utf-8")).hexdigest()[25:32], 16), 6)
    return (
        f"{_pad(dt.tm_year, 4)}{_pad(dt.tm_mon, 2)}{_pad(dt.tm_mday, 2)}"
        f"{_pad(dt.tm_hour, 2)}{_pad(dt.tm_min, 2)}{_pad(dt.tm_sec, 2)}"
        f"{curtime[-3:]}{rnd}"
    )


def _signed_post(url: str, payload_data: dict, *, referer: str, proxy: str | None = None) -> dict:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    secret = "".join(random.choice(alphabet) for _ in range(10))
    curtime = str(int(time.time() * 1000))
    digest_left = base64.b64encode(hashlib.md5((curtime + secret).encode("utf-8")).hexdigest().encode("utf-8")).decode(
        "ascii"
    )
    digest_right = base64.b64encode(_pkcs1_encrypt(secret.encode("utf-8"))).decode("ascii")

    payload = {
        "serviceName": payload_data.get("serviceName"),
        "header": {
            "version": "1.0",
            "timestamp": curtime,
            "digest": f"{digest_left};{digest_right}",
            "conversationId": _conversation_id(curtime, referer),
        },
        "data": payload_data.get("data") or {},
    }
    resp = post_json(
        url,
        payload,
        proxy=proxy,
        timeout=60,
        headers={
            "Referer": referer,
            "Origin": "https://job.10086.cn",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        },
    )
    if isinstance(resp, str):
        try:
            parsed = json.loads(resp)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return resp if isinstance(resp, dict) else {}


def _company_name_map(proxy: str | None) -> dict[str, str]:
    data = _signed_post(_COMPANY_LIST_URL, {"serviceName": "getCompanyList", "data": {}}, referer=_REFERER, proxy=proxy)
    items = ((data.get("data") or {}).get("companyList") or []) if isinstance(data, dict) else []
    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        company_id = str(item.get("companyId") or "").strip()
        short_name = str(item.get("shortName") or "").strip()
        if company_id and short_name:
            out[company_id] = short_name
    return out


def fetch(config: dict, proxy: str | None = None) -> list[RawJob]:
    company_name = str(config.get("company_name") or "中国移动").strip() or "中国移动"
    effective_proxy = proxy or (str(config.get("proxy") or "").strip() or None)
    page_size = min(max(int(config.get("page_size") or 20), 1), 50)
    max_pages = max(int(config.get("max_pages") or 8), 1)
    search_key = str(config.get("search_key") or "").strip()
    company_ids = [str(x).strip() for x in (config.get("company_ids") or []) if str(x).strip()]
    if not company_ids:
        company_ids = [""]
    type_allow = {str(x).strip() for x in (config.get("type_allowlist") or ["2"]) if str(x).strip()}

    company_names = _company_name_map(effective_proxy)
    out: list[RawJob] = []
    seen: set[str] = set()

    for company_id in company_ids:
        for page_no in range(1, max_pages + 1):
            data = _signed_post(
                _SEARCH_URL,
                {
                    "serviceName": "searchJobs",
                    "data": {
                        "pageNo": page_no,
                        "pageSize": page_size,
                        "key": search_key,
                        "companyId": company_id,
                        "workYear": "",
                        "degree": "",
                        "publishTime": "",
                        "workType": "",
                        "type": "",
                        "category": "",
                        "subCategory": "",
                        "workCity": "",
                        "workProvince": "",
                    },
                },
                referer=_REFERER,
                proxy=effective_proxy,
            )
            items = ((data.get("data") or {}).get("jobList") or []) if isinstance(data, dict) else []
            if not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                job_id = str(item.get("id") or "").strip()
                title = str(item.get("name") or "").strip()
                job_type = str(item.get("type") or "").strip()
                if not job_id or not title:
                    continue
                if type_allow and job_type and job_type not in type_allow:
                    continue

                detail_url = f"https://job.10086.cn/personal/job/detail.html?id={job_id}"
                if job_type == "1":
                    detail_url += f"&typess={job_type}"
                if detail_url in seen:
                    continue
                seen.add(detail_url)

                short_name = str(item.get("companyShortName") or "").strip()
                city = str(item.get("city") or item.get("address") or "").strip() or None
                excerpt = clamp_excerpt(
                    " | ".join(
                        x
                        for x in [
                            short_name or company_names.get(company_id) or company_name,
                            str(item.get("category") or "").strip(),
                            str(item.get("workYear") or "").strip(),
                            str(item.get("degree") or "").strip(),
                            str(item.get("workType") or "").strip(),
                        ]
                        if x
                    )
                )
                out.append(
                    RawJob(
                        source_url=detail_url,
                        title=title,
                        company_name=short_name or company_names.get(company_id) or company_name,
                        city=city,
                        published_at=parse_dt(str(item.get("startTime") or "").strip() or None),
                        excerpt=excerpt,
                        department=str(item.get("category") or "").strip() or None,
                        seniority=str(item.get("workYear") or "").strip() or None,
                        tags=[],
                    )
                )
            if len(items) < page_size:
                break

    return out
