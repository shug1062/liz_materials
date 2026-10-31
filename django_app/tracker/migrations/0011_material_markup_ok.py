from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tracker", "0010_material_kind")]

    operations = [
        migrations.AddField(
            "material", "markup_ok",
            models.BooleanField(
                default=False, verbose_name="low markup is deliberate",
                help_text="Don't warn about a thin margin unless silver prices mean selling at a loss.",
            ),
        ),
    ]
