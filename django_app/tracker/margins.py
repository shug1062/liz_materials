"""Spot materials whose margin is thin – either a low markup, or silver has risen since the price was last set."""
from decimal import Decimal

from django.conf import settings

from . import silver

SILVER_PRICED = {"per_gram", "per_gram_item"}


def margin_percent(markup: Decimal) -> Decimal:
    """Share of the student price that is profit, e.g. 20% markup → 16.7% margin."""
    return markup / (100 + markup) * 100


def flag_materials(materials) -> dict[int, list[str]]:
    threshold = Decimal(settings.THIN_MARGIN_PERCENT)
    rates = silver.Rates()
    silver_now = rates.prices[-1] if rates.prices else None

    flags = {}
    for m in materials:
        if m.kind != m.Kind.MATERIAL:
            continue
        reasons = []
        margin = margin_percent(m.markup_percentage)
        low_markup = margin < threshold
        if low_markup and not m.markup_ok:
            reasons.append(f"Markup of {m.markup_percentage.normalize():f}% leaves only a {margin:.0f}% margin.")
        elif silver_now and (m.is_silver or m.pricing_type in SILVER_PRICED) and m.final_price:
            silver_then = rates.on(m.price_date)
            if silver_then and silver_now > silver_then:
                rise = silver_now / silver_then
                real_cost = m.cost_per_item * rise
                real_margin = (m.final_price - real_cost) / m.final_price * 100
                # A deliberately low markup only warns once silver means selling at a loss.
                if real_margin < (0 if low_markup else threshold):
                    reasons.append(
                        f"Silver is up {(rise - 1) * 100:.0f}% since this price was set on {m.price_date.day} {m.price_date:%b} – "
                        f"the real margin is now about {real_margin:.0f}%. Check supplier prices."
                    )
        if reasons:
            flags[m.pk] = reasons
    return flags
