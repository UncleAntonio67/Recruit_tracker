from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import CrawlSource


def _parse_config(text: str) -> dict:
    s = (text or "").strip()
    if not s:
        return {}

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Allow Python literal dict syntax for PowerShell convenience.
        try:
            v = ast.literal_eval(s)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
        raise


def _upsert_source(db, *, kind: str, name: str, enabled: bool, config: dict) -> str:
    existing = db.execute(select(CrawlSource).where(CrawlSource.name == name)).scalar_one_or_none()
    if existing:
        existing.kind = kind
        existing.enabled = enabled
        existing.config = config
        db.add(existing)
        db.commit()
        return "updated"

    s = CrawlSource(kind=kind, name=name, enabled=enabled, config=config)
    db.add(s)
    db.commit()
    return "created"


def cmd_add_source(args: argparse.Namespace) -> None:
    cfg = _parse_config(args.config_json)
    db = SessionLocal()
    try:
        action = _upsert_source(db, kind=args.kind, name=args.name, enabled=not args.disabled, config=cfg)
        print(f"{action} source {args.name} kind={args.kind}")
    finally:
        db.close()


def cmd_list_sources(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        sources = db.execute(select(CrawlSource).order_by(CrawlSource.created_at.asc())).scalars().all()
        for s in sources:
            print(f"{s.enabled}\t{s.kind}\t{s.name}\tlast={s.last_run_at}\tstatus={s.last_status}")
    finally:
        db.close()


def _load_sources_file(path: str) -> list[dict]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    # JSON array
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    except Exception:
        pass

    # JSON lines
    out: list[dict] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        obj = json.loads(s)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def cmd_import_sources(args: argparse.Namespace) -> None:
    sources = _load_sources_file(args.file)
    if not sources:
        print("no sources loaded")
        return

    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for s in sources:
            kind = str(s.get("kind") or "").strip()
            name = str(s.get("name") or "").strip()
            if not kind or not name:
                continue
            enabled = bool(s.get("enabled", True))
            config = s.get("config") if isinstance(s.get("config"), dict) else {}

            action = _upsert_source(db, kind=kind, name=name, enabled=enabled, config=config)
            if action == "created":
                created += 1
            else:
                updated += 1

        print(f"imported sources: created={created} updated={updated} total={created+updated}")
    finally:
        db.close()


def cmd_seed_default(args: argparse.Namespace) -> None:
    """Seed a small set of China sources that are known to work.

    This is intentionally minimal. Add more sources via admin UI or import-sources.
    """

    proxy = (args.proxy or "").strip() or None

    include = [
        # Focus keywords
        "新能源",
        "锂电",
        "电池",
        "电芯",
        "储能",
        "BMS",
        "电化学",
        "材料",
        "研发",
        "后端",
        "后台",
        "软件开发",
        "系统开发",
        "全栈",
        "大数据",
        "数据平台",
        "数据工程",
        "数据开发",
        "数据分析",
        "算法",
        "机器学习",
        "人工智能",
        "平台",
        "中台",
        "云",
        "微服务",
        "DevOps",
        "SRE",
        "运维",
        "测试",
        "银行科技",
        "金融科技",
        "fintech",
        "bank",
        "项目管理",
        "项目经理",
        "PM",
        "架构",
        "架构师",
        "architecture",
        "architect",
    ]

    exclude = [
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
    ]

    city_allow = ["北京", "上海", "广州", "深圳"]

    sources = [
        (
            "tencent",
            "Tencent",
            {
                "company_name": "腾讯",
                "api_keywords": ["新能源", "锂电", "电池", "架构", "项目管理", "金融科技"],
                "max_pages": 12,
                "page_size": 200,
                "include_keywords": include,
                "exclude_keywords": exclude,
                "city_allowlist": city_allow,
            },
        ),
        (
            "kuaishou",
            "Kuaishou",
            {
                "company_name": "快手",
                "page_size": 50,
                "max_pages": 60,
                "include_keywords": include,
                "exclude_keywords": exclude,
                "city_allowlist": city_allow,
            },
        ),
        (
            "iguopin",
            "Guopin",
            {
                "company_name": "国聘网",
                "api_base": "https://gp-api.iguopin.com",
                "api_keywords": ["新能源", "锂电", "电池", "储能", "BMS", "金融科技", "银行科技", "架构", "项目管理"],
                "page_size": 50,
                "max_pages": 40,
                "include_keywords": include,
                "exclude_keywords": exclude,
                "city_allowlist": city_allow,
                "source_type": "aggregator",
            },
        ),
        (
            "jd",
            "JD",
            {
                "company_name": "京东",
                "base_url": "https://zhaopin.jd.com",
                "recruit_type": 3,
                "page_size": 50,
                "max_pages": 40,
                "include_keywords": include,
                "exclude_keywords": exclude,
                "city_allowlist": city_allow,
            },
        ),
    ]

    db = SessionLocal()
    try:
        created = 0
        updated = 0
        for kind, name, cfg in sources:
            cfg = dict(cfg)
            if proxy:
                cfg["proxy"] = proxy
            action = _upsert_source(db, kind=kind, name=name, enabled=True, config=cfg)
            if action == "created":
                created += 1
            else:
                updated += 1

        print(f"seeded default sources: created={created} updated={updated} total={created+updated}")
    finally:
        db.close()


def cmd_seed_template(args: argparse.Namespace) -> None:
    template = [
        {
            "kind": "tencent",
            "name": "Tencent",
            "enabled": True,
            "config": {
                "company_name": "腾讯",
                "api_keywords": ["架构", "项目管理", "新能源", "电池"],
                "max_pages": 12,
                "page_size": 200,
                "include_keywords": ["新能源", "锂电", "电池", "架构", "项目管理", "银行科技"],
                "city_allowlist": ["北京", "上海", "广州", "深圳"],
                "proxy": "http://127.0.0.1:7890",
            },
        },
        {
            "kind": "kuaishou",
            "name": "Kuaishou",
            "enabled": True,
            "config": {
                "company_name": "快手",
                "page_size": 50,
                "max_pages": 60,
                "include_keywords": ["新能源", "锂电", "电池", "架构", "项目管理", "银行科技"],
                "city_allowlist": ["北京", "上海", "广州", "深圳"],
                "proxy": "http://127.0.0.1:7890",
            },
        },
        {
            "kind": "rss",
            "name": "Example-RSS",
            "enabled": False,
            "config": {"feed_url": "https://example.com/jobs.rss", "company_name": "SomeCorp"},
        },
        {
            "kind": "html_list",
            "name": "Example-HTML",
            "enabled": False,
            "config": {
                "list_url": "https://example.com/careers",
                "company_name": "SomeCorp",
                "url_contains": ["job", "career"],
                "title_contains": ["架构", "项目", "电池"],
                "max_items": 200,
                "proxy": "http://127.0.0.1:7890",
            },
        },
    ]
    print(json.dumps(template, ensure_ascii=False, indent=2))

def cmd_run(args: argparse.Namespace) -> None:
    from app.crawler.runner import run

    db = SessionLocal()
    try:
        stats = run(db, since_days=args.since_days)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.crawl")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list-sources")
    ls.set_defaults(fn=cmd_list_sources)

    ad = sub.add_parser("add-source")
    ad.add_argument(
        "--kind",
        required=True,
        choices=["tencent", "kuaishou", "iguopin", "jd", "greenhouse", "lever", "rss", "html_list", "url_list"],
    )
    ad.add_argument("--name", required=True)
    ad.add_argument("--disabled", action="store_true")
    ad.add_argument("--config-json", default="{}")
    ad.set_defaults(fn=cmd_add_source)

    imp = sub.add_parser("import-sources")
    imp.add_argument("--file", required=True)
    imp.set_defaults(fn=cmd_import_sources)

    sd = sub.add_parser("seed-default")
    sd.add_argument("--proxy", default="")
    sd.set_defaults(fn=cmd_seed_default)

    st = sub.add_parser("seed-template")
    st.set_defaults(fn=cmd_seed_template)

    rn = sub.add_parser("run")
    rn.add_argument("--since-days", type=int, default=180)
    rn.set_defaults(fn=cmd_run)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()






