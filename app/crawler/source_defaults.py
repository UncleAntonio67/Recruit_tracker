from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def default_include_keywords() -> list[str]:
    return [
        "后端",
        "后台",
        "前端",
        "全栈",
        "开发",
        "研发",
        "工程师",
        "软件",
        "系统",
        "平台",
        "架构",
        "架构师",
        "企业架构",
        "架构管理",
        "数据",
        "数据开发",
        "数据工程",
        "数据平台",
        "数据分析",
        "大数据",
        "算法",
        "AI",
        "人工智能",
        "机器学习",
        "测试",
        "运维",
        "DevOps",
        "SRE",
        "云",
        "中台",
        "安全",
        "金融科技",
        "银行科技",
        "核心系统",
        "支付",
        "风控",
        "项目管理",
        "项目经理",
        "PMO",
        "交付",
        "实施",
        "新能源",
        "储能",
        "锂电",
        "电池",
        "电芯",
        "BMS",
        "电化学",
        "材料",
        "化工",
        "PACK",
        "正极",
        "负极",
        "电解液",
        "隔膜",
    ]


def default_exclude_keywords() -> list[str]:
    return [
        "校招",
        "校园",
        "应届",
        "实习",
        "管培",
        "管培生",
        "销售",
        "市场",
        "商务",
        "运营",
        "客服",
        "财务",
        "审计",
        "法务",
        "人力",
        "行政",
        "采购",
        "生产操作",
        "普工",
        "司机",
    ]


def default_city_allowlist() -> list[str]:
    return ["北京", "上海", "广州", "深圳"]


def apply_default_filters(cfg: dict | None) -> dict:
    out = dict(cfg or {})
    out.setdefault("include_keywords", default_include_keywords())
    out.setdefault("exclude_keywords", default_exclude_keywords())
    out.setdefault("city_allowlist", default_city_allowlist())
    return out


def infer_official_source(
    company_name: str,
    entry_url: str,
    *,
    proxy: str | None = None,
    overrides: dict | None = None,
) -> tuple[str, dict]:
    """Infer a CrawlSource kind+config from an official recruitment entrypoint."""

    u = (entry_url or "").strip()
    if not u:
        raise ValueError("entry_url is required")

    p = urlparse(u)
    host = (p.netloc or "").strip().lower()

    kind = "html_list"
    cfg: dict = {
        "list_url": u,
        "company_name": company_name.strip(),
        "url_contains": ["job", "jobs", "career", "careers", "recruit", "zhaopin", "hr", "join"],
        "url_excludes": ["campus", "intern", "xiaozhao", "校园", "校招", "实习"],
        "title_contains": [
            "后端",
            "前端",
            "全栈",
            "开发",
            "工程师",
            "架构",
            "数据",
            "算法",
            "测试",
            "金融科技",
            "银行科技",
            "新能源",
            "储能",
            "锂电",
            "电池",
            "BMS",
            "化工",
            "研发",
            "项目",
        ],
        "max_items": 200,
        "source_type": "official",
    }

    if host.endswith(".m.zhiye.com"):
        kind = "m_zhiye"
        cfg = {
            "base_url": f"{p.scheme}://{p.netloc}",
            "company_name": company_name.strip(),
            "jc": 1,
            "page_size": 30,
            "max_pages": 40,
            "source_type": "official",
        }
    elif host.endswith(".zhiye.com"):
        sub = host[: -len(".zhiye.com")]
        if sub:
            kind = "m_zhiye"
            cfg = {
                "base_url": f"{p.scheme}://{sub}.m.zhiye.com",
                "company_name": company_name.strip(),
                "jc": 1,
                "page_size": 30,
                "max_pages": 40,
                "source_type": "official",
            }
    elif host.endswith(".hotjob.cn") or host == "hotjob.cn":
        kind = "hotjob"
        base = f"{p.scheme or 'https'}://{p.netloc}" if p.netloc else u
        cfg = {
            "base_url": base.replace("http://", "https://"),
            "company_name": company_name.strip(),
            "recruit_type": 2,
            "page_size": 12,
            "max_pages": 12,
            "source_type": "official",
        }
    elif u.lower().endswith((".rss", ".xml")):
        kind = "rss"
        cfg = {"feed_url": u, "company_name": company_name.strip(), "source_type": "official"}

    if overrides:
        override_kind = str(overrides.get("source_kind") or "").strip()
        if override_kind:
            kind = override_kind
        override_cfg = overrides.get("source_config")
        if isinstance(override_cfg, dict):
            merged = dict(cfg)
            merged.update(override_cfg)
            cfg = merged
        for key in ("priority_group", "priority_rank", "schedule_group"):
            value = overrides.get(key)
            if value is not None and str(value).strip():
                cfg[key] = str(value).strip()

    if proxy and proxy.strip():
        cfg["proxy"] = proxy.strip()
    return kind, apply_default_filters(cfg)


def build_official_source(row: dict, *, proxy: str | None = None) -> tuple[str, str, dict]:
    company_name = str(row.get("name") or "").strip()
    if not company_name:
        raise ValueError("company name is required")
    entry_url = str(row.get("recruitment_url") or "").strip()
    if not entry_url:
        raise ValueError("recruitment_url is required")

    kind, cfg = infer_official_source(company_name, entry_url, proxy=proxy, overrides=row)
    source_name = str(row.get("source_name") or f"Official:{company_name}").strip()
    return kind, source_name, cfg


def load_company_entrypoints(paths: list[str]) -> list[dict]:
    """Load company seed rows from bundled JSON files."""

    merged: dict[str, dict] = {}
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        try:
            rows = json.loads(raw)
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            prev = merged.get(name, {})
            merged[name] = {
                "name": name,
                "company_type": str(row.get("company_type") or prev.get("company_type") or "").strip() or None,
                "industry": str(row.get("industry") or prev.get("industry") or "").strip() or None,
                "hq_location": str(row.get("hq_location") or prev.get("hq_location") or "").strip() or None,
                "focus_directions": str(row.get("focus_directions") or prev.get("focus_directions") or "").strip() or None,
                "website": str(row.get("website") or prev.get("website") or "").strip() or None,
                "recruitment_url": str(row.get("recruitment_url") or prev.get("recruitment_url") or "").strip() or None,
                "source_kind": str(row.get("source_kind") or prev.get("source_kind") or "").strip() or None,
                "source_name": str(row.get("source_name") or prev.get("source_name") or "").strip() or None,
                "priority_group": str(row.get("priority_group") or prev.get("priority_group") or "").strip() or None,
                "priority_rank": str(row.get("priority_rank") or prev.get("priority_rank") or "").strip() or None,
                "schedule_group": str(row.get("schedule_group") or prev.get("schedule_group") or "").strip() or None,
                "source_config": row.get("source_config")
                if isinstance(row.get("source_config"), dict)
                else (prev.get("source_config") if isinstance(prev.get("source_config"), dict) else None),
            }
    return list(merged.values())
