from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def remove_double_vat(apps, schema_editor):
    """Cooksongold already shows prices inc VAT, but readings were stored with another 20% added."""
    SilverPrice = apps.get_model("tracker", "SilverPrice")
    Purchase = apps.get_model("tracker", "Purchase")
    for reading in SilverPrice.objects.filter(source="cooksongold"):
        fixed = (reading.price_per_kg / Decimal("1.2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        Purchase.objects.filter(silver_rate=reading.price_per_kg).update(silver_rate=fixed)
        SilverPrice.objects.filter(pk=reading.pk).update(price_per_kg=fixed)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0012_material_in_silver_report")]

    operations = [migrations.RunPython(remove_double_vat, migrations.RunPython.noop)]
