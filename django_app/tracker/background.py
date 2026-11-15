"""Daily silver checks and a supplier-price refresh on the first app visit each day."""
import logging
import threading
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
CHECK_EVERY_SECONDS = 60 * 60
SUPPLIER_BATCH_SIZE = 20
SUPPLIER_PAUSE_SECONDS = 5 * 60
_started = threading.Event()
_serving = False
_daily_price_lock = threading.Lock()
_prices_checked_on = None
_price_thread = None


def prices_running():
    return _price_thread is not None and _price_thread.is_alive()


def start_daily_prices():
    """Claim the date persistently; multiple requests and app restarts must not start duplicate refreshes."""
    from .models import DailyPriceRefresh

    global _prices_checked_on, _price_thread
    today = timezone.localdate()
    if not _serving or _prices_checked_on == today or prices_running():
        return
    with _daily_price_lock:
        if _prices_checked_on == today or prices_running():
            return
        refresh, created = DailyPriceRefresh.objects.get_or_create(day=today)
        _prices_checked_on = today
        if created:
            _price_thread = threading.Thread(
                target=refresh_daily_prices, args=(refresh.day,), name="daily-supplier-prices", daemon=True,
            )
            _price_thread.start()


def _supplier_batches(materials):
    from . import suppliers

    for offset in range(0, len(materials), SUPPLIER_BATCH_SIZE):
        if offset:
            time.sleep(SUPPLIER_PAUSE_SECONDS)
        batch = materials[offset:offset + SUPPLIER_BATCH_SIZE]
        quotes = suppliers.fetch_quotes(batch)
        limited = [material for material in batch if quotes[material.pk].rate_limited]
        if limited:
            time.sleep(SUPPLIER_PAUSE_SECONDS)
            quotes.update(suppliers.fetch_quotes(limited))
        yield batch, quotes


def refresh_daily_prices(day):
    from . import silver, suppliers
    from .models import DailyPriceRefresh, Material

    refresh = DailyPriceRefresh.objects.get(day=day)
    completed = False
    try:
        materials = list(Material.objects.filter(kind=Material.Kind.MATERIAL).exclude(supplier_url="")
                         .order_by("price_date", "name"))
        refresh.total = len(materials)
        refresh.save(update_fields=["total"])
        groups = {}
        for material in materials:
            supplier = suppliers.supplier_for(material.supplier_url)
            groups.setdefault(supplier, []).append(material)
        batches = (
            batch
            for supplier, group in groups.items()
            for batch in (_supplier_batches(group) if supplier else [(group, {})])
        )
        for group, quotes in batches:
            for original in group:
                quote = quotes.get(original.pk)
                error = quote.error if quote else (
                    "The supplier did not return a quote." if suppliers.supplier_for(original.supplier_url)
                    else "Price updates only work for Cooksongold and Metal Clay links."
                )
                if not error and quote.price is None:
                    error = "The supplier did not return a price."
                if not error:
                    try:
                        with transaction.atomic():
                            material = Material.objects.filter(pk=original.pk).first()
                            fields = ("supplier_url", "pricing_type", "base_price", "weight_per_unit", "pack_quantity",
                                      "last_updated")
                            if material is None or any(getattr(material, f) != getattr(original, f) for f in fields):
                                raise ValidationError("Material changed during the price check; kept your edits.")
                            final_url = quote.final_url or material.supplier_url
                            material.supplier_url = Material._meta.get_field("supplier_url").clean(final_url, material)
                            changed = material.apply_supplier_price(
                                quote.price,
                                quote.weight_per_unit if quote.weight_per_unit is not None else material.weight_per_unit,
                                timezone.localdate(),
                            )
                            material.save(update_fields=["supplier_url"])
                            if material.is_silver:
                                silver.recost([material])
                        refresh.updated += int(changed)
                    except ValidationError as exc:
                        error = " ".join(exc.messages)
                if error:
                    refresh.errors.append(f"{original.name}: {error}")
                    logger.warning("Daily supplier price not updated for material %s: %s", original.pk, error)
                refresh.checked += 1
                refresh.save(update_fields=["checked", "updated", "errors"])
        completed = True
    finally:
        try:
            if not completed:
                message = "Daily price update stopped unexpectedly. Some prices were not checked; try checking them on Materials."
                refresh.errors.append(message)
                logger.error(message)
            refresh.finished_at = timezone.now()
            refresh.save(update_fields=["finished_at", "errors"])
        finally:
            connections.close_all()


def check_silver_price():
    from . import silver, suppliers

    try:
        silver.fetch_today()
    except suppliers.SupplierError as error:
        logger.warning("Daily silver price not fetched: %s", error)
    finally:
        connections.close_all()


def _loop():
    while True:
        try:
            check_silver_price()
        except Exception:  # never let a surprise (e.g. a locked database) stop the daily check for good
            logger.exception("Daily silver price check failed.")
        time.sleep(CHECK_EVERY_SECONDS)


def start():
    """Start the hourly check once per process; it only fetches when today has no reading yet."""
    global _serving
    _serving = True
    if not settings.SILVER_AUTO_FETCH or _started.is_set():
        return
    _started.set()
    threading.Thread(target=_loop, name="daily-silver-price", daemon=True).start()
