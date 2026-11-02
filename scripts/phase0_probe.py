"""Phase 0 feasibility probe for Walmart and H-E-B browser automation.

Commands:
  login   <store>                 open a persistent profile and log in by hand
  search  <store> "<query>"       search and try to read result names and prices
  product <store> "<url>"         open a product page and try to read its price

Every run saves a screenshot and the page HTML to probe-output/ so selectors
can be fixed by inspecting what the site actually served. The selectors below
are starting guesses and will likely need adjusting.
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import BrowserContext, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / ".profiles"
OUTPUT = ROOT / "probe-output"

STORES = {
    "walmart": {
        "home": "https://www.walmart.com/",
        "search": "https://www.walmart.com/search?q={q}",
        # Starting guesses; verify against saved HTML.
        "result_item": "[data-item-id]",
        "result_name": "[data-automation-id='product-title']",
        "result_price": "[data-automation-id='product-price']",
        "product_price": "[itemprop='price']",
    },
    "heb": {
        "home": "https://www.heb.com/",
        "search": "https://www.heb.com/search?q={q}",
        "result_item": "[data-qe-id='productCard']",
        "result_name": "[data-qe-id='productCard'] h4, [data-qe-id='productCard'] a span",
        "result_price": "[data-qe-id='productCard'] [data-qe-id*='price'], [data-qe-id='productCard'] .price",
        "product_price": "[data-qe-id*='price']",
    },
}


def human_pause(low: float = 1.5, high: float = 4.0) -> None:
    time.sleep(random.uniform(low, high))


def open_context(p, store: str) -> BrowserContext:
    profile_dir = PROFILES / store
    profile_dir.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,  # visible browser; headless is far more likely to be blocked
        viewport={"width": 1366, "height": 900},
    )


def capture(page: Page, store: str, label: str) -> None:
    OUTPUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = OUTPUT / f"{store}-{label}-{stamp}"
    page.screenshot(path=f"{base}.png", full_page=True)
    Path(f"{base}.html").write_text(page.content(), encoding="utf-8")
    print(f"Saved {base}.png and {base}.html")


def first_page(ctx: BrowserContext) -> Page:
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def cmd_login(store: str) -> None:
    with sync_playwright() as p:
        ctx = open_context(p, store)
        page = first_page(ctx)
        page.goto(STORES[store]["home"])
        print(f"Log in to {store} in the browser window.")
        if store == "heb":
            print("Also make sure your curbside pickup store is selected.")
        input("Press Enter here when you're done to save the session... ")
        capture(page, store, "after-login")
        ctx.close()


def cmd_search(store: str, query: str) -> None:
    cfg = STORES[store]
    with sync_playwright() as p:
        ctx = open_context(p, store)
        page = first_page(ctx)
        page.goto(cfg["home"])
        human_pause()
        page.goto(cfg["search"].format(q=quote_plus(query)))
        page.wait_for_load_state("domcontentloaded")
        human_pause(3, 6)
        capture(page, store, "search")

        items = page.locator(cfg["result_item"])
        count = items.count()
        print(f"Result elements matched: {count}")
        for i in range(min(count, 5)):
            item = items.nth(i)
            name = _text(item.locator(cfg["result_name"]))
            price = _text(item.locator(cfg["result_price"]))
            print(f"  {i + 1}. {name!r}  price={price!r}")
        if count == 0:
            print("No results matched the selector. Inspect the saved HTML/screenshot;")
            print("you may also be looking at a bot-detection page.")
        input("Press Enter to close the browser... ")
        ctx.close()


def cmd_product(store: str, url: str) -> None:
    cfg = STORES[store]
    with sync_playwright() as p:
        ctx = open_context(p, store)
        page = first_page(ctx)
        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        human_pause(3, 6)
        capture(page, store, "product")
        print(f"Price: {_text(page.locator(cfg['product_price']))!r}")
        print("Try adding the item to the cart by hand and note the button's markup")
        print("in the saved HTML; that selector is the next thing to automate.")
        input("Press Enter to close the browser... ")
        ctx.close()


def _text(locator) -> str | None:
    try:
        if locator.count() == 0:
            return None
        return locator.first.inner_text(timeout=2000).strip()
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("login")
    s.add_argument("store", choices=STORES)
    s = sub.add_parser("search")
    s.add_argument("store", choices=STORES)
    s.add_argument("query")
    s = sub.add_parser("product")
    s.add_argument("store", choices=STORES)
    s.add_argument("url")
    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args.store)
    elif args.command == "search":
        cmd_search(args.store, args.query)
    else:
        cmd_product(args.store, args.url)


if __name__ == "__main__":
    main()
