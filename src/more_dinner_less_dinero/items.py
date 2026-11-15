"""Import the item list from the "Grocery Essentials" Google Sheet.

Sheet layout: row 1 holds category names (Fridge, Pantry, ...); each column
lists item names under its category. A column may continue, after a run of
blank cells, with a second unlabeled block; in the current sheet that block
(under Cosmetic) is a list of meals, so it is imported as `meals`.

The sheet only has names. Schedules, quantities and brand rules live in
data/items.yaml and are kept when the sheet is re-imported.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

import requests

# Categories whose items keep well enough to buy ahead when on sale.
KEEPS_WELL_CATEGORIES = {"pantry", "spices", "cosmetic"}
KEEPS_WELL_WORDS = ("frozen",)

DEFAULT_ITEM = {
    "quantity": 1,
    "size": None,
    "every_weeks": 1,        # start weekly; "still have it" bumps it
    "last_bought": None,
    "avoid_brands": [],
}


@dataclass
class SheetImport:
    items: list[dict] = field(default_factory=list)
    meals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def clean(cell: str) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def key(name: str) -> str:
    return clean(name).casefold()


def parse_grid(rows: list[list[str]]) -> SheetImport:
    """Turn the sheet's cell grid (header row first) into items and meals."""
    out = SheetImport()
    if not rows:
        return out
    headers = [clean(h) for h in rows[0]]
    seen: dict[str, str] = {}
    for col, category in enumerate(headers):
        if not category:
            continue
        cells = [clean(r[col]) if col < len(r) else "" for r in rows[1:]]
        gap = False
        for cell in cells:
            if not cell:
                gap = True
                continue
            if gap:  # anything after a blank run is the second block
                out.meals.append(cell)
                continue
            k = key(cell)
            if k in seen:
                out.warnings.append(f"'{cell}' is listed under both {seen[k]} and {category}; kept {seen[k]}")
                continue
            seen[k] = category
            keeps = category.casefold() in KEEPS_WELL_CATEGORIES or any(w in k for w in KEEPS_WELL_WORDS)
            out.items.append({"name": cell, "category": category, **DEFAULT_ITEM,
                              "avoid_brands": [], "keeps_well": keeps})
    return out


def merge(existing: list[dict], imported: list[dict]) -> tuple[list[dict], list[str]]:
    """New list in sheet order; settings you already edited are kept.

    Returns the merged items and the names that are no longer in the sheet
    (dropped from the list and reported, so nothing disappears silently).
    """
    old = {key(i["name"]): i for i in existing}
    merged = []
    for item in imported:
        prev = old.pop(key(item["name"]), None)
        kept = {k: v for k, v in (prev or {}).items() if v is not None}  # empty fields take the default
        merged.append({**item, **kept, "name": item["name"], "category": item["category"]})
    return merged, [i["name"] for i in old.values()]


def csv_export_url(sheet_url: str) -> str:
    """CSV export link for a Google Sheet URL (keeps the gid of the tab)."""
    m = re.search(r"/spreadsheets/d/([\w-]+)", sheet_url)
    if not m:
        raise ValueError(f"Not a Google Sheets URL: {sheet_url}")
    gid = re.search(r"gid=(\d+)", sheet_url)
    url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv"
    return url + (f"&gid={gid.group(1)}" if gid else "")


def read_csv_text(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def fetch_sheet(sheet_url: str) -> list[list[str]]:
    resp = requests.get(csv_export_url(sheet_url), timeout=30)
    if resp.status_code != 200 or "text/csv" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(
            "Couldn't download the sheet as CSV. Share it as 'Anyone with the link can view', "
            "or use File > Download > CSV and pass --csv <file>."
        )
    return read_csv_text(resp.content.decode("utf-8"))


# --- Weekly schedule -------------------------------------------------------
#
# Every item starts at every_weeks: 1. Each week, an item is due once
# every_weeks weeks have passed since last_bought (never bought = due). If
# you still have a due item, it's skipped that week and its interval grows
# by one week (1 -> 2, 2 -> 3, ...), so it comes up again at the new
# interval from when it was last bought.

def weeks_since(d: date | str | None, today: date) -> int | None:
    if d is None:
        return None
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return (today - d).days // 7


def is_due(item: dict, today: date) -> bool:
    since = weeks_since(item.get("last_bought"), today)
    return since is None or since >= (item.get("every_weeks") or 1)


def due_items(items: list[dict], today: date) -> list[dict]:
    return [i for i in items if is_due(i, today)]


def mark_ordered(item: dict, today: date) -> None:
    item["last_bought"] = today


def mark_still_have(item: dict) -> None:
    """Skip it this week and order it one week less often from now on."""
    item["every_weeks"] = (item.get("every_weeks") or 1) + 1


def find(items: list[dict], name: str) -> dict:
    k = key(name)
    exact = [i for i in items if key(i["name"]) == k]
    matches = exact or [i for i in items if k in key(i["name"])]
    if len(matches) != 1:
        found = ", ".join(i["name"] for i in matches) or "nothing"
        raise LookupError(f"'{name}' matches {found}")
    return matches[0]
