#!/usr/bin/env python3
"""
Compare-at audit for a Shopify products export (Products -> Export -> CSV).

The kit supports ONE price model:
  - Variant Price            = what the customer pays today
  - Variant Compare At Price = set ONLY during a real, temporary sale (the regular price)

This script lists every variant that has a compare-at price and classifies it, so you
can clean the data BEFORE setting up the anchor price and the price list:

  SALE?         compare-at > price. Correct ONLY if the product is really on a
                temporary sale right now. If the compare-at is a "value" (e.g. sum of
                single-item prices in a bundle) or a permanent fake strikethrough,
                clear it. It would otherwise be reported as "Akcija" every day and
                become the product's anchor price.
  CLEAR         compare-at == price. Meaningless; clear it.
  WRONG         compare-at < price. Clear it.

Usage:
  python3 scripts/audit_compare_at.py products_export_1.csv
  python3 scripts/audit_compare_at.py products_export_1.csv --include-inactive --out audit.csv

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


def to_decimal(value: str) -> Decimal | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


# Shopify has used two sets of column names in product exports; both are accepted.
HEADER_ALIASES = {
    "url handle": "Handle",
    "handle": "Handle",
    "title": "Title",
    "status": "Status",
    "price": "Variant Price",
    "variant price": "Variant Price",
    "compare-at price": "Variant Compare At Price",
    "compare at price": "Variant Compare At Price",
    "variant compare at price": "Variant Compare At Price",
    "sku": "Variant SKU",
    "variant sku": "Variant SKU",
    "option1 value": "Option1 Value",
    "option2 value": "Option2 Value",
    "option3 value": "Option3 Value",
}


def normalise(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if key is None:
            continue
        name = HEADER_ALIASES.get(key.strip().lower(), key.strip())
        if name not in out or not out[name]:
            out[name] = value if value is not None else ""
    return out


def audit(path: Path, include_inactive: bool) -> tuple[list[dict], dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = {HEADER_ALIASES.get(h.strip().lower(), h.strip()) for h in (reader.fieldnames or [])}
        needed = {"Handle", "Variant Price", "Variant Compare At Price"}
        missing = needed - columns
        if missing:
            raise SystemExit(
                f"{path} does not look like a Shopify products export (missing columns: {', '.join(sorted(missing))})"
            )
        titles: dict[str, str] = {}
        statuses: dict[str, str] = {}
        findings: list[dict] = []
        stats = {"variants": 0, "with_compare_at": 0, "SALE?": 0, "CLEAR": 0, "WRONG": 0}
        for raw_row in reader:
            row = normalise(raw_row)
            handle = row.get("Handle", "").strip()
            if row.get("Title", "").strip():
                titles[handle] = row["Title"].strip()
            if row.get("Status", "").strip():
                statuses[handle] = row["Status"].strip().lower()
            price = to_decimal(row.get("Variant Price", ""))
            if price is None:
                continue  # image-only row, not a variant
            status = statuses.get(handle, "")
            if not include_inactive and status and status != "active":
                continue
            stats["variants"] += 1
            compare_at = to_decimal(row.get("Variant Compare At Price", ""))
            if compare_at is None:
                continue
            stats["with_compare_at"] += 1
            if compare_at > price:
                verdict = "SALE?"
            elif compare_at == price:
                verdict = "CLEAR"
            else:
                verdict = "WRONG"
            stats[verdict] += 1
            options = " / ".join(
                v for v in (row.get(f"Option{i} Value", "").strip() for i in (1, 2, 3)) if v and v != "Default Title"
            )
            findings.append(
                {
                    "verdict": verdict,
                    "handle": handle,
                    "title": titles.get(handle, ""),
                    "variant": options,
                    "sku": row.get("Variant SKU", "").strip(),
                    "status": status,
                    "price": f"{price:.2f}",
                    "compare_at": f"{compare_at:.2f}",
                }
            )
    order = {"SALE?": 0, "WRONG": 1, "CLEAR": 2}
    findings.sort(key=lambda f: (order[f["verdict"]], f["handle"], f["variant"]))
    return findings, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit compare-at prices in a Shopify products export.")
    parser.add_argument("export_csv", type=Path, help="Shopify products export (CSV)")
    parser.add_argument("--out", type=Path, help="also write the findings to this CSV file")
    parser.add_argument("--include-inactive", action="store_true", help="include draft/archived products")
    args = parser.parse_args(argv)

    findings, stats = audit(args.export_csv, args.include_inactive)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["verdict", "handle", "title", "variant", "sku", "status", "price", "compare_at"]
            )
            writer.writeheader()
            writer.writerows(findings)
        print(f"Findings written to {args.out}\n")
    scope = "all products" if args.include_inactive else "active products only"
    print(
        f"Compare-at audit ({scope}): {stats['variants']} variants, "
        f"{stats['with_compare_at']} with a compare-at price"
    )
    print(f"  SALE?  {stats['SALE?']:>4}  compare-at > price: must be a REAL temporary sale, otherwise clear it")
    print(f"  WRONG  {stats['WRONG']:>4}  compare-at < price: clear it")
    print(f"  CLEAR  {stats['CLEAR']:>4}  compare-at = price: clear it")
    if findings:
        print()
        width = max(len(f["title"] + (f" [{f['variant']}]" if f["variant"] else "")) for f in findings)
        width = min(max(width, 20), 70)
        print(f"{'VERDICT':<7}  {'PRODUCT':<{width}}  {'PRICE':>9}  {'COMPARE-AT':>10}  HANDLE")
        for f in findings:
            name = f["title"] + (f" [{f['variant']}]" if f["variant"] else "")
            if len(name) > width:
                name = name[: width - 1] + "…"
            print(f"{f['verdict']:<7}  {name:<{width}}  {f['price']:>9}  {f['compare_at']:>10}  {f['handle']}")
    else:
        print("\nNo compare-at prices found. Nothing to clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
