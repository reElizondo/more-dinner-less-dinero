"""Stored H-E-B prices.

H-E-B has no public API. Prices come from two sources:
  - manual:  typed in with scripts/heb.py
  - apify:   fetched for your store by a third-party scraper (apify.py)

Every entry is kept with its date. The current price is the newest entry;
on the same day, a typed-in price wins over a fetched one. `price` is what
curbside pickup costs; fetched entries also keep the in-store price.

Stored in SQLite (data/grocery.db, git-ignored).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .units import unit_price

SCHEMA = """
CREATE TABLE IF NOT EXISTS heb_prices (
    id          INTEGER PRIMARY KEY,
    item        TEXT NOT NULL,     -- item name from data/items.yaml
    product     TEXT,              -- H-E-B product name
    url         TEXT,              -- heb.com product link
    size        TEXT,              -- package size, e.g. "16 oz"
    price       REAL NOT NULL,     -- curbside price for one package
    recorded_on TEXT NOT NULL      -- ISO date
);
CREATE INDEX IF NOT EXISTS heb_prices_item ON heb_prices (item, recorded_on);
"""

# Columns added after the first version; added to older databases on connect.
EXTRA_COLUMNS = {
    "source": "TEXT NOT NULL DEFAULT 'manual'",
    "in_store_price": "REAL",
    "product_id": "TEXT",
    "on_sale": "INTEGER",
    "on_weekly_ad": "INTEGER",
    "coupon": "INTEGER",
}
FIELDS = "item, product, url, size, price, recorded_on, source, in_store_price, product_id, " \
         "on_sale, on_weekly_ad, coupon"
NEWEST_FIRST = "recorded_on DESC, (source = 'manual') DESC, id DESC"


@dataclass
class HebPrice:
    item: str
    product: str | None
    url: str | None
    size: str | None
    price: float
    recorded_on: str
    source: str = "manual"
    in_store_price: float | None = None
    product_id: str | None = None
    on_sale: bool | None = None
    on_weekly_ad: bool | None = None
    coupon: bool | None = None

    @property
    def unit_price(self) -> tuple[float, str] | None:
        return unit_price(self.price, self.size)


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    have = {r[1] for r in db.execute("PRAGMA table_info(heb_prices)")}
    for col, decl in EXTRA_COLUMNS.items():
        if col not in have:
            db.execute(f"ALTER TABLE heb_prices ADD COLUMN {col} {decl}")
    db.commit()
    return db


def record(db: sqlite3.Connection, item: str, price: float, *, product: str | None = None,
           url: str | None = None, size: str | None = None, on: date | None = None,
           source: str = "manual", in_store_price: float | None = None, product_id: str | None = None,
           on_sale: bool | None = None, on_weekly_ad: bool | None = None,
           coupon: bool | None = None) -> HebPrice:
    """Add a price. Product, link and size carry over from the last entry if not given."""
    if price is None or price <= 0:
        raise ValueError("Price must be positive")
    prev = latest(db, item)
    if prev:
        product = product or prev.product
        url = url or prev.url
        size = size or prev.size
        product_id = product_id or prev.product_id
    entry = HebPrice(item, product, url, size, round(price, 2), (on or date.today()).isoformat(),
                     source, in_store_price, product_id, on_sale, on_weekly_ad, coupon)
    db.execute(f"INSERT INTO heb_prices ({FIELDS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (entry.item, entry.product, entry.url, entry.size, entry.price, entry.recorded_on,
                entry.source, entry.in_store_price, entry.product_id, entry.on_sale,
                entry.on_weekly_ad, entry.coupon))
    db.commit()
    return entry


def latest(db: sqlite3.Connection, item: str) -> HebPrice | None:
    row = db.execute(f"SELECT {FIELDS} FROM heb_prices WHERE item = ? ORDER BY {NEWEST_FIRST} LIMIT 1",
                     (item,)).fetchone()
    return HebPrice(*row) if row else None


def all_latest(db: sqlite3.Connection) -> dict[str, HebPrice]:
    rows = db.execute(f"""
        SELECT {FIELDS} FROM heb_prices p
        WHERE id = (SELECT id FROM heb_prices WHERE item = p.item ORDER BY {NEWEST_FIRST} LIMIT 1)""")
    return {r[0]: HebPrice(*r) for r in rows}


def history(db: sqlite3.Connection, item: str) -> list[HebPrice]:
    rows = db.execute(f"SELECT {FIELDS} FROM heb_prices WHERE item = ? ORDER BY recorded_on, id", (item,))
    return [HebPrice(*r) for r in rows]


def missing(db: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """Items that have no H-E-B price yet, in list order."""
    have = set(all_latest(db))
    return [i for i in items if i["name"] not in have]


def without_product(db: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """Items with no saved heb.com product link yet (nothing to fetch prices for)."""
    prices = all_latest(db)
    return [i for i in items if not (prices.get(i["name"]) and prices[i["name"]].url)]


def with_product(db: sqlite3.Connection, items: list[dict]) -> dict[str, HebPrice]:
    """Items that have a saved product link, mapped to their current entry."""
    prices = all_latest(db)
    return {i["name"]: prices[i["name"]] for i in items if prices.get(i["name"]) and prices[i["name"]].url}
