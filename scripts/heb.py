"""H-E-B prices: fetched from your store via Apify, or typed in by hand.

  python scripts/heb.py pick --category Fridge   # search H-E-B, choose the product for each item
  python scripts/heb.py fetch                    # refresh prices for every chosen product
  python scripts/heb.py show                     # current prices
  python scripts/heb.py show milk                # price history for one item
  python scripts/heb.py todo                     # items with no H-E-B product yet

  python scripts/heb.py enter --category Pantry  # type prices in by hand instead
  python scripts/heb.py set milk 3.29            # override one price by hand

`pick` and `fetch` use the Apify scraper (paid per product, about $0.006);
they show an estimate and ask first. Needs APIFY_TOKEN, and the store number
in config/settings.yaml (stores.heb.store_id).

Item names match exactly or by a unique part ("thighs" -> Chicken Thighs).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from more_dinner_less_dinero import apify, heb  # noqa: E402
from more_dinner_less_dinero.items import find  # noqa: E402
from more_dinner_less_dinero.units import parse_size, unit_price  # noqa: E402

ITEMS = ROOT / "data" / "items.yaml"
DB = ROOT / "data" / "grocery.db"
SETTINGS = ROOT / "config" / "settings.yaml"


def load_items(category: str | None) -> list[dict]:
    if not ITEMS.exists():
        sys.exit("No data/items.yaml yet. Run scripts/import_sheet.py first.")
    items = yaml.safe_load(ITEMS.read_text())["items"]
    if category:
        items = [i for i in items if i["category"].casefold() == category.casefold()]
        if not items:
            sys.exit(f"No items in category '{category}'.")
    return items


def store_id() -> str:
    cfg = yaml.safe_load(SETTINGS.read_text()) if SETTINGS.exists() else {}
    sid = ((cfg or {}).get("stores", {}).get("heb", {}) or {}).get("store_id")
    if not sid:
        sys.exit("Set stores.heb.store_id in config/settings.yaml (your H-E-B store number).")
    return str(sid)


def flags(sale=None, ad=None, coupon=None) -> str:
    return "".join([" SALE" if sale else "", " AD" if ad else "", " coupon" if coupon else ""])


def fmt(p: heb.HebPrice) -> str:
    up = p.unit_price
    per = f"  (${up[0]:.3f}/{up[1]})" if up else ""
    size = f" {p.size}" if p.size else ""
    return (f"${p.price:.2f}{size}{per}{flags(p.on_sale, p.on_weekly_ad, p.coupon)}  "
            f"{p.product or ''}  [{p.recorded_on} {p.source}]")


def confirm(what: str, rows: int, yes: bool) -> bool:
    cost = apify.estimate(rows)
    print(f"{what}: up to {rows} products from Apify, about ${cost:.2f}.")
    return yes or input("Go ahead? [y/N] ").strip().lower() == "y"


def ask(prompt: str, default: str | None = None) -> str:
    hint = f" [{default}]" if default else ""
    return input(f"  {prompt}{hint}: ").strip() or (default or "")


def cmd_pick(db, items: list[dict], per_term: int, yes: bool) -> None:
    todo = heb.without_product(db, items)
    if not todo:
        print("Every item already has an H-E-B product. Use `fetch` to refresh prices.")
        return
    if not confirm(f"Search H-E-B for {len(todo)} items", len(todo) * per_term, yes):
        return
    terms = {i["name"]: i["name"] for i in todo}
    results = apify.by_term(apify.search(list(terms.values()), store_id(), per_term))
    print("\nFor each item: pick a number, Enter to skip, q to stop. Prices are curbside.\n")
    saved = 0
    for n, item in enumerate(todo, 1):
        options = results.get(terms[item["name"]], [])
        print(f"[{n}/{len(todo)}] {item['category']}: {item['name']}")
        if not options:
            print("  No results; try `enter` or `set` for this one.")
            continue
        for k, row in enumerate(options, 1):
            e = apify.to_entry(row)
            up = unit_price(e["price"], e["size"])
            per = f" (${up[0]:.3f}/{up[1]})" if up else ""
            print(f"  {k}. ${e['price']:.2f}  {e['size'] or ''}{per}"
                  f"{flags(e['on_sale'], e['on_weekly_ad'], e['coupon'])}  {e['product']}")
        choice = ask("pick")
        if choice.lower() == "q":
            break
        if not choice.isdigit() or not 1 <= int(choice) <= len(options):
            continue
        entry = heb.record(db, item["name"], **apify.to_entry(options[int(choice) - 1]))
        print("  Saved:", fmt(entry))
        saved += 1
    print(f"\nSaved {saved} products. {len(heb.without_product(db, items))} items still have none.")


def cmd_fetch(db, items: list[dict], yes: bool) -> None:
    chosen = heb.with_product(db, items)
    if not chosen:
        print("No products chosen yet. Run `pick` first.")
        return
    if not confirm(f"Refresh {len(chosen)} H-E-B prices", len(chosen), yes):
        return
    by_id = {p.product_id or apify.product_id(p.url): name for name, p in chosen.items()}
    rows = apify.products([p.url for p in chosen.values()], store_id())
    updated: set[str] = set()
    for row in filter(apify.usable, rows):
        e = apify.to_entry(row)
        name = by_id.get(e["product_id"])
        if name and name not in updated:
            old = chosen[name].price
            new = heb.record(db, name, **e)
            change = f"  (was ${old:.2f})" if abs(new.price - old) >= 0.01 else ""
            print(f"  {name:<22} {fmt(new)}{change}")
            updated.add(name)
    failed = sorted(set(chosen) - updated)
    print(f"Updated {len(updated)} of {len(chosen)} prices.")
    if failed:
        print("No price returned for:", ", ".join(failed))


def cmd_enter(db, items: list[dict]) -> None:
    todo = heb.missing(db, items)
    print(f"{len(todo)} items need an H-E-B price. Enter to skip an item, q to stop.\n")
    done = 0
    for n, item in enumerate(todo, 1):
        print(f"[{n}/{len(todo)}] {item['category']}: {item['name']}")
        price = ask("curbside price $")
        if price.lower() == "q":
            break
        if not price:
            continue
        try:
            value = float(price.lstrip("$"))
        except ValueError:
            print("  Not a price, skipped.")
            continue
        size = ask("size (e.g. 16 oz, 1 gal, 12 ct)", item.get("size"))
        if size and not parse_size(size):
            print(f"  Note: couldn't read '{size}' as a size; it's saved, but there's no unit price.")
        product = ask("product name")
        url = ask("heb.com link")
        entry = heb.record(db, item["name"], value, size=size or None, product=product or None, url=url or None)
        print("  Saved:", fmt(entry))
        done += 1
    print(f"\nSaved {done} prices. {len(heb.missing(db, items))} still missing.")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick"); p.add_argument("--category")
    p.add_argument("-n", type=int, default=5, help="choices per item (default 5)")
    p.add_argument("--yes", action="store_true", help="don't ask before spending")
    f = sub.add_parser("fetch"); f.add_argument("--category"); f.add_argument("--yes", action="store_true")
    e = sub.add_parser("enter"); e.add_argument("--category")
    s = sub.add_parser("set")
    s.add_argument("item"); s.add_argument("price", type=lambda v: float(v.lstrip("$")))
    s.add_argument("--size"); s.add_argument("--product"); s.add_argument("--url")
    sh = sub.add_parser("show"); sh.add_argument("item", nargs="?")
    t = sub.add_parser("todo"); t.add_argument("--category")
    a = ap.parse_args()

    db = heb.connect(DB)
    items = load_items(getattr(a, "category", None))
    try:
        if a.cmd == "pick":
            cmd_pick(db, items, a.n, a.yes)
        elif a.cmd == "fetch":
            cmd_fetch(db, items, a.yes)
        elif a.cmd == "enter":
            cmd_enter(db, items)
        elif a.cmd == "set":
            entry = heb.record(db, find(items, a.item)["name"], a.price,
                               size=a.size, product=a.product, url=a.url)
            print("Saved:", entry.item, fmt(entry))
        elif a.cmd == "show" and a.item:
            name = find(items, a.item)["name"]
            for p in heb.history(db, name):
                print(" ", fmt(p))
            cur = heb.latest(db, name)
            print(f"{name}: {cur.url or 'no link'}" if cur else f"{name}: no H-E-B price yet")
        elif a.cmd == "show":
            prices = heb.all_latest(db)
            for i in items:
                if i["name"] in prices:
                    print(f"  {i['category']:<9} {i['name']:<22} {fmt(prices[i['name']])}")
            print(f"{len(prices)} of {len(items)} items have an H-E-B price")
        elif a.cmd == "todo":
            todo = heb.without_product(db, items)
            for i in todo:
                print(f"  {i['category']:<9} {i['name']}")
            print(f"{len(todo)} of {len(items)} items have no H-E-B product yet")
    except (LookupError, ValueError, RuntimeError) as err:
        sys.exit(str(err))


if __name__ == "__main__":
    main()
