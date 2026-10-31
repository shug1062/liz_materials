"""Fetch prices from supplier websites (Cooksongold, Metal Clay) with certificate checks on."""
import re
import ssl
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

import requests
import truststore
from bs4 import BeautifulSoup
from django.conf import settings
from requests.adapters import HTTPAdapter

VAT = Decimal("1.2")
PRICE_PLACES = Decimal("0.0001")
TIMEOUT = 15
# Cooksongold refuses quick bursts of requests (HTTP 429), so pages are fetched one at a time with a pause.
REQUEST_GAP_SECONDS = 2
RATE_LIMIT_RETRY_SECONDS = 15
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


class RateLimited(SupplierError):
    pass


@dataclass
class Quote:
    price: Decimal | None = None  # pack price, or price per gram for weight-priced materials
    weight_per_unit: Decimal | None = None
    error: str = ""
    final_url: str = ""  # where the supplier redirected an old link to
    rate_limited: bool = False


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
    for attempt in range(2):
        try:
            response = session.get(url, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise SupplierError(f"Couldn't reach the supplier ({exc.__class__.__name__}).") from exc
        if response.status_code != 429 or attempt:
            break
        time.sleep(RATE_LIMIT_RETRY_SECONDS)
    if response.status_code == 429:
        raise RateLimited("The supplier asked us to slow down – wait a few minutes, then check again.")
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


def _cooksongold_vat_basis(amount: Decimal, html: str) -> Decimal:
    """Cooksongold shows prices inc VAT unless the visitor switches to ex VAT; the page says which (vatopt)."""
    match = re.search(r"vatopt\s*=\s*['\"](inc|exc)", html)
    page_includes_vat = not match or match.group(1) == "inc"
    if settings.SUPPLIER_PRICES_INCLUDE_VAT:
        price = amount if page_includes_vat else amount * VAT
    else:
        price = amount / VAT if page_includes_vat else amount
    return price.quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


# ---------- Cooksongold ----------

def parse_cooksongold_price(html: str, pricing_type: str) -> Decimal:
    """The price in <meta itemprop="price">, e.g. "16.280" or "2097.380 per kg" (inc VAT by default)."""
    meta = BeautifulSoup(html, "html.parser").find("meta", attrs={"itemprop": "price"})
    content = (meta.get("content") or "").strip() if meta else ""
    match = re.match(r"([\d,]+(?:\.\d+)?)\s*(per\s*kg|per\s*g\b)?", content, re.I)
    if not match:
        raise SupplierError("Couldn't find a price on the product page.")
    amount, unit = _dec(match.group(1)), (match.group(2) or "").lower().replace(" ", "")
    by_weight = pricing_type != "fixed"
    if unit and not by_weight:
        # Chains and wire coils are labelled "per g" in the page data but sold by the item; use the shown price.
        if (shown := _shown_item_price(html)) is not None:
            return shown
        raise SupplierError("This product is priced by weight – change the pricing type to a per-gram option.")
    if by_weight and not unit:
        raise SupplierError("This product has a fixed pack price – change the pricing type to Fixed.")
    per_gram = amount / 1000 if unit == "perkg" else amount
    return _cooksongold_vat_basis(per_gram if by_weight else amount, html)


def _shown_item_price(html: str) -> Decimal | None:
    """The item price as displayed, e.g. "£7.26 £6.05 exc. VAT" (inc VAT first) – only on pages sold by the item."""
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ")).replace("\xa0", " ")
    match = re.search(r"£\s?([\d,]+\.\d{2})\s+£\s?([\d,]+\.\d{2})\s+(exc|inc)\.?\s*VAT", text, re.I)
    if not match:
        return None
    first, second = _dec(match.group(1)), _dec(match.group(2))
    inc_vat, ex_vat = (first, second) if match.group(3).lower() == "exc" else (second, first)
    price = inc_vat if settings.SUPPLIER_PRICES_INCLUDE_VAT else ex_vat
    return price.quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)


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
    # Some pages give a single piece instead: "The approximate weight for 1 piece is 0.26 grams."
    if match := re.search(r"weight\s+(?:of|for)\s+(?:1|one)\s+(?:piece|item|ring|jump ring)\s+is\s+(\d+(?:\.\d+)?)\s*g",
                          text, re.I):
        return Decimal(match.group(1)).quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)
    return None


# ---------- Metal Clay (Shopify) ----------

def parse_metalclay_price(product_json: dict, variant_id: str = "") -> Decimal:
    """Shopify product JSON gives the VAT-inclusive price in pence; products with sizes need the chosen variant."""
    variants = product_json.get("variants") or []
    if variant_id:
        pence = next((v.get("price") for v in variants if str(v.get("id")) == variant_id), None)
    elif len({v.get("price") for v in variants}) > 1:
        raise SupplierError("This product comes in several sizes at different prices – choose the size on "
                            "metalclay.co.uk, then paste that link (it ends in ?variant=…).")
    else:
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
            response = _get(session, url)
            html = response.text
            weight = parse_weight_per_unit(html) if pricing_type == "per_gram_item" else None
            return Quote(price=parse_cooksongold_price(html, pricing_type), weight_per_unit=weight,
                         final_url=response.url if response.history else "")
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
            return Quote(price=parse_metalclay_price(data, parse_qs(urlparse(url).query).get("variant", [""])[0]))
        raise SupplierError("Price updates only work for Cooksongold and Metal Clay links.")
    except RateLimited as exc:
        return Quote(error=str(exc), rate_limited=True)
    except SupplierError as exc:
        return Quote(error=str(exc))
    except ValueError:
        return Quote(error="The supplier page wasn't in the expected format.")


def fetch_quotes(materials) -> dict:
    """Fetch materials one at a time; once the supplier says slow down, the rest wait for next time."""
    session = _session()
    quotes, stopped = {}, None
    for i, m in enumerate(materials):
        if stopped:
            quotes[m.pk] = stopped
            continue
        if i:
            time.sleep(REQUEST_GAP_SECONDS)
        quotes[m.pk] = quote = fetch_quote(m.supplier_url, m.pricing_type, session)
        if quote.rate_limited:
            stopped = quote
    return quotes


def fetch_silver_price_per_kg() -> Decimal:
    """Today's sterling silver sheet price per kg, on the same VAT basis as material prices."""
    html = _get(_session(), SILVER_URL).text
    meta = BeautifulSoup(html, "html.parser").find("meta", attrs={"itemprop": "price"})
    match = re.match(r"([\d,]+(?:\.\d+)?)\s*per\s*kg", (meta.get("content") or "") if meta else "", re.I)
    if not match:
        raise SupplierError("Couldn't find the silver price on Cooksongold.")
    return _cooksongold_vat_basis(_dec(match.group(1)), html).quantize(Decimal("0.01"))
