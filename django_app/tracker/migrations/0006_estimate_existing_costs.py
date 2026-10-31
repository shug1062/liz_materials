from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations

PLACES = Decimal("0.0001")
PENNY = Decimal("0.01")


def estimate_existing_costs(apps, schema_editor):
    Purchase = apps.get_model("tracker", "Purchase")
    for purchase in Purchase.objects.filter(unit_cost__isnull=True).select_related("material"):
        markup = purchase.material.markup_percentage or Decimal("0")
        unit_cost = (purchase.unit_price / (1 + markup / 100)).quantize(PLACES, rounding=ROUND_HALF_UP)
        purchase.unit_cost = unit_cost
        purchase.cost_total = (purchase.quantity * unit_cost).quantize(PENNY, rounding=ROUND_HALF_UP)
        purchase.cost_is_estimate = True
        purchase.save(update_fields=["unit_cost", "cost_total", "cost_is_estimate"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0005_purchase_cost")]

    operations = [migrations.RunPython(estimate_existing_costs, migrations.RunPython.noop)]
