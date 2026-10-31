from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def backfill(apps, schema_editor):
    Material = apps.get_model("tracker", "Material")
    PriceChange = apps.get_model("tracker", "PriceChange")
    Material.objects.filter(Q(name__icontains="silver") | Q(name__icontains="sterling")).update(is_silver=True)
    for material in Material.objects.all():
        change = PriceChange.objects.filter(material=material).order_by("-changed_at").first()
        when = change.changed_at if change else material.last_updated
        Material.objects.filter(pk=material.pk).update(price_date=timezone.localtime(when).date())


class Migration(migrations.Migration):
    dependencies = [("tracker", "0007_classes_and_archive")]

    operations = [
        migrations.AddField(
            "material", "is_silver",
            models.BooleanField(default=False, help_text="Cost follows the silver price on the day of each sale.", verbose_name="silver"),
        ),
        migrations.AddField(
            "material", "price_date",
            models.DateField(default=timezone.localdate, help_text="When the supplier price was last checked.", verbose_name="price date"),
        ),
        migrations.AddField(
            "purchase", "silver_rate",
            models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="silver £/kg",
                                help_text="Silver price on the day of sale, used for the cost of silver materials."),
        ),
        migrations.AddField("silverprice", "source", models.CharField(default="cooksongold", max_length=20)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
