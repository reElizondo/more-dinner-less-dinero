"""Try the Walmart Affiliate API from the command line.

  python scripts/walmart_try.py search "great value 2% milk gallon"
  python scripts/walmart_try.py lookup 10450114 10315752
  python scripts/walmart_try.py cart 10450114:2 10315752

Reads the `walmart` section of config/settings.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from more_dinner_less_dinero.walmart import WalmartClient, cart_url  # noqa: E402


def client() -> WalmartClient:
    settings_path = ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        sys.exit("Copy config/settings.example.yaml to config/settings.yaml and fill in the walmart section.")
    cfg = yaml.safe_load(settings_path.read_text())["walmart"]
    return WalmartClient(cfg["consumer_id"], cfg["private_key_path"], cfg.get("key_version", "1"),
                         cfg.get("zip_code"), environment=cfg.get("environment", "prod"))


def show(products) -> None:
    for p in products:
        disc = f"  ({p.discount_pct}% off ${p.msrp})" if p.discount_pct else ""
        flags = " CLEARANCE" if p.clearance else ""
        print(f"{p.item_id:>12}  ${p.sale_price}{disc}{flags}  {p.brand or ''} | {p.name}"
              f"{'' if p.in_stock else '  [out of stock]'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("-n", type=int, default=10)
    s.add_argument("--raw", action="store_true", help="print the raw JSON of the first result")
    l = sub.add_parser("lookup"); l.add_argument("ids", nargs="+")
    l.add_argument("--raw", action="store_true")
    c = sub.add_parser("cart"); c.add_argument("items", nargs="+", help="itemId or itemId:qty")
    a = ap.parse_args()

    if a.cmd == "cart":
        items = {}
        for spec in a.items:
            item_id, _, qty = spec.partition(":")
            items[item_id] = int(qty or 1)
        print(cart_url(items))
        return

    products = client().search(a.query, a.n) if a.cmd == "search" else client().lookup(a.ids)
    show(products)
    if a.raw and products:
        print(json.dumps(products[0].raw, indent=2))


if __name__ == "__main__":
    main()
