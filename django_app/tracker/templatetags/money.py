from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def gbp(value):
    if value is None or value == "":
        return ""
    value = Decimal(value)
    places = 4 if 0 < abs(value) < Decimal("0.01") else 2
    sign = "-" if value < 0 else ""
    return f"{sign}£{abs(value):,.{places}f}"
