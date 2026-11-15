from more_dinner_less_dinero.items import csv_export_url, merge, parse_grid

GRID = [
    ["Fridge", "Pantry", "Cosmetic"],
    ["Milk", "Rice", "Baking Soda"],
    ["Frozen Veggies", "Baking Soda", "Shampoo"],
    ["Eggs ", "", ""],
    ["", "", ""],
    ["", "", "Tacos "],
    ["", " ", "Spaghetti"],
]


def test_parse_grid_categories_meals_and_cleanup():
    r = parse_grid(GRID)
    names = [(i["name"], i["category"]) for i in r.items]
    assert names == [("Milk", "Fridge"), ("Frozen Veggies", "Fridge"), ("Eggs", "Fridge"),
                     ("Rice", "Pantry"), ("Baking Soda", "Pantry"), ("Shampoo", "Cosmetic")]
    assert r.meals == ["Tacos", "Spaghetti"]
    assert any("Baking Soda" in w for w in r.warnings)


def test_keeps_well_by_category_and_frozen():
    keeps = {i["name"]: i["keeps_well"] for i in parse_grid(GRID).items}
    assert keeps == {"Milk": False, "Frozen Veggies": True, "Eggs": False,
                     "Rice": True, "Baking Soda": True, "Shampoo": True}


def test_merge_keeps_user_settings_and_reports_removed():
    imported = parse_grid(GRID).items
    existing = [{"name": "milk", "category": "Dairy", "every_weeks": 1, "quantity": 2},
                {"name": "Old Thing", "category": "Pantry"}]
    merged, removed = merge(existing, imported)
    milk = merged[0]
    assert milk["name"] == "Milk" and milk["category"] == "Fridge"
    assert milk["every_weeks"] == 1 and milk["quantity"] == 2
    assert removed == ["Old Thing"]


def test_csv_export_url_keeps_gid():
    url = "https://docs.google.com/spreadsheets/d/abc_123/edit?gid=42#gid=42"
    assert csv_export_url(url) == "https://docs.google.com/spreadsheets/d/abc_123/export?format=csv&gid=42"


from datetime import date  # noqa: E402

from more_dinner_less_dinero.items import (  # noqa: E402
    due_items, find, is_due, mark_ordered, mark_still_have,
)


def test_imported_items_start_weekly_and_merge_fills_empty_schedule():
    imported = parse_grid(GRID).items
    assert all(i["every_weeks"] == 1 for i in imported)
    merged, _ = merge([{"name": "Milk", "every_weeks": None}], imported)
    assert merged[0]["every_weeks"] == 1


def test_never_bought_is_due():
    assert is_due({"name": "Milk", "every_weeks": 1, "last_bought": None}, date(2026, 11, 16))


def test_weekly_cycle_with_still_have():
    milk = {"name": "Milk", "every_weeks": 1, "last_bought": None}
    week1, week2, week3 = date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 30)
    mark_ordered(milk, week1)
    assert not is_due(milk, date(2026, 11, 20))
    assert is_due(milk, week2)
    mark_still_have(milk)               # still have it at the start of week 2
    assert milk["every_weeks"] == 2
    assert due_items([milk], week2) == []
    assert is_due(milk, week3)          # two weeks after it was bought


def test_still_have_keeps_growing():
    item = {"name": "Rice", "every_weeks": 2}
    mark_still_have(item)
    assert item["every_weeks"] == 3


def test_find_exact_then_partial():
    items = [{"name": "Chicken Thighs"}, {"name": "Chicken Breasts"}, {"name": "Eggs"}, {"name": "Egg whites"}]
    assert find(items, "eggs")["name"] == "Eggs"
    assert find(items, "thighs")["name"] == "Chicken Thighs"
    try:
        find(items, "chicken")
        assert False
    except LookupError as e:
        assert "Chicken Thighs" in str(e)
