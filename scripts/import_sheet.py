"""Import the item list from the Google Sheet into data/items.yaml.

  python scripts/import_sheet.py --sheet-url "https://docs.google.com/spreadsheets/d/.../edit?gid=..."
  python scripts/import_sheet.py --csv ~/Downloads/Grocery\\ Essentials.csv

--sheet-url needs the sheet shared as "Anyone with the link can view";
otherwise download it as CSV and use --csv. Settings already in
data/items.yaml (schedules, quantities, brands) are kept.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from more_dinner_less_dinero.items import fetch_sheet, merge, parse_grid, read_csv_text  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sheet-url")
    src.add_argument("--csv", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "items.yaml")
    a = ap.parse_args()

    rows = fetch_sheet(a.sheet_url) if a.sheet_url else read_csv_text(a.csv.expanduser().read_text())
    result = parse_grid(rows)

    existing = yaml.safe_load(a.out.read_text()) if a.out.exists() else {}
    items, removed = merge((existing or {}).get("items", []), result.items)
    a.out.write_text(yaml.safe_dump({"items": items, "meals": result.meals},
                                    sort_keys=False, allow_unicode=True))

    for w in result.warnings:
        print("Note:", w)
    for name in removed:
        print(f"Removed (no longer in the sheet): {name}")
    by_cat: dict[str, int] = {}
    for i in items:
        by_cat[i["category"]] = by_cat.get(i["category"], 0) + 1
    print(f"Wrote {len(items)} items and {len(result.meals)} meals to {a.out}")
    print("  " + ", ".join(f"{c} {n}" for c, n in by_cat.items()))


if __name__ == "__main__":
    main()
