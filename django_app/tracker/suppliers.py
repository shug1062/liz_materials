"""Fetch prices from supplier websites (Cooksongold, Metal Clay) with certificate checks on."""
import re
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
import truststore
from bs4 import BeautifulSoup
from django.conf import settings
from requests.adapters import HTTPAdapter

VAT = Decimal("1.2")
PRICE_PLACES = Decimal("0.0001")
TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
SILVER_URL = (
    "https://www.cooksongold.com/Sheet/Sterling-Silver-Sheet-1.00mm-Fully-Annealed,"
    "-100-Recycled-Silver-prcode-CSA-100"
)


class SupplierError(Exception):
    pass


@dataclass
class Quote:
    price: Decimal | None = None  # pack price, or price per gram for weight-priced materials
    weight_per_unit: Decimal | None = None
    error: str = ""


class _TrustStoreAdapter(HTTPAdapter):
    """Use the operating system's certificate store (works behind home routers and proxies)."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return super().init_poolmanager(*args, **kwargs)


def _session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", _TrustStoreAdapter())
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get(session, url) -> requests.Response:
    try:
        response = session.get(url, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SupplierError(f"Couldn't reach the supplier ({exc.__class__.__name__}).") from exc
    if response.status_code == 404:
        raise SupplierError("Product page not found – the supplier link may have changed.")
    if not response.ok:
        raise SupplierError(f"Supplier website returned error {response.status_code}.")
    return response


def _dec(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise SupplierError(f"Couldn't read a price from “{text}”.") from exc


def _vat_basis(price_ex_vat: Decimal) -> Decimal:
    price = price_ex_vat * VAT if settings.SUPPLIER_PRICES_INCLUDE_VAT else price_ex_vat
    return price.quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


# ---------- Cooksongold ----------

def parse_cooksongold_price(html: str, pricing_type: str) -> Decimal:
    """Cooksongold publishes an ex-VAT price in <meta itemprop="price">, e.g. "16.280" or "2097.610 per kg"."""
    meta = BeautifulSoup(html, "html.parser").find("meta", attrs={"itemprop": "price"})
    content = (meta.get("content") or "").strip() if meta else ""
    match = re.match(r"([\d,]+(?:\.\d+)?)\s*(per\s*kg|per\s*g\b)?", content, re.I)
    if not match:
        raise SupplierError("Couldn't find a price on the product page.")
    amount, unit = _dec(match.group(1)), (match.group(2) or "").lower().replace(" ", "")
    by_weight = pricing_type != "fixed"
    if unit and not by_weight:
        raise SupplierError("This product is priced by weight – change the pricing type to a per-gram option.")
    if by_weight and not unit:
        raise SupplierError("This product has a fixed pack price – change the pricing type to Fixed.")
    per_gram = amount / 1000 if unit == "perkg" else amount
    return _vat_basis(per_gram if by_weight else amount)


def parse_weight_per_unit(html: str) -> Decimal | None:
    """Reads wording like "Approx. weight of 100 jump rings is 47.8g" and returns grams per item."""
    # No separator: the site splits numbers across tags ("47" + ".8g").
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text())
    patterns = [
        r"weight\s+(?:of|for)\s+100\s+[a-z ]*?\bis\s+(\d+(?:\.\d+)?)\s*g",
        r"weight\s+per\s+100[:\s]+(\d+(?:\.\d+)?)\s*g",
        r"100\s+(?:pieces|items|rings|units)\s+weigh\s+(?:approx(?:imately)?\.?\s+)?(\d+(?:\.\d+)?)\s*g",
    ]
    for pattern in patterns:
        if match := re.search(pattern, text, re.I):
            return (Decimal(match.group(1)) / 100).quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)
    return None


# ---------- Metal Clay (Shopify) ----------

def parse_metalclay_price(product_json: dict) -> Decimal:
    """Shopify product JSON gives the VAT-inclusive price in pence."""
    pence = product_json.get("price")
    if pence is None:
        raise SupplierError("Couldn't find a price on the product page.")
    inc_vat = Decimal(pence) / 100
    price = inc_vat if settings.SUPPLIER_PRICES_INCLUDE_VAT else inc_vat / VAT
    return price.quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


# ---------- Public API ----------

def supplier_for(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.endswith("cooksongold.com"):
        return "cooksongold"
    if host.endswith("metalclay.co.uk"):
        return "metalclay"
    return None


def fetch_quote(url: str, pricing_type: str, session=None) -> Quote:
    session = session or _session()
    try:
        supplier = supplier_for(url)
        if supplier == "cooksongold":
            html = _get(session, url).text
            weight = parse_weight_per_unit(html) if pricing_type == "per_gram_item" else None
            return Quote(price=parse_cooksongold_price(html, pricing_type), weight_per_unit=weight)
        if supplier == "metalclay":
            if pricing_type != "fixed":
                raise SupplierError("Metal Clay products have fixed prices – change the pricing type to Fixed.")
            path = urlparse(url).path.rstrip("/")
            if "/collections/" in path and "/products/" not in path:
                raise SupplierError("That's a collection page – open the individual product and paste its link.")
            # Old site links (metalclay.co.uk/<slug>/) usually live on at /products/<slug>.
            handle = path.rsplit("/", 1)[-1]
            try:
                data = _get(session, f"https://www.metalclay.co.uk/products/{handle}.js").json()
            except SupplierError as exc:
                if "/products/" not in path:
                    raise SupplierError("Old Metal Clay link that no longer works – open the product on metalclay.co.uk and paste the new link.") from exc
                raise
            return Quote(price=parse_metalclay_price(data))
        raise SupplierError("Price updates only work for Cooksongold and Metal Clay links.")
    except SupplierError as exc:
        return Quote(error=str(exc))
    except ValueError:
        return Quote(error="The supplier page wasn't in the expected format.")


def fetch_quotes(materials) -> dict:
    """Fetch several materials in parallel; returns {material.pk: Quote}."""
    session = _session()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {m.pk: pool.submit(fetch_quote, m.supplier_url, m.pricing_type, session) for m in materials}
    return {pk: future.result() for pk, future in futures.items()}


def fetch_silver_price_per_kg() -> Decimal:
    """Today's sterling silver sheet price per kg, on the same VAT basis as material prices."""
    html = _get(_session(), SILVER_URL).text
    meta = BeautifulSoup(html, "html.parser").find("meta", attrs={"itemprop": "price"})
    match = re.match(r"([\d,]+(?:\.\d+)?)\s*per\s*kg", (meta.get("content") or "") if meta else "", re.I)
    if not match:
        raise SupplierError("Couldn't find the silver price on Cooksongold.")
    return _vat_basis(_dec(match.group(1))).quantize(Decimal("0.01"))
