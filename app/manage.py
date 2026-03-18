from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Company, CrawlSource, User
from app.security import hash_password


def cmd_create_user(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        exists = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if exists:
            raise SystemExit("username already exists")
        u = User(
            username=args.username,
            password_hash=hash_password(args.password),
            is_admin=bool(args.admin),
        )
        db.add(u)
        db.commit()
        print(f"created user {u.username} admin={u.is_admin}")
    finally:
        db.close()


def cmd_set_password(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        u = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if not u:
            raise SystemExit("user not found")
        u.password_hash = hash_password(args.password)
        db.add(u)
        db.commit()
        print(f"updated password for {u.username}")
    finally:
        db.close()


def cmd_ensure_user(args: argparse.Namespace) -> None:
    """Create user if missing; otherwise reset password and (optionally) admin flag.

    This is intentionally convenient for local/dev use.
    """

    db = SessionLocal()
    try:
        u = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if not u:
            u = User(
                username=args.username,
                password_hash=hash_password(args.password),
                is_admin=bool(args.admin),
            )
            db.add(u)
            db.commit()
            print(f"created user {u.username} admin={u.is_admin}")
            return

        u.password_hash = hash_password(args.password)
        if args.admin:
            u.is_admin = True
        db.add(u)
        db.commit()
        print(f"ensured user {u.username} admin={u.is_admin} (password reset)")
    finally:
        db.close()


def _load_json(path: str) -> object:
    p = Path(path)
    raw = p.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def cmd_import_companies(args: argparse.Namespace) -> None:
    """Upsert companies (name-unique) from a JSON file."""

    data = _load_json(args.file)
    if not isinstance(data, list):
        raise SystemExit("companies file must be a JSON array")

    db = SessionLocal()
    try:
        created = 0
        updated = 0

        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue

            c = db.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
            if not c:
                c = Company(name=name)
                db.add(c)
                db.flush()
                created += 1
            else:
                updated += 1

            # Only set fields when present in input.
            if "industry" in item and (item.get("industry") is None or str(item.get("industry")).strip()):
                c.industry = (str(item.get("industry")).strip() if item.get("industry") is not None else None)
            if "hq_location" in item and (item.get("hq_location") is None or str(item.get("hq_location")).strip()):
                c.hq_location = (str(item.get("hq_location")).strip() if item.get("hq_location") is not None else None)
            if "focus_directions" in item and (item.get("focus_directions") is None or str(item.get("focus_directions")).strip()):
                c.focus_directions = (
                    (str(item.get("focus_directions")).strip() if item.get("focus_directions") is not None else None)
                )
            if "company_type" in item and (item.get("company_type") is None or str(item.get("company_type")).strip()):
                c.company_type = (str(item.get("company_type")).strip() if item.get("company_type") is not None else None)
            if "website" in item and (item.get("website") is None or str(item.get("website")).strip()):
                c.website = (str(item.get("website")).strip() if item.get("website") is not None else None)
            if "recruitment_url" in item and (item.get("recruitment_url") is None or str(item.get("recruitment_url")).strip()):
                c.recruitment_url = (str(item.get("recruitment_url")).strip() if item.get("recruitment_url") is not None else None)

            db.add(c)

        db.commit()
        print(f"imported companies: created={created} updated={updated} total={created+updated}")
    finally:
        db.close()


def _infer_industry(name: str, note: str) -> str | None:
    text = f"{name} {note}".lower()
    if any(k in text for k in ["电池", "锂电", "储能", "bms", "电化学", "新能源"]):
        return "电池与新能源"
    if any(k in text for k in ["电网", "电力", "发电", "华能", "华电", "国家电网", "南方电网", "三峡"]):
        return "能源与电力"
    if any(k in text for k in ["银行", "金科", "金融科技", "fintech", "核心系统"]):
        return "银行与金融科技"
    if any(k in text for k in ["研究院", "研究所", "科学院"]):
        return "科技与软件"
    return None


def cmd_import_companies_xlsx(args: argparse.Namespace) -> None:
    """Import companies from an Excel file that contains at least a '单位' column.

    This supports the user's internal delivery tracking sheet:
    columns: 分类/投递日期/单位/地点/级别/备注

    Behavior:
    - Upsert Company by name.
    - Optionally create per-company CrawlSource entries (Guopin keyword search) as a coverage booster.
    """

    try:
        import openpyxl  # type: ignore
    except Exception as e:
        raise SystemExit(f"missing dependency openpyxl: {e}")

    xlsx_path = str(args.file)
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

    sheets: list[str]
    if args.sheet:
        sheets = [args.sheet]
    else:
        # Default: only enterprise-oriented sheets (skip civil-service "选调" sheet).
        sheets = [sn for sn in wb.sheetnames if "选调" not in sn]

    db = SessionLocal()
    try:
        created = 0
        updated = 0
        units: dict[str, dict] = {}

        for sn in sheets:
            if sn not in wb.sheetnames:
                continue
            ws = wb[sn]

            # Expect header row in row 1.
            header = [str(c).strip() if c is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
            col = {name: idx for idx, name in enumerate(header) if name}
            if "单位" not in col:
                continue

            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row:
                    continue
                name = row[col["单位"]] if col["单位"] < len(row) else None
                if name is None:
                    continue
                name = str(name).strip()
                if not name:
                    continue
                # Skip obvious non-company numeric placeholders.
                if name.isdigit():
                    continue

                city = None
                if "地点" in col and col["地点"] < len(row):
                    v = row[col["地点"]]
                    if v is not None and str(v).strip():
                        city = str(v).strip()

                level = None
                if "级别" in col and col["级别"] < len(row):
                    v = row[col["级别"]]
                    if v is not None and str(v).strip():
                        level = str(v).strip()

                note = None
                if "备注" in col and col["备注"] < len(row):
                    v = row[col["备注"]]
                    if v is not None and str(v).strip():
                        note = str(v).strip()

                industry = _infer_industry(name, note or "")

                # Keep the "best" info if a company appears multiple times.
                agg = units.get(name) or {}
                if level and not agg.get("company_type"):
                    agg["company_type"] = level
                if city and not agg.get("hq_location"):
                    agg["hq_location"] = city
                if industry and not agg.get("industry"):
                    agg["industry"] = industry
                if note and not agg.get("focus_directions"):
                    # Keep notes short; treat as focus directions hint.
                    agg["focus_directions"] = note[:200]
                units[name] = agg

        for name, meta in sorted(units.items(), key=lambda kv: kv[0]):
            c = db.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
            if not c:
                c = Company(name=name)
                db.add(c)
                db.flush()
                created += 1
            else:
                updated += 1

            # Only fill empty fields; do not overwrite curated seed data.
            if not c.company_type and meta.get("company_type"):
                c.company_type = meta["company_type"]
            if not c.hq_location and meta.get("hq_location"):
                c.hq_location = meta["hq_location"]
            if not c.industry and meta.get("industry"):
                c.industry = meta["industry"]
            if not c.focus_directions and meta.get("focus_directions"):
                c.focus_directions = meta["focus_directions"]

            db.add(c)

        db.commit()

        src_created = 0
        src_updated = 0
        if args.create_sources:
            include = [
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
                "人工智能",
                "平台",
                "中台",
                "云",
                "微服务",
                "DevOps",
                "SRE",
                "测试",
                "银行科技",
                "金融科技",
                "项目管理",
                "架构",
                "架构师",
            ]
            exclude = ["销售", "市场", "商务", "运营", "客服", "财务", "法务", "人力", "行政"]

            city_allow = ["北京", "上海", "广州", "深圳"] if args.city_allowlist else []

            for name in sorted(units.keys()):
                src_name = f"Guopin:{name}"
                cfg = {
                    "company_name": "国聘网",
                    "api_base": "https://gp-api.iguopin.com",
                    "keyword": name,
                    "page_size": int(args.page_size),
                    "max_pages": int(args.max_pages),
                    "include_keywords": include,
                    "exclude_keywords": exclude,
                    "source_type": "aggregator",
                }
                if city_allow:
                    cfg["city_allowlist"] = city_allow

                existing = db.execute(select(CrawlSource).where(CrawlSource.name == src_name)).scalar_one_or_none()
                if existing:
                    existing.kind = "iguopin"
                    existing.enabled = True
                    existing.config = cfg
                    db.add(existing)
                    src_updated += 1
                else:
                    s = CrawlSource(kind="iguopin", name=src_name, enabled=True, config=cfg)
                    db.add(s)
                    src_created += 1

            db.commit()

        print(
            f"imported companies from xlsx: companies_created={created} companies_updated={updated} "
            f"sources_created={src_created} sources_updated={src_updated} total_companies={len(units)}"
        )
    finally:
        db.close()
        try:
            wb.close()
        except Exception:
            pass


def cmd_seed_official_html_sources(args: argparse.Namespace) -> None:
    """Create html_list crawl sources for companies that have recruitment_url set.

    This is best-effort: many official portals are JS-heavy or WAF-protected.
    """

    proxy = str(args.proxy or "").strip() or None
    title_contains = [
        "后端",
        "前端",
        "全栈",
        "开发",
        "工程师",
        "架构",
        "数据",
        "算法",
        "测试",
        "运维",
        "DevOps",
        "SRE",
        "金融科技",
        "银行",
        "新能源",
        "储能",
        "锂电",
        "电池",
        "电化学",
        "材料",
        "化工",
        "研发",
        "项目",
        "项目管理",
    ]
    url_contains = ["job", "jobs", "career", "careers", "recruit", "zhaopin", "hr", "join"]
    url_excludes = ["campus", "intern", "xiaozhao", "校园", "校招", "实习"]

    db = SessionLocal()
    try:
        companies = (
            db.execute(
                select(Company)
                .where(Company.recruitment_url.is_not(None))
                .where(Company.recruitment_url != "")
                .order_by(Company.name.asc())
            )
            .scalars()
            .all()
        )

        created = 0
        updated = 0
        for c in companies:
            name = c.name
            src_name = f"Official:{name}"
            cfg = {
                "list_url": c.recruitment_url,
                "company_name": name,
                "url_contains": url_contains,
                "url_excludes": url_excludes,
                "title_contains": title_contains,
                "max_items": int(args.max_items),
                "source_type": "official",
            }
            if proxy:
                cfg["proxy"] = proxy

            existing = db.execute(select(CrawlSource).where(CrawlSource.name == src_name)).scalar_one_or_none()
            if existing:
                existing.kind = "html_list"
                existing.enabled = True
                existing.config = cfg
                db.add(existing)
                updated += 1
            else:
                s = CrawlSource(kind="html_list", name=src_name, enabled=True, config=cfg)
                db.add(s)
                created += 1

        db.commit()
        print(f"seeded official html sources: created={created} updated={updated} total={created+updated}")
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    cu = sub.add_parser("create-user")
    cu.add_argument("--username", required=True)
    cu.add_argument("--password", required=True)
    cu.add_argument("--admin", action="store_true")
    cu.set_defaults(fn=cmd_create_user)

    sp = sub.add_parser("set-password")
    sp.add_argument("--username", required=True)
    sp.add_argument("--password", required=True)
    sp.set_defaults(fn=cmd_set_password)

    eu = sub.add_parser("ensure-user")
    eu.add_argument("--username", required=True)
    eu.add_argument("--password", required=True)
    eu.add_argument("--admin", action="store_true")
    eu.set_defaults(fn=cmd_ensure_user)

    ic = sub.add_parser("import-companies")
    ic.add_argument("--file", required=True, help="JSON array of {name, industry, company_type, recruitment_url, website}")
    ic.set_defaults(fn=cmd_import_companies)

    ix = sub.add_parser("import-companies-xlsx")
    ix.add_argument("--file", required=True, help="Excel file containing a '单位' column")
    ix.add_argument("--sheet", default="", help="Sheet name (default: all sheets)")
    ix.add_argument("--create-sources", action="store_true", help="Create per-company Guopin crawl sources (keyword search)")
    ix.add_argument("--max-pages", type=int, default=2)
    ix.add_argument("--page-size", type=int, default=50)
    ix.add_argument("--city-allowlist", action="store_true", help="Restrict ingestion to 北上广深 (based on city field)")
    ix.set_defaults(fn=cmd_import_companies_xlsx)

    so = sub.add_parser("seed-official-html-sources")
    so.add_argument("--proxy", default="", help="Optional proxy URL, e.g. http://127.0.0.1:7890")
    so.add_argument("--max-items", type=int, default=200)
    so.set_defaults(fn=cmd_seed_official_html_sources)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
