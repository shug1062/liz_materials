"""Work that runs while the app is serving: keeps the daily silver price filled in without anyone opening the dashboard."""
import logging
import threading
import time

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)
CHECK_EVERY_SECONDS = 60 * 60
_started = threading.Event()


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
    if not settings.SILVER_AUTO_FETCH or _started.is_set():
        return
    _started.set()
    threading.Thread(target=_loop, name="daily-silver-price", daemon=True).start()
