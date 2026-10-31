from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tracker", "0011_material_markup_ok")]

    operations = [
        migrations.AddField(
            "material", "in_silver_report",
            models.BooleanField(
                default=False, verbose_name="count in silver report",
                help_text="Include in the silver used by class report on the Reports page.",
            ),
        ),
    ]
