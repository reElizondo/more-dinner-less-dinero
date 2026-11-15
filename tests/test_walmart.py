import base64
from unittest.mock import MagicMock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from more_dinner_less_dinero.walmart import Product, WalmartClient, canonicalize, cart_url, sign


def _key_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return key, pem


def test_canonicalize_sorts_by_header_name():
    s = canonicalize({"WM_SEC.KEY_VERSION": "1", "WM_CONSUMER.ID": "abc", "WM_CONSUMER.INTIMESTAMP": "123"})
    assert s == "abc\n123\n1\n"


def test_signature_verifies_with_public_key():
    key, pem = _key_pem()
    sig = sign(pem, "abc", "1", 123)
    key.public_key().verify(base64.b64decode(sig), b"abc\n123\n1\n", padding.PKCS1v15(), hashes.SHA256())


def test_lookup_batches_by_20_and_passes_zip(tmp_path):
    _, pem = _key_pem()
    key_file = tmp_path / "k.pem"
    key_file.write_bytes(pem)
    session = MagicMock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = {"items": []}
    c = WalmartClient("abc", key_file, zip_code="78701", session=session)
    c.lookup(list(range(45)))
    assert session.get.call_count == 3
    params = session.get.call_args_list[0].kwargs["params"]
    assert len(params["ids"].split(",")) == 20 and params["zipCode"] == "78701"
    assert "WM_SEC.AUTH_SIGNATURE" in session.get.call_args_list[0].kwargs["headers"]


def test_product_discount():
    p = Product.from_api({"itemId": 1, "name": "x", "salePrice": 3.0, "msrp": 4.0})
    assert p.discount_pct == 25.0
    assert Product.from_api({"itemId": 1, "salePrice": 3.0}).discount_pct is None


def test_cart_url():
    assert cart_url({123: 1}) == "https://affil.walmart.com/cart/addToCart?items=123"
    assert cart_url({123: 2, 456: 1}) == "https://affil.walmart.com/cart/addToCart?items=123|2,456"
