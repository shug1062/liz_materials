"""Silver materials are costed at the silver price on the day of each sale.

A material's supplier price was true on its price date. On any other day its cost is scaled by how
much silver moved between the two: cost on day D = cost per item × silver(D) ÷ silver(price date).
A day without a reading uses the most recent earlier one; with no reading on or before either date,
the cost recorded at the time of sale is kept.
"""
from bisect import bisect_right
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP

from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import UNIT_PRICE_PLACES, Purchase, SilverPrice, money


class Rates:
    """Every reading, loaded once – for re-costing many sales at a time."""

    def __init__(self):
        by_day = {}
        for price, when in SilverPrice.objects.order_by("fetched_at").values_list("price_per_kg", "fetched_at"):
            by_day[timezone.localtime(when).date()] = price
        self.days = sorted(by_day)
        self.prices = [by_day[d] for d in self.days]

    def on(self, day):
        i = bisect_right(self.days, day)
        return self.prices[i - 1] if i else None


class RateLookup:
    """One small query per day asked about – for saving a single sale."""

    def on(self, day):
        end_of_day = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
        return (SilverPrice.objects.filter(fetched_at__lt=end_of_day).order_by("-fetched_at")
                .values_list("price_per_kg", flat=True).first())


def looks_like_silver(material) -> bool:
    """A guess for the Choose silver page: named silver, or sold by weight at a silver-like price per gram."""
    name = f"{material.name} {material.category.name if material.category else ''}".lower()
    if any(word in name for word in ("copper", "gold", "brass", "bronze")):
        return False
    if "silver" in name or "sterling" in name:
        return True
    by_weight = material.pricing_type in (material.PricingType.PER_GRAM, material.PricingType.PER_GRAM_ITEM)
    return by_weight and 1 <= material.base_price <= 10


def unit_cost(material, day, rates):
    then, now = rates.on(material.price_date), rates.on(day)
    if not then or not now:
        return None, None
    return (material.cost_per_item * now / then).quantize(UNIT_PRICE_PLACES, rounding=ROUND_HALF_UP), now


def apply(purchase, rates=None) -> bool:
    cost, rate = unit_cost(purchase.material, purchase.purchase_date, rates or RateLookup())
    if cost is None:
        return False
    purchase.unit_cost, purchase.silver_rate, purchase.cost_is_estimate = cost, rate, False
    purchase.cost_total = money(purchase.quantity * cost)
    return True


def recost(materials=None, since=None) -> int:
    """Re-cost silver sales after silver readings or material prices change. Returns how many changed.

    since: a silver reading for this day changed, so only sales on or after it, or of materials priced on
    or after it, can be affected.
    """
    purchases = Purchase.objects.filter(material__is_silver=True).select_related("material")
    if materials is not None:
        purchases = purchases.filter(material__in=materials)
    if since is not None:
        purchases = purchases.filter(Q(purchase_date__gte=since) | Q(material__price_date__gte=since))
    purchases = list(purchases)
    if not purchases:
        return 0
    rates = Rates()
    changed = []
    for p in purchases:
        before = (p.unit_cost, p.cost_total, p.silver_rate)
        if apply(p, rates) and (p.unit_cost, p.cost_total, p.silver_rate) != before:
            changed.append(p)
    Purchase.objects.bulk_update(changed, ["unit_cost", "cost_total", "cost_is_estimate", "silver_rate"])
    return len(changed)


@receiver(post_save, sender=SilverPrice)
@receiver(post_delete, sender=SilverPrice)
def _silver_reading_changed(instance, created=True, **kwargs):
    # An edited reading may have moved from another date, so check every sale then.
    recost(since=timezone.localtime(instance.fetched_at).date() if created else None)
