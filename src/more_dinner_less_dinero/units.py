"""Parse package sizes ("16 oz", "1 gal", "6 ct") so prices compare per unit.

Everything is normalized to one base unit per kind:
  weight -> oz, volume -> fl oz, count -> each.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

UNITS = {
    # weight, in oz
    "oz": ("weight", 1.0), "ounce": ("weight", 1.0), "ounces": ("weight", 1.0),
    "lb": ("weight", 16.0), "lbs": ("weight", 16.0), "pound": ("weight", 16.0), "pounds": ("weight", 16.0),
    "g": ("weight", 0.035274), "gram": ("weight", 0.035274), "grams": ("weight", 0.035274),
    "kg": ("weight", 35.274),
    # volume, in fl oz
    "fl oz": ("volume", 1.0), "floz": ("volume", 1.0), "fl. oz": ("volume", 1.0),
    "gal": ("volume", 128.0), "gallon": ("volume", 128.0), "gallons": ("volume", 128.0),
    "qt": ("volume", 32.0), "quart": ("volume", 32.0), "pt": ("volume", 16.0), "pint": ("volume", 16.0),
    "l": ("volume", 33.814), "liter": ("volume", 33.814), "litre": ("volume", 33.814),
    "ml": ("volume", 0.033814),
    # count, in each
    "ct": ("count", 1.0), "count": ("count", 1.0), "each": ("count", 1.0), "ea": ("count", 1.0),
    "pk": ("count", 1.0), "pack": ("count", 1.0), "roll": ("count", 1.0), "rolls": ("count", 1.0),
    "dozen": ("count", 12.0), "dz": ("count", 12.0),
}
BASE = {"weight": "oz", "volume": "fl oz", "count": "each"}

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*([a-z. ]+?)\s*$")


@dataclass(frozen=True)
class Size:
    amount: float      # in the base unit for its kind
    kind: str          # weight | volume | count

    @property
    def base_unit(self) -> str:
        return BASE[self.kind]


def parse_size(text: str | None) -> Size | None:
    """'16 oz' -> Size(16, weight); '1 gal' -> Size(128, volume). None if unknown."""
    if not text:
        return None
    m = _SIZE.match(text.lower())
    if not m:
        return None
    unit = m.group(2).strip().rstrip(".")
    if unit not in UNITS:
        return None
    kind, factor = UNITS[unit]
    return Size(float(m.group(1)) * factor, kind)


def unit_price(price: float | None, size: str | None) -> tuple[float, str] | None:
    """Price per base unit, e.g. (0.25, 'oz'). None if the size can't be parsed."""
    s = parse_size(size)
    if price is None or s is None or s.amount <= 0:
        return None
    return round(price / s.amount, 4), s.base_unit
