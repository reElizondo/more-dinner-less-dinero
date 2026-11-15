"""Client for the Walmart Affiliate API (walmart.io).

Auth: every request carries a consumer ID, a timestamp, a key version and an
RSA-SHA256 signature over those three values, made with your private key.
Signatures expire after 180 seconds, so one is generated per request.

Docs: https://walmart.io/apidocs/affiliates/quickstart
Limits: 5,000 calls per day; Product Lookup takes up to 20 item IDs per call.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE_URL = "https://developer.api.walmart.com/api-proxy/service/affil/product/v2"
LOOKUP_BATCH = 20


def canonicalize(headers: dict[str, str]) -> str:
    """Values of the signed headers, sorted by header name, each followed by a newline."""
    return "".join(f"{headers[k].strip()}\n" for k in sorted(headers))


def sign(private_key_pem: bytes, consumer_id: str, key_version: str, timestamp_ms: int) -> str:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    to_sign = canonicalize({
        "WM_CONSUMER.ID": consumer_id,
        "WM_CONSUMER.INTIMESTAMP": str(timestamp_ms),
        "WM_SEC.KEY_VERSION": key_version,
    })
    signature = key.sign(to_sign.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


@dataclass
class Product:
    item_id: int
    name: str
    brand: str | None
    sale_price: float | None
    msrp: float | None
    upc: str | None
    size: str | None
    in_stock: bool
    clearance: bool
    offer_type: str | None
    product_url: str | None
    raw: dict

    @property
    def discount_pct(self) -> float | None:
        if self.sale_price and self.msrp and self.msrp > self.sale_price:
            return round(100 * (self.msrp - self.sale_price) / self.msrp, 1)
        return None

    @classmethod
    def from_api(cls, d: dict) -> "Product":
        return cls(
            item_id=d.get("itemId"),
            name=d.get("name", ""),
            brand=d.get("brandName"),
            sale_price=d.get("salePrice"),
            msrp=d.get("msrp"),
            upc=d.get("upc"),
            size=d.get("size"),
            in_stock=str(d.get("stock", "")).lower() == "available" or bool(d.get("availableOnline")),
            clearance=bool(d.get("clearance")),
            offer_type=d.get("offerType"),
            product_url=d.get("productUrl") or d.get("productTrackingUrl"),
            raw=d,
        )


class WalmartClient:
    def __init__(self, consumer_id: str, private_key_path: str | Path, key_version: str = "1",
                 zip_code: str | None = None, session: requests.Session | None = None):
        self.consumer_id = consumer_id
        self.key_version = str(key_version)
        self.private_key_pem = Path(private_key_path).expanduser().read_bytes()
        self.zip_code = zip_code
        self.http = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        ts = int(time.time() * 1000)
        return {
            "WM_CONSUMER.ID": self.consumer_id,
            "WM_CONSUMER.INTIMESTAMP": str(ts),
            "WM_SEC.KEY_VERSION": self.key_version,
            "WM_SEC.AUTH_SIGNATURE": sign(self.private_key_pem, self.consumer_id, self.key_version, ts),
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict) -> dict:
        resp = self.http.get(f"{BASE_URL}/{path}", params=params, headers=self._headers(), timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"Walmart API {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def search(self, query: str, num_items: int = 10) -> list[Product]:
        data = self._get("search", {"query": query, "numItems": min(num_items, 25),
                                    "responseGroup": "full"})
        return [Product.from_api(i) for i in data.get("items", [])]

    def lookup(self, item_ids: list[int | str]) -> list[Product]:
        """Current price and availability, for the configured zip code if set."""
        products: list[Product] = []
        for i in range(0, len(item_ids), LOOKUP_BATCH):
            batch = item_ids[i:i + LOOKUP_BATCH]
            params = {"ids": ",".join(str(x) for x in batch)}
            if self.zip_code:
                params["zipCode"] = self.zip_code
            data = self._get("items", params)
            products += [Product.from_api(d) for d in data.get("items", [])]
        return products


def cart_url(items: dict[int | str, int]) -> str:
    """Link that adds items to the Walmart.com cart.

    The documented form is a single item: affil.walmart.com/cart/addToCart?items=<id>.
    The multi-item "id|qty,id|qty" form is UNVERIFIED; test it in a browser.
    """
    value = ",".join(f"{item_id}|{qty}" if qty != 1 else str(item_id) for item_id, qty in items.items())
    return "https://affil.walmart.com/cart/addToCart?" + urlencode({"items": value}, safe=",|")
