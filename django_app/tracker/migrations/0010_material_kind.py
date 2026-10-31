from decimal import Decimal

from django.db import migrations, models


def classify(apps, schema_editor):
    Material = apps.get_model("tracker", "Material")
    Purchase = apps.get_model("tracker", "Purchase")
    Material.objects.filter(name__icontains="lesson").update(kind="lesson")
    Material.objects.filter(kind="material", name__icontains="order").update(kind="order", is_silver=False)
    # The old app recorded a typed-in amount as "£1 each, no markup" with the pounds as the quantity.
    pound_items = Material.objects.filter(kind="material", pricing_type="fixed", base_price=Decimal("1"),
                                          pack_quantity=Decimal("1"), markup_percentage=0)
    for material in pound_items:
        quantities = Purchase.objects.filter(material=material).values_list("quantity", flat=True)
        if any(q != q.to_integral_value() for q in quantities):
            Material.objects.filter(pk=material.pk).update(kind="order", is_silver=False)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0009_studio_backup_settings")]

    operations = [
        migrations.AddField(
            "material", "kind",
            models.CharField(
                choices=[("material", "Material"), ("lesson", "Lesson fee"), ("order", "Order at cost (type the amount)")],
                default="material", max_length=20, verbose_name="type",
                help_text="Lesson fees and orders at cost are kept out of materials profit.",
            ),
        ),
        migrations.RunPython(classify, migrations.RunPython.noop),
    ]
