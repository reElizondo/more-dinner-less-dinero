from datetime import date

import pytest

from more_dinner_less_dinero import heb
from more_dinner_less_dinero.units import parse_size, unit_price


@pytest.mark.parametrize("text,amount,kind", [
    ("16 oz", 16, "weight"), ("2 lb", 32, "weight"), ("1 gal", 128, "volume"),
    ("64 fl oz", 64, "volume"), ("1.5 L", 50.721, "volume"), ("12 ct", 12, "count"),
    ("1 dozen", 12, "count"), ("6 rolls", 6, "count"),
])
def test_parse_size(text, amount, kind):
    s = parse_size(text)
    assert s.kind == kind and s.amount == pytest.approx(amount)


@pytest.mark.parametrize("text", [None, "", "family size", "16"])
def test_parse_size_unknown(text):
    assert parse_size(text) is None


def test_unit_price():
    assert unit_price(3.84, "1 gal") == (0.03, "fl oz")
    assert unit_price(4.00, "2 lb") == (0.125, "oz")
    assert unit_price(4.00, "big") is None


def test_record_latest_and_history(tmp_path):
    db = heb.connect(tmp_path / "g.db")
    heb.record(db, "Milk", 3.48, size="1 gal", product="H-E-B 2% Milk", url="https://heb.com/p/1",
               on=date(2026, 11, 1))
    heb.record(db, "Milk", 3.29, on=date(2026, 11, 15))   # product/size/link carry over
    now = heb.latest(db, "Milk")
    assert now.price == 3.29 and now.size == "1 gal" and now.url == "https://heb.com/p/1"
    assert [p.price for p in heb.history(db, "Milk")] == [3.48, 3.29]
    assert set(heb.all_latest(db)) == {"Milk"}


def test_missing_keeps_list_order(tmp_path):
    db = heb.connect(tmp_path / "g.db")
    heb.record(db, "Eggs", 2.50)
    items = [{"name": "Milk"}, {"name": "Eggs"}, {"name": "Rice"}]
    assert [i["name"] for i in heb.missing(db, items)] == ["Milk", "Rice"]


def test_record_rejects_bad_price(tmp_path):
    db = heb.connect(tmp_path / "g.db")
    with pytest.raises(ValueError):
        heb.record(db, "Milk", 0)


# --- Apify source --------------------------------------------------------

import json  # noqa: E402
import sqlite3  # noqa: E402
from pathlib import Path  # noqa: E402

from more_dinner_less_dinero import apify  # noqa: E402

ROWS = json.loads((Path(__file__).parent / "fixtures" / "heb_search.json").read_text())


def test_by_term_groups_in_rank_order():
    groups = apify.by_term(ROWS)
    assert list(groups) == ["2% milk gallon", "large eggs 12", "chicken thighs"]
    assert [r["position"] for r in groups["2% milk gallon"]] == [1, 2, 3]


def test_to_entry_uses_curbside_price_and_numeric_size():
    thighs = next(r for r in ROWS if r["productId"] == "790544")
    e = apify.to_entry(thighs)
    assert e["price"] == 7.74 and e["in_store_price"] == 7.38
    assert e["size"] == "2 lb" and e["product_id"] == "790544" and e["source"] == "apify"
    assert unit_price(e["price"], e["size"]) == (0.2419, "oz")


def test_product_id_from_url():
    assert apify.product_id("https://www.heb.com/product-detail/h-e-b-2-milk-1-gal/314125") == "314125"
    assert apify.product_id("https://www.heb.com/") is None


def test_estimate():
    assert apify.estimate(94) == 0.58


def test_run_needs_token(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="APIFY_TOKEN"):
        apify.run({})


def test_manual_wins_same_day_newer_fetch_wins(tmp_path):
    db = heb.connect(tmp_path / "g.db")
    milk = next(r for r in ROWS if r["productId"] == "314125")
    heb.record(db, "Milk", on=date(2026, 11, 16), **apify.to_entry(milk))
    heb.record(db, "Milk", 3.50, on=date(2026, 11, 16))            # typed in, same day
    assert heb.latest(db, "Milk").price == 3.50
    assert heb.latest(db, "Milk").url.endswith("/314125")          # link carried over
    heb.record(db, "Milk", on=date(2026, 11, 23), **apify.to_entry(milk))
    assert heb.latest(db, "Milk").source == "apify"


def test_with_and_without_product(tmp_path):
    db = heb.connect(tmp_path / "g.db")
    heb.record(db, "Eggs", 2.0)                                     # price but no link
    heb.record(db, "Milk", **apify.to_entry(ROWS[1]))
    items = [{"name": "Milk"}, {"name": "Eggs"}, {"name": "Rice"}]
    assert [i["name"] for i in heb.without_product(db, items)] == ["Eggs", "Rice"]
    assert list(heb.with_product(db, items)) == ["Milk"]


def test_old_database_gets_new_columns(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE heb_prices (id INTEGER PRIMARY KEY, item TEXT NOT NULL, product TEXT, "
                      "url TEXT, size TEXT, price REAL NOT NULL, recorded_on TEXT NOT NULL);"
                      "INSERT INTO heb_prices (item, price, recorded_on) VALUES ('Milk', 3.0, '2026-11-01');")
    old.commit(); old.close()
    p = heb.latest(heb.connect(path), "Milk")
    assert p.price == 3.0 and p.source == "manual"
