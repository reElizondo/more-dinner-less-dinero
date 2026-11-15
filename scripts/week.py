"""Track the weekly schedule in data/items.yaml.

  python scripts/week.py due                     # what's due this week
  python scripts/week.py have milk "egg whites"  # still have these: skip, order less often
  python scripts/week.py ordered --due           # bought everything that's due
  python scripts/week.py ordered milk eggs       # bought these

Names match exactly or by a unique part ("thighs" -> Chicken Thighs).
--date YYYY-MM-DD overrides today.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from more_dinner_less_dinero.items import (  # noqa: E402
    due_items, find, mark_ordered, mark_still_have,
)

ITEMS = ROOT / "data" / "items.yaml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    h = sub.add_parser("have"); h.add_argument("names", nargs="+")
    o = sub.add_parser("ordered"); o.add_argument("names", nargs="*")
    o.add_argument("--due", action="store_true", help="everything currently due")
    a = ap.parse_args()

    if not ITEMS.exists():
        sys.exit("No data/items.yaml yet. Run scripts/import_sheet.py first.")
    data = yaml.safe_load(ITEMS.read_text())
    items = data["items"]

    try:
        if a.cmd == "due":
            due = due_items(items, a.date)
            for i in due:
                print(f"  {i['category']:<9} {i['name']}  (every {i['every_weeks']} wk)")
            print(f"{len(due)} of {len(items)} items due")
            return
        if a.cmd == "have":
            for name in a.names:
                item = find(items, name)
                mark_still_have(item)
                print(f"{item['name']}: skipped this week, now every {item['every_weeks']} weeks")
        if a.cmd == "ordered":
            chosen = due_items(items, a.date) if a.due else [find(items, n) for n in a.names]
            for item in chosen:
                mark_ordered(item, a.date)
            print(f"Marked {len(chosen)} items as bought on {a.date}")
    except LookupError as e:
        sys.exit(str(e))

    ITEMS.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
