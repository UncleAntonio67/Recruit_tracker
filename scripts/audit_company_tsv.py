from __future__ import annotations

import argparse
import re
from pathlib import Path


def _read_text_best_effort(path: Path) -> str:
    b = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", errors="ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Path to the company list text file (TSV-ish).")
    ap.add_argument("--context", type=int, default=220, help="Context chars to show around missing URLs.")
    args = ap.parse_args()

    # Allow running as `python scripts/audit_company_tsv.py` from repo root.
    import sys

    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from app.manage import _ASCII_URL_RE, _parse_company_tsv_text

    p = Path(args.file)
    t = _read_text_best_effort(p).replace("\r\n", "\n").replace("\r", "\n")

    # Raw URL inventory.
    raw_urls = [m.group(0) for m in re.finditer(_ASCII_URL_RE, t)]
    raw_unique = list(dict.fromkeys(raw_urls))

    items = _parse_company_tsv_text(t)
    parsed_urls = [str(it.get("recruitment_url") or "").strip() for it in items if it.get("recruitment_url")]
    parsed_unique = list(dict.fromkeys([u for u in parsed_urls if u]))

    raw_set = set(raw_unique)
    parsed_set = set(parsed_unique)
    missing = [u for u in raw_unique if u not in parsed_set]

    print(f"file={p}")
    print(f"lines={len(t.splitlines())}")
    long_lines = sorted([(i + 1, len(line)) for i, line in enumerate(t.splitlines()) if len(line) > 240], key=lambda x: x[1], reverse=True)
    print(f"long_lines(>240)={len(long_lines)} top10={long_lines[:10]}")
    print(f"raw_urls={len(raw_urls)} raw_unique={len(raw_unique)} parsed_items={len(items)} parsed_unique_urls={len(parsed_unique)}")
    print(f"missing_urls={len(missing)}")

    # Heuristics: suspicious company names (noise from glued chunks).
    suspicious = []
    for it in items:
        nm = str(it.get("name") or "")
        if not nm:
            continue
        if any(x in nm.lower() for x in ("http", "https", "www.")) or any(x in nm for x in ("/", ":", "\\", "\t")):
            suspicious.append((nm, str(it.get("recruitment_url") or "")))
    suspicious = suspicious[:30]
    if suspicious:
        print("suspicious_names(sample up to 30):")
        for nm, u in suspicious:
            print(f"  - {nm} | {u}")

    if missing:
        print("missing_url_details:")
        ctx = int(args.context)
        for u in missing[:120]:
            idx = t.find(u)
            left = t[max(0, idx - ctx) : idx]
            right = t[idx + len(u) : idx + len(u) + max(80, ctx // 2)]
            left = left.replace("\n", "\\n")
            right = right.replace("\n", "\\n")
            print(f"  - {u}")
            print(f"    left=...{left[-ctx:]}")  # trim to avoid huge output
            print(f"    right={right[:ctx//2]}...")

    # Extra sanity: report duplicate company names with multiple URLs (can indicate parse confusion).
    by_name: dict[str, set[str]] = {}
    for it in items:
        nm = str(it.get("name") or "").strip()
        u = str(it.get("recruitment_url") or "").strip()
        if not nm or not u:
            continue
        by_name.setdefault(nm, set()).add(u)
    multi = sorted([(n, sorted(list(us))) for n, us in by_name.items() if len(us) > 1], key=lambda x: len(x[1]), reverse=True)
    if multi:
        print(f"multi_url_same_name={len(multi)} (top 25):")
        for n, us in multi[:25]:
            print(f"  - {n}: {us[:4]}{' ...' if len(us) > 4 else ''}")


if __name__ == "__main__":
    main()
