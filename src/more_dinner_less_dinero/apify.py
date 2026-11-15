"""H-E-B prices from the zaiq/heb-scraper actor on Apify.

https://apify.com/zaiq/heb-scraper — a third-party service that reads
heb.com for a chosen store. Billed per product row returned (about $0.006),
so callers show an estimate and ask before running.

Needs APIFY_TOKEN in the environment.
"""

from __future__ import annotations

import os
import re

import requests

ACTOR = "zaiq~heb-scraper"
RUN_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
PRICE_PER_ROW = 0.006
START_FEE = 0.02


def estimate(rows: int) -> float:
    return round(rows * PRICE_PER_ROW + START_FEE, 2)


def run(actor_input: dict, token: str | None = None, session: requests.Session | None = None) -> list[dict]:
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is not set. Add it to ~/.zshrc and open a new terminal.")
    http = session or requests.Session()
    resp = http.post(RUN_URL, json=actor_input, headers={"Authorization": f"Bearer {token}"}, timeout=600)
    if resp.status_code >= 400:
        raise RuntimeError(f"Apify {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def search(terms: list[str], store_id: str, per_term: int = 5, **kw) -> list[dict]:
    return run({"storeIds": [str(store_id)], "searchTerms": terms, "maxItemsPerQuery": per_term,
                "maxItems": per_term * len(terms), "includeDetails": False}, **kw)


def products(urls: list[str], store_id: str, **kw) -> list[dict]:
    return run({"storeIds": [str(store_id)], "productUrls": urls, "maxItems": len(urls),
                "includeDetails": False}, **kw)


def product_id(url: str | None) -> str | None:
    """heb.com/product-detail/<slug>/314125 -> '314125'."""
    m = re.search(r"/(\d+)/?(?:\?|$)", url or "")
    return m.group(1) if m else None


def usable(row: dict) -> bool:
    return bool(row.get("productUrl")) and (row.get("curbsidePrice") or row.get("price")) is not None


def to_entry(row: dict) -> dict:
    """A scraper row as keyword arguments for heb.record().

    `price` is the curbside price (what pickup costs); the in-store price is
    kept alongside it.
    """
    qty, unit = row.get("sizeQuantity"), row.get("sizeUnit")
    size = f"{qty:g} {unit}" if isinstance(qty, (int, float)) and unit else row.get("size")
    return {
        "price": row.get("curbsidePrice") or row["price"],
        "in_store_price": row.get("price"),
        "size": size,
        "product": (row.get("name") or "").strip() or None,
        "url": row["productUrl"],
        "product_id": str(row.get("productId") or product_id(row["productUrl"]) or "") or None,
        "on_sale": bool(row.get("onSale")),
        "on_weekly_ad": bool(row.get("onWeeklyAd")),
        "coupon": bool(row.get("couponAvailable")),
        "source": "apify",
    }


def by_term(rows: list[dict]) -> dict[str, list[dict]]:
    """Search results grouped by the search term they came from, in rank order."""
    out: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r.get("position") or 0):
        if usable(r):
            out.setdefault(r.get("source") or "", []).append(r)
    return out
