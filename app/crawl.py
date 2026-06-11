from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from sqlalchemy import select

from app.crawler.source_defaults import apply_default_filters, infer_official_source, load_company_entrypoints
from app.db import SessionLocal
from app.models import Company, CrawlSource


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


def _upsert_company(db, row: dict) -> tuple[Company, bool]:
    name = str(row.get("name") or "").strip()
    if not name:
        raise ValueError("company name is required")

    existing = db.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
    if existing:
        changed = False
        for fld in ["company_type", "industry", "hq_location", "focus_directions", "website", "recruitment_url"]:
            new_v = row.get(fld)
            if new_v and not getattr(existing, fld):
                setattr(existing, fld, str(new_v).strip())
                changed = True
        if changed:
            db.add(existing)
            db.commit()
        return existing, False

    c = Company(
        name=name,
        company_type=row.get("company_type"),
        industry=row.get("industry"),
        hq_location=row.get("hq_location"),
        focus_directions=row.get("focus_directions"),
        website=row.get("website"),
        recruitment_url=row.get("recruitment_url"),
    )
    db.add(c)
    db.commit()
    return c, True


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

    defaults = apply_default_filters({})
    include = defaults["include_keywords"]
    exclude = defaults["exclude_keywords"]
    city_allow = defaults["city_allowlist"]

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
        (
            "m_zhiye",
            "中核集团",
            {
                "company_name": "中核集团",
                "base_url": "https://cnnc.m.zhiye.com",
                "jc": 1,  # 社招
                "page_size": 30,
                "max_pages": 40,
                "include_keywords": include,
                "exclude_keywords": exclude,
            },
        ),
        (
            "hotjob",
            "上海电气",
            {
                "company_name": "上海电气",
                "base_url": "https://sec.hotjob.cn",
                "recruit_type": 2,  # 社招
                "page_size": 12,
                "max_pages": 10,
                "include_keywords": include,
                "exclude_keywords": exclude,
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


def cmd_seed_official(args: argparse.Namespace) -> None:
    proxy = (args.proxy or "").strip() or None
    paths = [
        "data/company_entrypoints_cn_seed.json",
        "data/company_entrypoints_autofill_20260319_top.json",
        "data/companies_seed_cn.json",
    ]
    rows = load_company_entrypoints(paths)
    if not rows:
        print("no bundled company entrypoints found")
        return

    db = SessionLocal()
    try:
        companies_created = 0
        companies_seen = 0
        sources_created = 0
        sources_updated = 0
        skipped_no_recruitment_url = 0

        for row in rows:
            c, created = _upsert_company(db, row)
            companies_seen += 1
            if created:
                companies_created += 1

            rec_url = (c.recruitment_url or "").strip()
            if not rec_url:
                skipped_no_recruitment_url += 1
                continue

            kind, cfg = infer_official_source(c.name, rec_url, proxy=proxy)
            action = _upsert_source(db, kind=kind, name=f"Official:{c.name}", enabled=True, config=cfg)
            if action == "created":
                sources_created += 1
            else:
                sources_updated += 1

        print(
            json.dumps(
                {
                    "bundled_companies": len(rows),
                    "companies_created": companies_created,
                    "companies_seen": companies_seen,
                    "sources_created": sources_created,
                    "sources_updated": sources_updated,
                    "skipped_no_recruitment_url": skipped_no_recruitment_url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
        stats = run(db, since_days=args.since_days, mode=str(getattr(args, "mode", "") or "all"))
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    finally:
        db.close()


def cmd_run_one(args: argparse.Namespace) -> None:
    from app.crawler.runner import run_one

    db = SessionLocal()
    try:
        source_id = (args.source_id or "").strip()
        if not source_id:
            # Resolve by name for convenience (non-unique names are unlikely but possible).
            name = (args.name or "").strip()
            if not name:
                raise SystemExit("run-one requires --source-id or --name")
            src = db.execute(select(CrawlSource).where(CrawlSource.name == name)).scalar_one_or_none()
            if not src:
                raise SystemExit(f"source not found by name: {name}")
            source_id = src.id

        stats = run_one(db, source_id=source_id, since_days=args.since_days)
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
        choices=["tencent", "kuaishou", "iguopin", "jd", "m_zhiye", "hotjob", "greenhouse", "lever", "rss", "html_list", "url_list"],
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

    so = sub.add_parser("seed-official")
    so.add_argument("--proxy", default="")
    so.set_defaults(fn=cmd_seed_official)

    st = sub.add_parser("seed-template")
    st.set_defaults(fn=cmd_seed_template)

    rn = sub.add_parser("run")
    rn.add_argument("--since-days", type=int, default=180)
    rn.add_argument("--mode", choices=["official", "core", "all"], default="official")
    rn.set_defaults(fn=cmd_run)

    r1 = sub.add_parser("run-one")
    r1.add_argument("--since-days", type=int, default=180)
    r1.add_argument("--source-id", default="")
    r1.add_argument("--name", default="")
    r1.set_defaults(fn=cmd_run_one)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()






