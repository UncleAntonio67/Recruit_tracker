from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Company, User
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

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
